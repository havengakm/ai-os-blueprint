"""SupabaseCoolOffBackend — real persistence for the cool-off runtime.

Conforms to ``systems.beacon.reply.cool_off.CoolOffBackend``.

Two query-shaped methods (find_idle / find_ready) use multi-query
Python assembly because the Supabase client doesn't traverse joins.
This matches the SupabaseSendBackend pattern (eligibility computed
in Python after pulling candidate rows + their auxiliary data).

A future ``v_idle_contacts`` Postgres VIEW could push find_idle down
to SQL when load justifies; for v1 this approach is straightforward
and FakeSupabaseClient-testable.
"""
from __future__ import annotations

from datetime import datetime

from systems.beacon.reply.cool_off import CoolOffContactRef
from systems.scout.supabase_backends._base import SupabaseLike


_BLOCKED_STATUSES = frozenset(
    {"dnd", "unsubscribed", "dead", "cooling_off", "opted_out"}
)


class SupabaseCoolOffBackend:
    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def find_idle_contacts_for_cool_off(
        self, client_id: str, *, idle_days: int, now: datetime,
    ) -> list[CoolOffContactRef]:
        # 1. Pull contacts with status='sent' (sequence finished) for this client.
        contacts_resp = (
            self._client.table("contacts")
            .select("id, client_id, status, sequence_round")
            .eq("client_id", client_id)
            .eq("status", "sent")
            .execute()
        )
        candidates = [
            c for c in (contacts_resp.data or [])
            if c.get("status") not in _BLOCKED_STATUSES
        ]
        if not candidates:
            return []
        contact_ids = [c["id"] for c in candidates]

        # 2. Pull the most recent send for each candidate.
        sends_resp = (
            self._client.table("outreach_send_log")
            .select("contact_id, sent_at")
            .in_("contact_id", contact_ids)
            .execute()
        )
        # Group by contact_id, keep max sent_at.
        latest_send: dict[str, str] = {}
        for row in sends_resp.data or []:
            cid = row["contact_id"]
            sa = row.get("sent_at") or ""
            if cid not in latest_send or sa > latest_send[cid]:
                latest_send[cid] = sa

        # 3. Replies for any of these contacts → exclude.
        replies_resp = (
            self._client.table("outreach_reply")
            .select("contact_id")
            .in_("contact_id", contact_ids)
            .execute()
        )
        replied = {row["contact_id"] for row in (replies_resp.data or [])}

        # 4. Filter: send is old enough AND not replied.
        idle_threshold_iso = self._iso_n_days_ago(now, idle_days)
        out: list[CoolOffContactRef] = []
        for c in candidates:
            cid = c["id"]
            if cid in replied:
                continue
            send_at = latest_send.get(cid)
            if not send_at or send_at > idle_threshold_iso:
                continue
            out.append(
                CoolOffContactRef(
                    contact_id=cid,
                    sequence_round=c.get("sequence_round") or 1,
                    client_id=c["client_id"],
                )
            )
        return out

    async def find_contacts_ready_to_re_enter(
        self, client_id: str, *, now: datetime,
    ) -> list[CoolOffContactRef]:
        resp = (
            self._client.table("contacts")
            .select("id, client_id, status, sequence_round, cool_off_until")
            .eq("client_id", client_id)
            .eq("status", "cooling_off")
            .execute()
        )
        out: list[CoolOffContactRef] = []
        now_iso = now.isoformat()
        for row in resp.data or []:
            cool_off_until = row.get("cool_off_until")
            if not cool_off_until or cool_off_until > now_iso:
                continue
            out.append(
                CoolOffContactRef(
                    contact_id=row["id"],
                    sequence_round=row.get("sequence_round") or 1,
                    client_id=row["client_id"],
                )
            )
        return out

    async def mark_contact_cooling_off(
        self, contact_id: str, *, cool_off_until: datetime,
    ) -> None:
        (
            self._client.table("contacts")
            .update(
                {
                    "status": "cooling_off",
                    "cool_off_until": cool_off_until.isoformat(),
                }
            )
            .eq("id", contact_id)
            .execute()
        )

    async def transition_to_next_round(
        self, contact_id: str, *, new_round: int,
    ) -> None:
        (
            self._client.table("contacts")
            .update(
                {
                    "status": "ready",
                    "sequence_round": new_round,
                    "cool_off_until": None,
                }
            )
            .eq("id", contact_id)
            .execute()
        )

    async def mark_contact_dead(
        self, contact_id: str, *, reason: str,
    ) -> None:
        # Read-modify-write to preserve existing raw_data fields.
        resp = (
            self._client.table("contacts")
            .select("raw_data")
            .eq("id", contact_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        raw_data = (rows[0].get("raw_data") if rows else None) or {}
        raw_data["dead_reason"] = reason

        (
            self._client.table("contacts")
            .update({"status": "dead", "raw_data": raw_data})
            .eq("id", contact_id)
            .execute()
        )

    @staticmethod
    def _iso_n_days_ago(now: datetime, days: int) -> str:
        from datetime import timedelta
        return (now - timedelta(days=days)).isoformat()
