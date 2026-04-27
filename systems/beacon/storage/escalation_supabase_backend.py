"""SupabaseEscalationBackend — real persistence for the escalation queue.

Conforms to ``systems.beacon.reply.escalation.EscalationBackend``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from systems.scout.supabase_backends._base import SupabaseLike


class SupabaseEscalationBackend:
    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def insert_escalation(
        self,
        *,
        client_id: str,
        contact_id: str,
        reply_id: str | None,
        escalation_type: str,
        summary: str,
        raw_data: dict,
    ) -> str:
        new_id = str(uuid4())
        (
            self._client.table("escalations")
            .insert(
                {
                    "id": new_id,
                    "client_id": client_id,
                    "contact_id": contact_id,
                    "reply_id": reply_id,
                    "escalation_type": escalation_type,
                    "summary": summary,
                    "status": "open",
                    "raw_data": raw_data,
                }
            )
            .execute()
        )
        return new_id

    async def mark_resolved(
        self, escalation_id: str, *, resolved_by: str
    ) -> None:
        (
            self._client.table("escalations")
            .update(
                {
                    "status": "resolved",
                    "resolved_by": resolved_by,
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", escalation_id)
            .execute()
        )

    async def mark_dismissed(
        self, escalation_id: str, *, dismissed_by: str
    ) -> None:
        (
            self._client.table("escalations")
            .update(
                {
                    "status": "dismissed",
                    "resolved_by": dismissed_by,
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", escalation_id)
            .execute()
        )

    async def list_open(self, client_id: str) -> list[dict]:
        resp = (
            self._client.table("escalations")
            .select(
                "id, client_id, contact_id, reply_id, escalation_type, "
                "summary, status, raw_data, created_at"
            )
            .eq("client_id", client_id)
            .eq("status", "open")
            .order("created_at", desc=True)
            .execute()
        )
        return list(resp.data or [])
