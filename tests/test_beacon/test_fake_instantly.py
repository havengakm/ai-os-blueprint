"""Tests for the in-memory FakeInstantly adapter.

Validates that FakeInstantly satisfies the ESPAdapter Protocol contract
+ behaves correctly so tests in test_beacon/test_orchestrator.py (and
later phase tests) can rely on it.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from systems.beacon import ESPAdapter, FakeInstantly, Reply, SendStats


def test_fake_instantly_satisfies_espadapter_protocol():
    """Structural-typing check — FakeInstantly is recognised as an ESPAdapter."""
    fake: ESPAdapter = FakeInstantly()
    assert fake.name == "fake-instantly"


@pytest.mark.asyncio
async def test_add_lead_to_campaign_records_call_and_returns_lead_id():
    fake = FakeInstantly()
    lead_id = await fake.add_lead_to_campaign(
        campaign_id="camp-1",
        contact_email="alice@example.com",
        contact_first_name="Alice",
        custom_subject="thoughts Alice?",
        custom_body="Saw your work on X. Quick question.",
    )
    assert lead_id == "fake-lead-000001"
    assert len(fake.leads_added) == 1
    call = fake.leads_added[0]
    assert call["campaign_id"] == "camp-1"
    assert call["contact_email"] == "alice@example.com"
    assert call["contact_first_name"] == "Alice"
    assert call["custom_subject"] == "thoughts Alice?"
    assert call["custom_body"].startswith("Saw your work")
    assert call["lead_id"] == "fake-lead-000001"


@pytest.mark.asyncio
async def test_add_lead_to_campaign_increments_lead_id_per_call():
    fake = FakeInstantly()
    a = await fake.add_lead_to_campaign(
        campaign_id="c", contact_email="a@x.com", contact_first_name="A",
        custom_subject="s", custom_body="b",
    )
    b = await fake.add_lead_to_campaign(
        campaign_id="c", contact_email="b@x.com", contact_first_name="B",
        custom_subject="s", custom_body="b",
    )
    assert a == "fake-lead-000001"
    assert b == "fake-lead-000002"


@pytest.mark.asyncio
async def test_pause_account_records_reason():
    fake = FakeInstantly()
    await fake.pause_account(esp_account_id="acct-A", reason="bounce-rate-spike")
    assert fake.paused_accounts == [("acct-A", "bounce-rate-spike")]


@pytest.mark.asyncio
async def test_fetch_replies_since_returns_recent_only_and_newest_first():
    fake = FakeInstantly()
    now = datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    older = Reply(
        esp_message_id="r-old",
        replied_to_message_id="m-old",
        from_email="old@example.com",
        subject="Old",
        body="...",
        received_at=now - timedelta(hours=2),
    )
    newer = Reply(
        esp_message_id="r-new",
        replied_to_message_id="m-new",
        from_email="new@example.com",
        subject="New",
        body="...",
        received_at=now - timedelta(minutes=10),
    )
    really_new = Reply(
        esp_message_id="r-newest",
        replied_to_message_id="m-newest",
        from_email="newest@example.com",
        subject="Newest",
        body="...",
        received_at=now,
    )
    fake.replies_queue = [older, newer, really_new]

    result = await fake.fetch_replies_since(since=now - timedelta(hours=1))
    # Only newer + really_new match the cutoff (older is excluded).
    assert [r.esp_message_id for r in result] == ["r-newest", "r-new"]


@pytest.mark.asyncio
async def test_fetch_replies_since_respects_limit():
    fake = FakeInstantly()
    now = datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    for i in range(5):
        fake.replies_queue.append(
            Reply(
                esp_message_id=f"r-{i}",
                replied_to_message_id=None,
                from_email=f"x{i}@example.com",
                subject=None,
                body="...",
                received_at=now - timedelta(minutes=i),
            )
        )
    result = await fake.fetch_replies_since(since=now - timedelta(hours=1), limit=2)
    assert len(result) == 2
    # Newest first → r-0 then r-1.
    assert [r.esp_message_id for r in result] == ["r-0", "r-1"]


@pytest.mark.asyncio
async def test_get_send_stats_returns_default_zeros_for_unknown_account():
    fake = FakeInstantly()
    stats = await fake.get_send_stats(
        esp_account_id="never-seen", on_date=date(2026, 4, 27),
    )
    assert stats.esp_account_id == "never-seen"
    assert stats.sent_count == 0
    assert stats.bounced_count == 0
    assert stats.replied_count == 0
    assert stats.open_rate is None


@pytest.mark.asyncio
async def test_get_send_stats_returns_preloaded_value():
    fake = FakeInstantly()
    on_day = date(2026, 4, 27)
    fake.stats_by_key[("acct-A", on_day)] = SendStats(
        esp_account_id="acct-A",
        on_date=on_day,
        sent_count=18,
        bounced_count=1,
        replied_count=2,
        open_rate=0.55,
    )
    stats = await fake.get_send_stats(esp_account_id="acct-A", on_date=on_day)
    assert stats.sent_count == 18
    assert stats.bounced_count == 1
    assert stats.replied_count == 2
    assert stats.open_rate == pytest.approx(0.55)
