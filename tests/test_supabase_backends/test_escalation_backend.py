"""Tests for SupabaseEscalationBackend.

Conforms to ``systems.beacon.reply.escalation.EscalationBackend``.
"""
from __future__ import annotations

from systems.beacon.storage.escalation_supabase_backend import (
    SupabaseEscalationBackend,
)
from tests.test_supabase_backends.fakes import FakeSupabaseClient


async def test_insert_escalation_persists_row_and_returns_id() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseEscalationBackend(fake)

    eid = await backend.insert_escalation(
        client_id="c1",
        contact_id="u1",
        reply_id="reply-1",
        escalation_type="cannot_classify_reply",
        summary="Reply was ambiguous; needs human triage.",
        raw_data={"body": "????"},
    )
    assert eid

    rows = fake.rows("escalations")
    assert len(rows) == 1
    row = rows[0]
    assert row["client_id"] == "c1"
    assert row["contact_id"] == "u1"
    assert row["reply_id"] == "reply-1"
    assert row["escalation_type"] == "cannot_classify_reply"
    assert row["summary"] == "Reply was ambiguous; needs human triage."
    assert row["status"] == "open"
    assert row["raw_data"]["body"] == "????"


async def test_insert_escalation_with_null_reply_id() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseEscalationBackend(fake)
    await backend.insert_escalation(
        client_id="c1",
        contact_id="u1",
        reply_id=None,
        escalation_type="manual_flag",
        summary="x",
        raw_data={},
    )
    assert fake.rows("escalations")[0]["reply_id"] is None


async def test_mark_resolved_updates_status_and_resolved_fields() -> None:
    fake = FakeSupabaseClient(
        tables={
            "escalations": [
                {
                    "id": "esc-1", "status": "open",
                    "resolved_at": None, "resolved_by": None,
                }
            ]
        }
    )
    backend = SupabaseEscalationBackend(fake)

    await backend.mark_resolved("esc-1", resolved_by="kirsten@aios.dev")

    row = fake.rows("escalations")[0]
    assert row["status"] == "resolved"
    assert row["resolved_by"] == "kirsten@aios.dev"
    assert row["resolved_at"] is not None  # set to NOW() in real impl


async def test_mark_dismissed_updates_status() -> None:
    fake = FakeSupabaseClient(
        tables={"escalations": [{"id": "esc-1", "status": "open"}]}
    )
    backend = SupabaseEscalationBackend(fake)

    await backend.mark_dismissed("esc-1", dismissed_by="kirsten@aios.dev")

    row = fake.rows("escalations")[0]
    assert row["status"] == "dismissed"
    assert row["resolved_by"] == "kirsten@aios.dev"


async def test_list_open_returns_only_open_escalations() -> None:
    fake = FakeSupabaseClient(
        tables={
            "escalations": [
                {"id": "esc-1", "client_id": "c1", "status": "open",
                 "summary": "open one"},
                {"id": "esc-2", "client_id": "c1", "status": "resolved",
                 "summary": "resolved one"},
                {"id": "esc-3", "client_id": "c2", "status": "open",
                 "summary": "other client"},
            ]
        }
    )
    backend = SupabaseEscalationBackend(fake)
    rows = await backend.list_open("c1")

    assert [r["id"] for r in rows] == ["esc-1"]
