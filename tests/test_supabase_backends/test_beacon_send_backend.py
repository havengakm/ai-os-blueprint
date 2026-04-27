"""Tests for SupabaseSendBackend — Beacon's real send-backend impl.

Conforms to ``systems.beacon.pipeline.send_stage.SendBackend``.
Uses the same FakeSupabaseClient infra as the Scout backends so the
chainable Builder API is exercised the same way.
"""
from __future__ import annotations

from datetime import date

from systems.beacon.storage.send_supabase_backend import SupabaseSendBackend
from tests.test_supabase_backends.fakes import FakeSupabaseClient


# --------------------------------------------------------------------------- #
# fetch_eligible_contacts                                                     #
# --------------------------------------------------------------------------- #


async def test_fetch_eligible_contacts_returns_tier_ABC_with_drafts() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {
                    "id": "u1", "client_id": "c1", "email": "a@x.com",
                    "first_name": "Ada", "icp_tier": "A", "status": "rendered",
                    "research_data": {"trigger_events": ["funding"]},
                },
                {
                    "id": "u2", "client_id": "c1", "email": "b@x.com",
                    "first_name": "Bob", "icp_tier": "B", "status": "rendered",
                    "research_data": {},
                },
                {
                    "id": "u3", "client_id": "c1", "email": "d@x.com",
                    "first_name": "Dora", "icp_tier": "D", "status": "rendered",
                    "research_data": {},
                },
            ],
            "outreach_drafts": [
                {"id": "d1", "contact_id": "u1", "status": "rendered",
                 "subject": "Hi Ada", "body": "Body 1"},
                {"id": "d2", "contact_id": "u2", "status": "rendered",
                 "subject": "Hi Bob", "body": "Body 2"},
                {"id": "d3", "contact_id": "u3", "status": "rendered",
                 "subject": "Hi Dora", "body": "Body 3"},
            ],
            "outreach_send_log": [],
        }
    )
    backend = SupabaseSendBackend(fake)
    contacts = await backend.fetch_eligible_contacts("c1")

    ids = [c.contact_id for c in contacts]
    assert "u1" in ids and "u2" in ids
    assert "u3" not in ids  # tier D excluded


async def test_fetch_eligible_contacts_excludes_dnd_and_unsubscribed() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "client_id": "c1", "email": "a@x.com",
                 "first_name": "Ada", "icp_tier": "A", "status": "dnd",
                 "research_data": {}},
                {"id": "u2", "client_id": "c1", "email": "b@x.com",
                 "first_name": "Bob", "icp_tier": "A", "status": "unsubscribed",
                 "research_data": {}},
                {"id": "u3", "client_id": "c1", "email": "c@x.com",
                 "first_name": "Cara", "icp_tier": "A", "status": "rendered",
                 "research_data": {}},
            ],
            "outreach_drafts": [
                {"id": "d1", "contact_id": "u1", "status": "rendered",
                 "subject": "x", "body": "y"},
                {"id": "d2", "contact_id": "u2", "status": "rendered",
                 "subject": "x", "body": "y"},
                {"id": "d3", "contact_id": "u3", "status": "rendered",
                 "subject": "x", "body": "y"},
            ],
            "outreach_send_log": [],
        }
    )
    backend = SupabaseSendBackend(fake)
    contacts = await backend.fetch_eligible_contacts("c1")
    assert [c.contact_id for c in contacts] == ["u3"]


async def test_fetch_eligible_contacts_excludes_already_sent() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "client_id": "c1", "email": "a@x.com",
                 "first_name": "Ada", "icp_tier": "A", "status": "rendered",
                 "research_data": {}},
                {"id": "u2", "client_id": "c1", "email": "b@x.com",
                 "first_name": "Bob", "icp_tier": "A", "status": "rendered",
                 "research_data": {}},
            ],
            "outreach_drafts": [
                {"id": "d1", "contact_id": "u1", "status": "rendered",
                 "subject": "x", "body": "y"},
                {"id": "d2", "contact_id": "u2", "status": "rendered",
                 "subject": "x", "body": "y"},
            ],
            "outreach_send_log": [
                {"id": "log1", "client_id": "c1", "contact_id": "u1",
                 "status": "sent"},
            ],
        }
    )
    backend = SupabaseSendBackend(fake)
    contacts = await backend.fetch_eligible_contacts("c1")
    assert [c.contact_id for c in contacts] == ["u2"]


