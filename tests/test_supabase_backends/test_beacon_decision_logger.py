"""Tests for SupabaseDecisionLogger.

The decision logger has two shapes — one for SendStage's DecisionLogger
Protocol (rich keyword args: decision_type / decision / reasoning /
context / source / confidence) and one for WebhookHandler's leaner
DecisionLogger Protocol (decision_type / contact_id / payload). Both
write to the same ``decision_log`` table.
"""
from __future__ import annotations

from systems.beacon.storage.decision_logger_supabase import (
    SupabaseDecisionLogger,
)
from tests.test_supabase_backends.fakes import FakeSupabaseClient


# --------------------------------------------------------------------------- #
# log_decision (SendStage shape)                                              #
# --------------------------------------------------------------------------- #


async def test_log_decision_writes_full_shape() -> None:
    fake = FakeSupabaseClient()
    logger = SupabaseDecisionLogger(fake)

    new_id = await logger.log_decision(
        "c1",
        decision_type="send_attempt",
        decision="sent",
        reasoning="autonomy=autonomous, cost ok, account room available",
        context={
            "contact_id": "u1",
            "send_log_id": "log-1",
            "cost_cents": 2,
        },
        source="beacon.send_stage",
        confidence=0.9,
    )
    assert new_id

    rows = fake.rows("decision_log")
    assert len(rows) == 1
    row = rows[0]
    assert row["client_id"] == "c1"
    assert row["decision_type"] == "send_attempt"
    assert row["decision"] == "sent"
    assert row["reasoning"] == "autonomy=autonomous, cost ok, account room available"
    assert row["context"]["contact_id"] == "u1"
    assert row["context"]["cost_cents"] == 2
    assert row["source"] == "beacon.send_stage"
    assert row["confidence"] == 0.9


async def test_log_decision_with_no_confidence_writes_null() -> None:
    fake = FakeSupabaseClient()
    logger = SupabaseDecisionLogger(fake)
    await logger.log_decision(
        "c1",
        decision_type="send_attempt",
        decision="skipped:cost_ceiling",
        reasoning="contact cost 6c >= 5c ceiling",
        context={"contact_id": "u1"},
        source="beacon.send_stage",
    )
    row = fake.rows("decision_log")[0]
    assert row["confidence"] is None


# --------------------------------------------------------------------------- #
# emit (WebhookHandler shape)                                                 #
# --------------------------------------------------------------------------- #


async def test_emit_writes_decision_log_row_with_payload_as_context() -> None:
    fake = FakeSupabaseClient()
    logger = SupabaseDecisionLogger(fake)

    await logger.emit(
        client_id="c1",
        decision_type="send_event",
        contact_id="u1",
        payload={
            "event": "email_bounced",
            "new_status": "bounced",
            "send_log_id": "log-1",
            "error": "550 user unknown",
        },
    )
    rows = fake.rows("decision_log")
    assert len(rows) == 1
    row = rows[0]
    assert row["client_id"] == "c1"
    assert row["decision_type"] == "send_event"
    assert row["context"]["contact_id"] == "u1"  # injected so cost-rollup queries find it
    assert row["context"]["event"] == "email_bounced"
    assert row["context"]["new_status"] == "bounced"
    assert row["source"] == "beacon.webhook_handler"


async def test_emit_decision_field_summarises_event_type() -> None:
    """The ``decision`` text column gives a quick human-readable summary
    when scanning decision_log rows; uses ``event`` field if present,
    falls back to ``decision_type``."""
    fake = FakeSupabaseClient()
    logger = SupabaseDecisionLogger(fake)

    await logger.emit(
        client_id="c1",
        decision_type="reply_received",
        contact_id="u1",
        payload={
            "reply_id": "reply-1",
            "send_log_id": "log-1",
            "from_email": "alice@acme.com",
            "in_reply_to_message_id": "msg-1",
        },
    )
    row = fake.rows("decision_log")[0]
    assert row["decision"] == "reply_received"  # falls back to decision_type
