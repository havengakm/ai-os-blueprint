"""SupabasePullBackend — real persistence for PullOrchestrator.

Conforms to ``systems.scout.pipeline.pull.StorageBackend``.

Reads ``client_config.active_directories``, checks ``contacts`` for
(source, source_id) or company_domain collisions, inserts new rows,
and writes decision_log entries. Service-role key bypasses RLS.
"""
from __future__ import annotations

from typing import Any

from systems.scout.sources.base import RawCompanyContact
from systems.scout.sources.utils import normalize_domain
from systems.scout.supabase_backends._base import SupabaseLike, insert_decision_log_row


class SupabasePullBackend:
    """Real Supabase-backed implementation of the pull-stage StorageBackend."""

    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def get_active_directories(self, client_id: str) -> list[str]:
        """Return ``client_config.active_directories`` for this client."""
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

    async def contact_exists(
        self,
        client_id: str,
        *,
        source: str | None = None,
        source_id: str | None = None,
        company_domain: str | None = None,
    ) -> bool:
        """Advisory dedup check — True if a contact matches either
        ``(source, source_id)`` or normalised ``company_domain``.
        """
        if source_id is None and company_domain is None:
            raise ValueError(
                "contact_exists requires at least one of source_id or company_domain"
            )

        # Check (source, source_id) first — stronger match.
        if source is not None and source_id is not None:
            resp = (
                self._client.table("contacts")
                .select("id")
                .eq("client_id", client_id)
                .eq("source", source)
                .eq("source_id", source_id)
                .limit(1)
                .execute()
            )
            if resp.data:
                return True

        # Fall back to domain match.
        if company_domain:
            normalised = normalize_domain(company_domain)
            if normalised:
                resp = (
                    self._client.table("contacts")
                    .select("id")
                    .eq("client_id", client_id)
                    .eq("company_domain", normalised)
                    .limit(1)
                    .execute()
                )
                if resp.data:
                    return True

        return False

    async def insert_contact(
        self,
        client_id: str,
        contact: RawCompanyContact,
    ) -> None:
        """Persist a new contact row via INSERT ... ON CONFLICT DO NOTHING.

        The DB-level UNIQUE (client_id, source, source_id) constraint is the
        ultimate guard against races. We use upsert with
        ``ignore_duplicates=True`` where supported; falling back to insert
        otherwise (the orchestrator's advisory check usually catches dupes
        before we get here).
        """
        row = {
            "client_id": client_id,
            "source": contact.source,
            "source_id": contact.source_id,
            "company": contact.company,
            "company_domain": normalize_domain(contact.company_domain),
            "industry": contact.industry,
            "employees": contact.employees,
            "revenue_usd": contact.revenue_usd,
            "geography": contact.geography,
            "city": contact.city,
            "state": contact.state,
            "raw_data": contact.raw_data,
            "status": "new",
        }
        (
            self._client.table("contacts")
            .upsert(
                row,
                on_conflict="client_id,source,source_id",
                ignore_duplicates=True,
            )
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
        """Append an entry to decision_log."""
        insert_decision_log_row(
            self._client,
            client_id=client_id,
            decision_type=decision_type,
            decision=decision,
            context=context,
            reasoning=reasoning,
            confidence=confidence,
        )