async def test_fetch_eligible_contacts_excludes_no_draft() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "client_id": "c1", "email": "a@x.com",
                 "first_name": "Ada", "icp_tier": "A", "status": "rendered",
                 "research_data": {}},
            ],
            "outreach_drafts": [],
            "outreach_send_log": [],
        }
    )
    backend = SupabaseSendBackend(fake)
    contacts = await backend.fetch_eligible_contacts("c1")
    assert contacts == []


async def test_fetch_eligible_contacts_sorts_signal_first_within_tier() -> None:
    """Within the same tier, signal-having contacts come first. Across
    tiers, A beats B beats C."""
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u-A-no-sig", "client_id": "c1", "email": "1@x.com",
                 "first_name": "X", "icp_tier": "A", "status": "rendered",
                 "research_data": {}},
                {"id": "u-A-sig", "client_id": "c1", "email": "2@x.com",
                 "first_name": "X", "icp_tier": "A", "status": "rendered",
                 "research_data": {"trigger_events": ["funding"]}},
                {"id": "u-B-sig", "client_id": "c1", "email": "3@x.com",
                 "first_name": "X", "icp_tier": "B", "status": "rendered",
                 "research_data": {"structural_signals": ["expansion"]}},
            ],
            "outreach_drafts": [
                {"id": "d1", "contact_id": "u-A-no-sig", "status": "rendered",
                 "subject": "x", "body": "y"},
                {"id": "d2", "contact_id": "u-A-sig", "status": "rendered",
                 "subject": "x", "body": "y"},
                {"id": "d3", "contact_id": "u-B-sig", "status": "rendered",
                 "subject": "x", "body": "y"},
            ],
            "outreach_send_log": [],
        }
    )
    backend = SupabaseSendBackend(fake)
    contacts = await backend.fetch_eligible_contacts("c1")
    assert [c.contact_id for c in contacts] == ["u-A-sig", "u-A-no-sig", "u-B-sig"]


async def test_fetch_eligible_contacts_respects_limit() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": f"u{i}", "client_id": "c1", "email": f"{i}@x.com",
                 "first_name": "X", "icp_tier": "A", "status": "rendered",
                 "research_data": {}}
                for i in range(5)
            ],
            "outreach_drafts": [
                {"id": f"d{i}", "contact_id": f"u{i}", "status": "rendered",
                 "subject": "x", "body": "y"}
                for i in range(5)
            ],
            "outreach_send_log": [],
        }
    )
    backend = SupabaseSendBackend(fake)
    contacts = await backend.fetch_eligible_contacts("c1", limit=2)
    assert len(contacts) == 2


# --------------------------------------------------------------------------- #
# fetch_active_send_accounts                                                  #
# --------------------------------------------------------------------------- #


async def test_fetch_active_send_accounts_filters_inactive() -> None:
    fake = FakeSupabaseClient(
        tables={
            "send_account": [
                {"id": "acc1", "client_id": "c1", "account_email": "a@x.com",
                 "provider": "instantly", "esp_account_id": "esp-1",
                 "daily_cap": 25, "is_active": True},
                {"id": "acc2", "client_id": "c1", "account_email": "b@x.com",
                 "provider": "instantly", "esp_account_id": "esp-2",
                 "daily_cap": 25, "is_active": False},
            ]
        }
    )
    backend = SupabaseSendBackend(fake)
    accounts = await backend.fetch_active_send_accounts("c1")
    assert [a.id for a in accounts] == ["acc1"]
    assert accounts[0].provider == "instantly"
    assert accounts[0].daily_cap == 25


# --------------------------------------------------------------------------- #
# get_account_sent_count_today                                                #
# --------------------------------------------------------------------------- #


async def test_get_account_sent_count_today_returns_existing_count() -> None:
    today = date(2026, 4, 27)
    fake = FakeSupabaseClient(
        tables={
            "send_caps_daily": [
                {"account_id": "acc1", "date": today.isoformat(), "sent_count": 7}
            ]
        }
    )
    backend = SupabaseSendBackend(fake)
    n = await backend.get_account_sent_count_today("acc1", today)
    assert n == 7


