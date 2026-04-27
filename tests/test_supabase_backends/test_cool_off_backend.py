"""Tests for SupabaseCoolOffBackend.

Conforms to ``systems.beacon.reply.cool_off.CoolOffBackend``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from systems.beacon.storage.cool_off_supabase_backend import (
    SupabaseCoolOffBackend,
)
from tests.test_supabase_backends.fakes import FakeSupabaseClient


def _now() -> datetime:
    return datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# find_idle_contacts_for_cool_off                                              #
# --------------------------------------------------------------------------- #


async def test_find_idle_returns_sent_contacts_with_old_send_and_no_reply() -> None:
    """Three contacts:
    - u1: sent 100 days ago, no reply → eligible
    - u2: sent 10 days ago, no reply → too recent
    - u3: sent 100 days ago, has reply → already replied
    """
    now = _now()
    old = (now - timedelta(days=100)).isoformat()
    recent = (now - timedelta(days=10)).isoformat()

    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "client_id": "c1", "status": "sent", "sequence_round": 1},
                {"id": "u2", "client_id": "c1", "status": "sent", "sequence_round": 1},
                {"id": "u3", "client_id": "c1", "status": "sent", "sequence_round": 1},
            ],
            "outreach_send_log": [
                {"contact_id": "u1", "sent_at": old},
                {"contact_id": "u2", "sent_at": recent},
                {"contact_id": "u3", "sent_at": old},
            ],
            "outreach_reply": [
                {"contact_id": "u3"},
            ],
        }
    )
    backend = SupabaseCoolOffBackend(fake)
    refs = await backend.find_idle_contacts_for_cool_off(
        "c1", idle_days=90, now=now,
    )
    assert [r.contact_id for r in refs] == ["u1"]
    assert refs[0].sequence_round == 1
    assert refs[0].client_id == "c1"


async def test_find_idle_excludes_contacts_in_blocked_statuses() -> None:
    """DND / unsubscribed / dead / cooling_off contacts must not be
    re-cooled-off, even if their last send is old enough."""
    now = _now()
    old = (now - timedelta(days=100)).isoformat()

    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u-dnd", "client_id": "c1", "status": "dnd", "sequence_round": 1},
                {"id": "u-unsub", "client_id": "c1", "status": "unsubscribed", "sequence_round": 1},
                {"id": "u-dead", "client_id": "c1", "status": "dead", "sequence_round": 1},
                {"id": "u-cool", "client_id": "c1", "status": "cooling_off", "sequence_round": 1},
                {"id": "u-ok", "client_id": "c1", "status": "sent", "sequence_round": 1},
            ],
            "outreach_send_log": [
                {"contact_id": cid, "sent_at": old}
                for cid in ("u-dnd", "u-unsub", "u-dead", "u-cool", "u-ok")
            ],
            "outreach_reply": [],
        }
    )
    backend = SupabaseCoolOffBackend(fake)
    refs = await backend.find_idle_contacts_for_cool_off(
        "c1", idle_days=90, now=now,
    )
    assert [r.contact_id for r in refs] == ["u-ok"]


# --------------------------------------------------------------------------- #
# find_contacts_ready_to_re_enter                                              #
# --------------------------------------------------------------------------- #


async def test_find_ready_returns_cooling_off_contacts_past_until() -> None:
    now = _now()
    past = (now - timedelta(days=1)).isoformat()
    future = (now + timedelta(days=1)).isoformat()

    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "client_id": "c1", "status": "cooling_off",
                 "sequence_round": 1, "cool_off_until": past},
                {"id": "u2", "client_id": "c1", "status": "cooling_off",
                 "sequence_round": 2, "cool_off_until": future},
                {"id": "u3", "client_id": "c1", "status": "sent",
                 "sequence_round": 1, "cool_off_until": None},
            ]
        }
    )
    backend = SupabaseCoolOffBackend(fake)
    refs = await backend.find_contacts_ready_to_re_enter("c1", now=now)
    assert [r.contact_id for r in refs] == ["u1"]


# --------------------------------------------------------------------------- #
# mark_contact_cooling_off                                                     #
# --------------------------------------------------------------------------- #


async def test_mark_cooling_off_updates_status_and_cool_off_until() -> None:
    until = _now() + timedelta(days=90)
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "status": "sent", "cool_off_until": None,
                 "sequence_round": 1},
            ]
        }
    )
    backend = SupabaseCoolOffBackend(fake)
    await backend.mark_contact_cooling_off("u1", cool_off_until=until)
    row = fake.rows("contacts")[0]
    assert row["status"] == "cooling_off"
    assert row["cool_off_until"] == until.isoformat()


# --------------------------------------------------------------------------- #
# transition_to_next_round                                                     #
# --------------------------------------------------------------------------- #


async def test_transition_to_next_round_increments_and_clears_cool_off() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "status": "cooling_off", "sequence_round": 1,
                 "cool_off_until": _now().isoformat()},
            ]
        }
    )
    backend = SupabaseCoolOffBackend(fake)
    await backend.transition_to_next_round("u1", new_round=2)
    row = fake.rows("contacts")[0]
    assert row["status"] == "ready"
    assert row["sequence_round"] == 2
    assert row["cool_off_until"] is None


# --------------------------------------------------------------------------- #
# mark_contact_dead                                                            #
# --------------------------------------------------------------------------- #


async def test_mark_contact_dead_sets_status_and_records_reason() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "status": "cooling_off",
                 "raw_data": {"seeded": 1}},
            ]
        }
    )
    backend = SupabaseCoolOffBackend(fake)
    await backend.mark_contact_dead("u1", reason="max_rounds_reached")
    row = fake.rows("contacts")[0]
    assert row["status"] == "dead"
    assert row["raw_data"]["dead_reason"] == "max_rounds_reached"
    assert row["raw_data"]["seeded"] == 1
