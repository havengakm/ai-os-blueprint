"""SupabaseSendBackend — real persistence for SendStage.

Conforms to ``systems.beacon.pipeline.send_stage.SendBackend``.

The Supabase JS-flavoured SDK has no JOINs, so eligibility is computed
via three queries + Python assembly:

  1. ``contacts`` filtered to ``icp_tier ∈ {A,B,C}`` + non-blocked status.
  2. ``outreach_drafts`` for those contacts where ``status='rendered'``.
  3. ``outreach_send_log`` for those contacts (any status) — already-sent
     contacts are excluded.

Then in Python:

  - Drop contacts in any blocked status (DND / unsubscribed / dead /
    cooling_off / opted_out) — these statuses fail-loud rather than
    rely on the contacts query alone, so adding a new blocked status
    later is one place to edit.
  - Drop contacts without a rendered draft.
  - Drop contacts with any prior ``outreach_send_log`` row (any status).
    The send orchestrator never retries a sent / failed / bounced
    contact at this layer; cool-off + round-based re-entry is Plan 3.
  - Compute ``has_signal`` from ``research_data.trigger_events`` /
    ``structural_signals``.
  - Sort by (tier_order, has_signal DESC) — Tier A signal-having first,
    then Tier A no-signal, etc.

A future migration may ship a ``v_eligible_contacts`` Postgres VIEW
that pushes this down to SQL — for v1 the multi-query approach matches
how the Scout backends are structured and keeps the FakeSupabaseClient
test surface narrow.
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

from systems.beacon.pipeline.send_stage import EligibleContact, SendAccount
from aios.scout.supabase_backends._base import SupabaseLike


_ELIGIBLE_TIERS = ("A", "B", "C")
_BLOCKED_STATUSES = frozenset(
    {"dnd", "unsubscribed", "dead", "cooling_off", "opted_out"}
)
_TIER_ORDER = {"A": 0, "B": 1, "C": 2}


class SupabaseSendBackend:
    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def fetch_eligible_contacts(
        self, client_id: str, *, limit: int | None = None,
    ) -> list[EligibleContact]:
        contacts_resp = (
            self._client.table("contacts")
            .select("id, email, first_name, icp_tier, status, research_data")
            .eq("client_id", client_id)
            .in_("icp_tier", list(_ELIGIBLE_TIERS))
            .execute()
        )
        candidates = [
            c for c in (contacts_resp.data or [])
            if c.get("status") not in _BLOCKED_STATUSES
        ]
        if not candidates:
            return []

        contact_ids = [c["id"] for c in candidates]

        drafts_resp = (
            self._client.table("outreach_drafts")
            .select("id, contact_id, subject, body, status")
            .in_("contact_id", contact_ids)
            .eq("status", "rendered")
            .execute()
        )
        drafts_by_contact = {
            d["contact_id"]: d for d in (drafts_resp.data or [])
        }

        sent_resp = (
            self._client.table("outreach_send_log")
            .select("contact_id, status")
            .in_("contact_id", contact_ids)
            .execute()
        )
        already_sent_ids = {
            row["contact_id"] for row in (sent_resp.data or [])
        }

        out: list[EligibleContact] = []
        for c in candidates:
            if c["id"] in already_sent_ids:
                continue
            draft = drafts_by_contact.get(c["id"])
            if not draft:
                continue
            research = c.get("research_data") or {}
            has_signal = bool(
                research.get("trigger_events") or research.get("structural_signals")
            )
            out.append(
                EligibleContact(
                    contact_id=c["id"],
                    contact_email=c.get("email") or "",
                    contact_first_name=c.get("first_name") or "",
                    icp_tier=c["icp_tier"],
                    has_signal=has_signal,
                    draft_id=draft["id"],
                    draft_subject=draft.get("subject") or "",
                    draft_body=draft.get("body") or "",
                )
            )

        out.sort(key=lambda e: (_TIER_ORDER.get(e.icp_tier, 99), not e.has_signal))

        if limit is not None:
            out = out[:limit]
        return out

    async def fetch_active_send_accounts(
        self, client_id: str,
    ) -> list[SendAccount]:
        resp = (
            self._client.table("send_account")
            .select(
                "id, client_id, account_email, provider, esp_account_id, "
                "daily_cap, is_active"
            )
            .eq("client_id", client_id)
            .eq("is_active", True)
            .execute()
        )
        out: list[SendAccount] = []
        for row in resp.data or []:
            out.append(
                SendAccount(
                    id=row["id"],
                    account_email=row["account_email"],
                    provider=row["provider"],
                    esp_account_id=row.get("esp_account_id"),
                    daily_cap=row.get("daily_cap") or 0,
                    is_active=bool(row.get("is_active", False)),
                )
            )
        return out

    async def get_account_sent_count_today(
        self, account_id: str, on_date: date,
    ) -> int:
        resp = (
            self._client.table("send_caps_daily")
            .select("sent_count")
            .eq("account_id", account_id)
            .eq("date", on_date.isoformat())
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return 0
        return int(rows[0].get("sent_count") or 0)

    async def increment_account_sent_count(
        self, account_id: str, on_date: date,
    ) -> int:
        """Read-modify-write upsert. Production schema (migration 016)
        uses a composite PRIMARY KEY (account_id, date) so the upsert is
        atomic at the DB layer — Supabase's client-side upsert maps
        directly. The FakeSupabaseClient does not enforce the unique
        constraint, so the read-modify-write semantics are tested
        against its in-memory match-by-key behaviour."""
        current = await self.get_account_sent_count_today(account_id, on_date)
        new_count = current + 1
        (
            self._client.table("send_caps_daily")
            .upsert(
                {
                    "account_id": account_id,
                    "date": on_date.isoformat(),
                    "sent_count": new_count,
                },
                on_conflict="account_id,date",
            )
            .execute()
        )
        return new_count

    async def get_contact_total_cost_cents(
        self, contact_id: str,
    ) -> int:
        """Per-contact spend rollup.

        Calls the ``get_contact_cost(contact_id_param TEXT) RETURNS INTEGER``
        Postgres RPC (migration 020) which sums
        ``decision_log.context.cost_cents`` over rows where
        ``context.contact_id`` matches.

        The pre-Phase-4 v1 implementation was a Python full-table scan
        over decision_log; the RPC pushes that to SQL with the
        ``v_contact_cost_rollup`` view as the underlying engine.

        Returns 0 when the contact has no logged cost rows.
        """
        resp = (
            self._client
            .rpc("get_contact_cost", {"contact_id_param": contact_id})
            .execute()
        )
        # Real Supabase RPC returns the scalar in ``.data`` for scalar-
        # returning functions; FakeSupabaseClient mirrors this.
        value = resp.data
        if value is None:
            return 0
        if isinstance(value, list):  # defensive — some clients wrap scalars
            value = value[0] if value else 0
        return int(value)

    async def persist_send_log(
        self,
        *,
        client_id: str,
        contact_id: str,
        draft_id: str,
        account_id: str,
        esp_message_id: str | None,
        status: str,
        error: str | None,
        cost_cents: int,
    ) -> str:
        new_id = str(uuid4())
        (
            self._client.table("outreach_send_log")
            .insert(
                {
                    "id": new_id,
                    "client_id": client_id,
                    "contact_id": contact_id,
                    "draft_id": draft_id,
                    "account_id": account_id,
                    "esp_message_id": esp_message_id,
                    "status": status,
                    "error": error,
                    "cost_cents": cost_cents,
                }
            )
            .execute()
        )
        return new_id

    async def update_draft_status(
        self, draft_id: str, status: str,
    ) -> None:
        (
            self._client.table("outreach_drafts")
            .update({"status": status})
            .eq("id", draft_id)
            .execute()
        )
