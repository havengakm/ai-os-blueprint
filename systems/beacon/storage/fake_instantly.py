"""In-memory ``ESPAdapter`` implementation for tests.

Tests inject ``FakeInstantly`` instead of the real ``InstantlyAdapter``
to exercise the orchestrator + send-stage logic without HTTP calls.
Mirrors the FakeAnthropic / FakeBudgetTracker pattern used elsewhere
in the codebase.

Usage:
    fake = FakeInstantly()
    fake.replies_queue.append(Reply(...))
    result = await fake.fetch_replies_since(since=...)

Test assertions can read the state mutators directly:
    assert fake.leads_added == [...]
    assert fake.paused_accounts == [(esp_account_id, "high_bounce")]
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import uuid4

from systems.beacon.types import Reply, SendStats


class FakeInstantly:
    """In-memory ``ESPAdapter`` for tests.

    State mutators are public so tests can both observe call effects
    and pre-load responses (e.g. ``replies_queue``, ``stats_by_key``).
    """

    name: str = "fake-instantly"

    def __init__(self) -> None:
        # Public state — tests read + manipulate these.
        self.leads_added: list[dict[str, Any]] = []
        self.paused_accounts: list[tuple[str, str]] = []
        self.replies_queue: list[Reply] = []
        self.stats_by_key: dict[tuple[str, date], SendStats] = {}
        self.next_lead_id: int = 1

    async def add_lead_to_campaign(
        self,
        *,
        campaign_id: str,
        contact_email: str,
        contact_first_name: str,
        custom_subject: str,
        custom_body: str,
    ) -> str:
        lead_id = f"fake-lead-{self.next_lead_id:06d}"
        self.next_lead_id += 1
        self.leads_added.append({
            "campaign_id": campaign_id,
            "contact_email": contact_email,
            "contact_first_name": contact_first_name,
            "custom_subject": custom_subject,
            "custom_body": custom_body,
            "lead_id": lead_id,
        })
        return lead_id

    async def pause_account(
        self,
        *,
        esp_account_id: str,
        reason: str,
    ) -> None:
        self.paused_accounts.append((esp_account_id, reason))

    async def fetch_replies_since(
        self,
        *,
        since: datetime,
        limit: int = 100,
    ) -> list[Reply]:
        # Newest first, filtered to received_at >= since, capped at limit.
        matching = [r for r in self.replies_queue if r.received_at >= since]
        matching.sort(key=lambda r: r.received_at, reverse=True)
        return matching[:limit]

    async def get_send_stats(
        self,
        *,
        esp_account_id: str,
        on_date: date,
    ) -> SendStats:
        key = (esp_account_id, on_date)
        if key in self.stats_by_key:
            return self.stats_by_key[key]
        # Unknown account/date defaults to all-zero stats — mirrors how the
        # real Instantly endpoint returns zero counts for accounts with no
        # activity that day.
        return SendStats(
            esp_account_id=esp_account_id,
            on_date=on_date,
            sent_count=0,
            bounced_count=0,
            replied_count=0,
            open_rate=None,
        )
