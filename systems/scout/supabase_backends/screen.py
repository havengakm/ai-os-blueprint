"""SupabaseScreenBackend — real persistence for ScreenStage.

Conforms to ``systems.scout.pipeline.screen.ScreenStorageBackend``.
"""
from __future__ import annotations

from typing import Any

from systems.scout.pipeline.screen import ContactToScreen
from systems.scout.supabase_backends._base import SupabaseLike, insert_decision_log_row


class SupabaseScreenBackend:
    """Real Supabase-backed implementation of the screen-stage backend."""

    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def get_client_config(self, client_id: str) -> dict[str, Any]:
        """Return an icp-shaped config dict — only blacklists are consulted
        by ``screen_contact``."""
        resp = (
            self._client.table("icp_definitions")
            .select("blacklist_companies, blacklist_domains")
            .eq("client_id", client_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        icp = rows[0] if rows else {}
        return {"icp": icp}

    async def get_contacts_for_screening(
        self,
        client_id: str,
        *,
        limit: int | None = None,
    ) -> list[ContactToScreen]:
        """Return contacts currently at status='screened' (post-v1 scoring)."""
        query = (
            self._client.table("contacts")
            .select("id, first_name, last_name, company, company_domain")
            .eq("client_id", client_id)
            .eq("status", "screened")
        )
        if limit is not None:
            query = query.limit(limit)
        resp = query.execute()

        out: list[ContactToScreen] = []
        for row in resp.data or []:
            out.append(
                ContactToScreen(
                    contact_id=row["id"],
                    first_name=row.get("first_name"),
                    last_name=row.get("last_name"),
                    company=row.get("company"),
                    company_domain=row.get("company_domain"),
                )
            )
        return out

    async def mark_contact_passed(self, client_id: str, contact_id: str) -> None:
        """Transition status 'screened' → 'ready'."""
        (
            self._client.table("contacts")
            .update({"status": "ready"})
            .eq("client_id", client_id)
            .eq("id", contact_id)
            .execute()
        )

    async def mark_contact_rejected(
        self,
        client_id: str,
        contact_id: str,
        *,
        reason: str,
    ) -> None:
        """Set status='dead', embed reason in raw_data."""
        resp = (
            self._client.table("contacts")
            .select("raw_data")
            .eq("client_id", client_id)
            .eq("id", contact_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        raw_data = (rows[0].get("raw_data") if rows else None) or {}
        raw_data["screen_reject_reason"] = reason

        (
            self._client.table("contacts")
            .update({"status": "dead", "raw_data": raw_data})
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