async def test_get_account_sent_count_today_returns_zero_when_no_row() -> None:
    today = date(2026, 4, 27)
    fake = FakeSupabaseClient(tables={"send_caps_daily": []})
    backend = SupabaseSendBackend(fake)
    n = await backend.get_account_sent_count_today("acc1", today)
    assert n == 0


# --------------------------------------------------------------------------- #
# increment_account_sent_count                                                #
# --------------------------------------------------------------------------- #


async def test_increment_account_sent_count_creates_row_if_absent() -> None:
    today = date(2026, 4, 27)
    fake = FakeSupabaseClient(tables={"send_caps_daily": []})
    backend = SupabaseSendBackend(fake)

    n = await backend.increment_account_sent_count("acc1", today)
    assert n == 1
    rows = fake.rows("send_caps_daily")
    assert rows[0]["account_id"] == "acc1"
    assert rows[0]["sent_count"] == 1


async def test_increment_account_sent_count_bumps_existing_row() -> None:
    today = date(2026, 4, 27)
    fake = FakeSupabaseClient(
        tables={
            "send_caps_daily": [
                {"account_id": "acc1", "date": today.isoformat(), "sent_count": 4}
            ]
        }
    )
    backend = SupabaseSendBackend(fake)
    n = await backend.increment_account_sent_count("acc1", today)
    assert n == 5
    assert fake.rows("send_caps_daily")[0]["sent_count"] == 5


# --------------------------------------------------------------------------- #
# get_contact_total_cost_cents                                                #
# --------------------------------------------------------------------------- #


async def test_get_contact_total_cost_cents_sums_decision_log_entries() -> None:
    fake = FakeSupabaseClient(
        tables={
            "decision_log": [
                {"context": {"contact_id": "u1", "cost_cents": 2}},
                {"context": {"contact_id": "u1", "cost_cents": 1}},
                {"context": {"contact_id": "u2", "cost_cents": 5}},
                {"context": {"contact_id": "u1"}},  # no cost field
                {"context": {}},  # unrelated entry
            ]
        }
    )
    backend = SupabaseSendBackend(fake)
    total = await backend.get_contact_total_cost_cents("u1")
    assert total == 3


async def test_get_contact_total_cost_cents_returns_zero_when_no_rows() -> None:
    fake = FakeSupabaseClient(tables={"decision_log": []})
    backend = SupabaseSendBackend(fake)
    total = await backend.get_contact_total_cost_cents("u1")
    assert total == 0


# --------------------------------------------------------------------------- #
# persist_send_log                                                            #
# --------------------------------------------------------------------------- #


async def test_persist_send_log_inserts_row_and_returns_id() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseSendBackend(fake)
    new_id = await backend.persist_send_log(
        client_id="c1",
        contact_id="u1",
        draft_id="d1",
        account_id="acc1",
        esp_message_id="msg-xyz",
        status="accepted",
        error=None,
        cost_cents=2,
    )
    assert new_id  # uuid string
    rows = fake.rows("outreach_send_log")
    assert len(rows) == 1
    row = rows[0]
    assert row["client_id"] == "c1"
    assert row["contact_id"] == "u1"
    assert row["draft_id"] == "d1"
    assert row["account_id"] == "acc1"
    assert row["esp_message_id"] == "msg-xyz"
    assert row["status"] == "accepted"
    assert row["error"] is None
    assert row["cost_cents"] == 2


# --------------------------------------------------------------------------- #
# update_draft_status                                                         #
# --------------------------------------------------------------------------- #


async def test_update_draft_status_writes_new_status() -> None:
    fake = FakeSupabaseClient(
        tables={
            "outreach_drafts": [
                {"id": "d1", "status": "rendered"},
                {"id": "d2", "status": "rendered"},
            ]
        }
    )
    backend = SupabaseSendBackend(fake)
    await backend.update_draft_status("d1", "sent")
    rows = {r["id"]: r["status"] for r in fake.rows("outreach_drafts")}
    assert rows["d1"] == "sent"
    assert rows["d2"] == "rendered"
