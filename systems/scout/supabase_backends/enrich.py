"""SupabaseEnrichBackend + SupabaseBudgetTracker.

- ``SupabaseEnrichBackend`` conforms to
  ``systems.scout.pipeline.enrich.EnrichStorageBackend``.
- ``SupabaseBudgetTracker`` conforms to
  ``systems.scout.enrich.orchestrator.BudgetTracker``.

Both backends pair with EnrichStage — keeping them in one module avoids
a tiny standalone budget-tracker file.
"""
from __future__ import annotations

from typing import Any

from systems.scout.pipeline.enrich import EnrichContactRow
from systems.scout.supabase_backends._base import (
    SupabaseLike,
    deep_merge_into,
    insert_decision_log_row,
)


_ARCHIVED_STATUSES: tuple[str, ...] = (
    "archived",
    "archived_no_decision_maker",
    "killed",
)


class SupabaseEnrichBackend:
    """Real Supabase-backed implementation of the enrich-stage backend."""

    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def get_eligible_contacts_for_enrich(
        self,
        client_id: str,
        *,
        archive_floor: int,
        limit: int | None = None,
    ) -> list[EnrichContactRow]:
        """Return contacts eligible for enrichment."""
        query = (
            self._client.table("contacts")
            .select(
                "id, icp_tier, email, company, company_domain, "
                "linkedin_url, industry, research_data"
            )
            .eq("client_id", client_id)
            .gte("icp_score", archive_floor)
            .not_.is_("first_name", "null")
            .is_("enriched_at", "null")
            .not_.in_("status", list(_ARCHIVED_STATUSES))
        )
        if limit is not None:
            query = query.limit(limit)
        resp = query.execute()

        out: list[EnrichContactRow] = []
        for row in resp.data or []:
            out.append(
                EnrichContactRow(
                    contact_id=row["id"],
                    icp_tier=row.get("icp_tier") or "D",
                    email=row.get("email"),
                    company=row.get("company") or "",
                    company_domain=row.get("company_domain"),
                    linkedin_url=row.get("linkedin_url"),
                    industry=row.get("industry"),
                    existing_research_data=row.get("research_data") or {},
                )
            )
        return out

    async def get_client_trigify_search_ids(self, client_id: str) -> list[str]:
        """Return ``client_config.trigify_search_ids`` for this client.

        The column is expected to be TEXT[] (nullable). Missing or null
        returns empty list — the Trigify adapter then skips with
        ``no_monitors_configured``.
        """
        resp = (
            self._client.table("client_config")
            .select("trigify_search_ids")
            .eq("client_id", client_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return []
        return list(rows[0].get("trigify_search_ids") or [])

    async def update_contact_enrich_data(
        self,
        client_id: str,
        contact_id: str,
        *,
        research_data_patch: dict[str, Any],
        email_verified: bool | None,
        email_catch_all: bool | None,
        enriched_at_utc: str,
    ) -> None:
        """Read-modify-write merge the patch into contacts.research_data.

        Service-role key + single-writer discipline (the enrich stage is
        operator-triggered, not concurrent) makes optimistic locking
        unnecessary for MVP. Plan 2 may introduce a version column if
        concurrency becomes real.
        """
        # Read existing research_data.
        resp = (
            self._client.table("contacts")
            .select("research_data")
            .eq("client_id", client_id)
            .eq("id", contact_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        existing = (rows[0].get("research_data") if rows else None) or {}

        # Deep-merge patch in place.
        deep_merge_into(existing, research_data_patch or {})

        payload: dict[str, Any] = {
            "research_data": existing,
            "enriched_at": enriched_at_utc,
            "status": "enriched",
        }
        if email_verified is not None:
            payload["email_verified"] = email_verified
        if email_catch_all is not None:
            payload["email_catch_all"] = email_catch_all

        (
            self._client.table("contacts")
            .update(payload)
            .eq("client_id", client_id)
            .eq("id", contact_id)
            .execute()
        )

    async def log_decision(
        self,
        client_id: str,
        *,
        decision_type: str,
        decision: str,
        context: dict[str, Any],
        reasoning: str | None = None,
        confidence: float | None = None,
    ) -> None:
        insert_decision_log_row(
            self._client,
            client_id=client_id,
            decision_type=decision_type,
            decision=decision,
            context=context,
            reasoning=reasoning,
            confidence=confidence,
        )


class SupabaseBudgetTracker:
    """Real Supabase-backed tier-budget accounting.

    Reads ``client_config.tier_budgets_cents[tier]`` as the cap and
    ``client_config.tier_spent_cents[tier]`` as the running spend.
    ``remaining_cents = cap - spent``; fails safe to ``0`` when either
    side is missing.

    ``record_spend`` does a read-modify-write on tier_spent_cents; a
    single-writer discipline (per-tier enrich runs are not concurrent)
    makes this safe without optimistic locking. Postgres atomicity
    within the UPDATE keeps the JSONB consistent on the write side.
    """

    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def remaining_cents(self, client_id: str, tier: str) -> int:
        """Return remaining cents of budget for (client_id, tier)."""
        resp = (
            self._client.table("client_config")
            .select("tier_budgets_cents, tier_spent_cents")
            .eq("client_id", client_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return 0
        row = rows[0]
        budgets = row.get("tier_budgets_cents") or {}
        spent = row.get("tier_spent_cents") or {}
        try:
            cap = int(budgets.get(tier, 0))
            used = int(spent.get(tier, 0))
        except (TypeError, ValueError):
            return 0
        return cap - used

    async def record_spend(self, client_id: str, tier: str, cents: int) -> None:
        """Debit ``cents`` from the tier-specific running spend counter."""
        resp = (
            self._client.table("client_config")
            .select("tier_spent_cents")
            .eq("client_id", client_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        spent = (rows[0].get("tier_spent_cents") if rows else None) or {}
        try:
            current = int(spent.get(tier, 0))
        except (TypeError, ValueError):
            current = 0
        spent[tier] = current + int(cents)
        (
            self._client.table("client_config")
            .update({"tier_spent_cents": spent})
            .eq("client_id", client_id)
            .execute()
        )
