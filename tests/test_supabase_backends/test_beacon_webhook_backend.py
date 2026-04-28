"""Tests for SupabaseWebhookBackend.

Conforms to ``systems.beacon.pipeline.webhook_handler.BeaconWebhookBackend``.
"""
from __future__ import annotations

from systems.beacon.pipeline.webhook_handler import SendLogRef
from systems.beacon.storage.webhook_supabase_backend import SupabaseWebhookBackend
from tests.test_supabase_backends.fakes import FakeSupabaseClient


# --------------------------------------------------------------------------- #
# find_send_log_by_esp_message_id                                              #
# --------------------------------------------------------------------------- #


async def test_find_send_log_returns_ref_when_present() -> None:
    fake = FakeSupabaseClient(
        tables={
            "outreach_send_log": [
                {"id": "log-1", "client_id": "c1", "contact_id": "u1",
                 "esp_message_id": "msg-1", "status": "accepted"},
            ]
        }
    )
    backend = SupabaseWebhookBackend(fake)
    ref = await backend.find_send_log_by_esp_message_id("msg-1")
    assert ref == SendLogRef(send_log_id="log-1", contact_id="u1", client_id="c1")


async def test_find_send_log_returns_none_when_absent() -> None:
    fake = FakeSupabaseClient(tables={"outreach_send_log": []})
    backend = SupabaseWebhookBackend(fake)
    ref = await backend.find_send_log_by_esp_message_id("msg-unknown")
    assert ref is None


# --------------------------------------------------------------------------- #
# update_send_log_status                                                       #
# --------------------------------------------------------------------------- #


async def test_update_send_log_status_writes_status_error_raw_data() -> None:
    fake = FakeSupabaseClient(
        tables={
            "outreach_send_log": [
                {"id": "log-1", "status": "accepted", "error": None,
                 "raw_data": {"seeded": 1}},
            ]
        }
    )
    backend = SupabaseWebhookBackend(fake)
    await backend.update_send_log_status(
        send_log_id="log-1",
        status="bounced",
        error="550 user unknown",
        raw_data={"event_type": "email_bounced", "bounce_reason": "550 user unknown"},
    )
    row = fake.rows("outreach_send_log")[0]
    assert row["status"] == "bounced"
    assert row["error"] == "550 user unknown"
    assert row["raw_data"]["event_type"] == "email_bounced"


# --------------------------------------------------------------------------- #
# insert_reply                                                                 #
# --------------------------------------------------------------------------- #


async def test_insert_reply_persists_row_and_returns_id() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseWebhookBackend(fake)
    reply_id = await backend.insert_reply(
        client_id="c1",
        contact_id="u1",
        send_log_id="log-1",
        from_email="alice@acme.com",
        subject="Re: hi",
        body="yes please",
        replied_to_message_id="msg-1",
        raw_data={"event_type": "reply_received"},
    )
    assert reply_id  # uuid string
    rows = fake.rows("outreach_reply")
    assert len(rows) == 1
    row = rows[0]
    assert row["client_id"] == "c1"
    assert row["contact_id"] == "u1"
    assert row["send_log_id"] == "log-1"
    assert row["from_email"] == "alice@acme.com"
    assert row["subject"] == "Re: hi"
    assert row["body"] == "yes please"
    assert row["replied_to_message_id"] == "msg-1"
    assert row["classification"] is None  # phase 3 fills this in


async def test_insert_reply_with_null_send_log_id_persists() -> None:
    """Orphan reply path — handler returns ORPHAN before calling this, but
    the backend must still tolerate a NULL send_log_id if a future caller
    chooses to persist orphans (e.g. for triage)."""
    fake = FakeSupabaseClient()
    backend = SupabaseWebhookBackend(fake)
    reply_id = await backend.insert_reply(
        client_id="c1",
        contact_id="u1",
        send_log_id=None,
        from_email="alice@acme.com",
        subject=None,
        body="orphan",
        replied_to_message_id=None,
        raw_data={},
    )
    assert reply_id
    row = fake.rows("outreach_reply")[0]
    assert row["send_log_id"] is None
    assert row["subject"] is None
    assert row["replied_to_message_id"] is None
