"""SupabaseCheapResolveBackend — real persistence for CheapResolveStage.

Conforms to ``systems.scout.pipeline.cheap_resolve.CheapResolveStorageBackend``.
"""
from __future__ import annotations

from typing import Any

from systems.scout.pipeline.cheap_resolve import ContactRow
from systems.scout.supabase_backends._base import SupabaseLike, insert_decision_log_row


class SupabaseCheapResolveBackend:
    """Real Supabase-backed implementation of the cheap-resolve stage backend."""

    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def get_unresolved_contacts(
        self,
        client_id: str,
        *,
        limit: int | None = None,
    ) -> list[ContactRow]:
        """Return contacts with no domain yet AND status='new'.

        These are freshly-pulled contacts that the cheap-resolve stage
        should attempt to enrich BEFORE score_v1 runs. Score_v1 only
        operates on status='new', so cheap-resolve must run on the same
        cohort.
        """
        query = (
            self._client.table("contacts")
            .select("id, company, source, company_domain, industry, raw_data")
            .eq("client_id", client_id)
            .eq("status", "new")
            .is_("company_domain", "null")
        )
        if limit is not None:
            query = query.limit(limit)
        resp = query.execute()

        out: list[ContactRow] = []
        for row in resp.data or []:
            out.append(
                ContactRow(
                    contact_id=row["id"],
                    company=row.get("company") or "",
                    source=row.get("source") or "",
                    company_domain=row.get("company_domain"),
                    industry=row.get("industry"),
                    raw_data=row.get("raw_data") or {},
                )
            )
        return out

    async def update_contact_company_data(
        self,
        client_id: str,
        contact_id: str,
        *,
        company_domain: str | None = None,
        industry: str | None = None,
    ) -> None:
        """Set company-level fields on a contact. Only writes non-None
        values so partial fills don't clobber pre-existing data."""
        payload: dict[str, Any] = {}
        if company_domain is not None:
            payload["company_domain"] = company_domain
        if industry is not None:
            payload["industry"] = industry
        if not payload:
            return
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
