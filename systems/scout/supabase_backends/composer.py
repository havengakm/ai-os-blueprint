"""SupabaseComposerBackend — real persistence for the Composer.

Conforms to ``systems.scout.outreach.composer.ComposerStorageBackend``.

Writes drafts to ``outreach_drafts`` with ``component_selections`` JSONB
(shipped in migration 006). ``persist_draft`` returns the new draft UUID
so the composer can attach it to its decision-log entry.
"""
from __future__ import annotations

from typing import Any

from systems.scout.outreach.component_store import ComponentVariant
from systems.scout.supabase_backends._base import SupabaseLike, insert_decision_log_row


#: Contacts whose ``icp_tier`` is one of these are allowed into compose.
#: D-tier is the "maybe someday" bucket; archived/killed are dropped upstream.
_COMPOSE_TIERS: tuple[str, ...] = ("A", "B", "C")


class SupabaseComposerBackend:
    """Real Supabase-backed implementation of ComposerStorageBackend."""

    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def fetch_eligible_contacts(
        self,
        client_id: str,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return contacts ready for compose.

        Eligibility:
        - ``status = 'enriched'`` (post-enrich terminal state set by
          ``SupabaseEnrichBackend.update_contact_enrich_data``)
        - ``icp_tier`` in A / B / C (D is held, archive is dropped)
        - No existing row in ``outreach_drafts`` for this contact
          (avoids re-composing within the same sequence pass)

        The Supabase Python client has no clean NOT-EXISTS sub-select;
        we fetch both sides and filter client-side. Ordered by tier then
        icp_score desc so the highest-value contacts compose first when
        ``limit`` caps the batch. If perf matters later, swap in an RPC.
        """
        query = (
            self._client.table("contacts")
            .select(
                "id, niche, campaign_id, icp_score, icp_tier, "
                "first_name, company, email, research_data"
            )
            .eq("client_id", client_id)
            .eq("status", "enriched")
            .in_("icp_tier", list(_COMPOSE_TIERS))
        )
        resp = query.execute()
        rows = resp.data or []

        # Contact IDs already drafted — exclude these.
        contact_ids = [row["id"] for row in rows]
        drafted: set[str] = set()
        if contact_ids:
            drafts_resp = (
                self._client.table("outreach_drafts")
                .select("contact_id")
                .eq("client_id", client_id)
                .in_("contact_id", contact_ids)
                .execute()
            )
            drafted = {
                d["contact_id"]
                for d in (drafts_resp.data or [])
                if d.get("contact_id") is not None
            }

        eligible = [row for row in rows if row["id"] not in drafted]
        eligible.sort(
            key=lambda r: (
                _COMPOSE_TIERS.index(r.get("icp_tier"))
                if r.get("icp_tier") in _COMPOSE_TIERS
                else len(_COMPOSE_TIERS),
                -(r.get("icp_score") or 0),
            )
        )
        if limit is not None:
            eligible = eligible[:limit]

        # Composer.compose reads ``contact_id`` (DB column is ``id``).
        # ``offer_label`` is intentionally absent — the contacts table has
        # no such column. Multi-offer routing is a Plan 2 concern; for now
        # Composer.compose sees ``offer_label=""`` and either matches an
        # empty-labelled variant or skips cleanly with a logged decision.
        out: list[dict[str, Any]] = []
        for row in eligible:
            out.append(
                {
                    "contact_id": row["id"],
                    "niche": row.get("niche") or "",
                    "first_name": row.get("first_name"),
                    "company": row.get("company"),
                    "email": row.get("email"),
                    "icp_tier": row.get("icp_tier"),
                    "icp_score": row.get("icp_score"),
                    "research_data": row.get("research_data") or {},
                }
            )
        return out

    async def fetch_approved_variants(
        self,
        client_id: str,
        niche: str,
        offer_label: str,
    ) -> dict[str, list[ComponentVariant]]:
        """Return approved ComponentVariants grouped by component_type.

        Reads win_rate + sample_size from the DB (Plan 2's learned
        state) — the composer's bandit needs them for exploit scoring.
        """
        resp = (
            self._client.table("component_variants")
            .select(
                "component_type, variant_key, niche, offer_label, "
                "variant_content, status, metadata, ab_epsilon, "
                "win_rate, sample_size"
            )
            .eq("client_id", client_id)
            .eq("niche", niche)
            .eq("offer_label", offer_label)
            .eq("status", "approved")
            .execute()
        )

        out: dict[str, list[ComponentVariant]] = {}
        for row in resp.data or []:
            variant = ComponentVariant(
                variant_key=row["variant_key"],
                component_type=row["component_type"],
                niche=row["niche"],
                offer_label=row["offer_label"],
                variant_content=row["variant_content"],
                status=row.get("status", "approved"),
                metadata=row.get("metadata") or {},
                ab_epsilon=float(row.get("ab_epsilon") or 0.1),
                win_rate=(
                    float(row["win_rate"])
                    if row.get("win_rate") is not None
                    else None
                ),
                sample_size=int(row.get("sample_size") or 0),
            )
            out.setdefault(variant.component_type, []).append(variant)
        return out

    async def fetch_active_directories(self, client_id: str) -> list[str]:
        """Return ``client_config.active_directories``."""
        resp = (
            self._client.table("client_config")
            .select("active_directories")
            .eq("client_id", client_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return []
        return list(rows[0].get("active_directories") or [])

    async def persist_draft(
        self,
        client_id: str,
        contact_id: str,
        *,
        subject: str,
        body: str,
        component_selections: dict[str, str],
        research_sources: list[dict[str, Any]],
    ) -> str:
        """Insert into outreach_drafts and return the new draft UUID."""
        row = {
            "client_id": client_id,
            "contact_id": contact_id,
            "subject": subject,
            "body": body,
            "component_selections": component_selections,
            "research_sources": research_sources,
            "status": "rendered",
        }
        resp = (
            self._client.table("outreach_drafts")
            .insert(row)
            .execute()
        )
        data = resp.data or []
        if not data:
            raise RuntimeError("persist_draft: insert returned no rows")
        return str(data[0]["id"])

    async def log_decision(self, client_id: str, **kwargs: Any) -> str | None:
        """Minimal log_decision — composer passes kwargs directly."""
        insert_decision_log_row(
            self._client,
            client_id=client_id,
            decision_type=kwargs.get("decision_type", ""),
            decision=kwargs.get("decision", ""),
            context=kwargs.get("context") or {},
            reasoning=kwargs.get("reasoning"),
            confidence=kwargs.get("confidence"),
            source=kwargs.get("source", "system"),
        )
        return None
