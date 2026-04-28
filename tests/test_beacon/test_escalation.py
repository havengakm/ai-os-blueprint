"""Plan 2 Phase 3 Task 2.3.3: EscalationRuntime tests.

Replies that need human attention land in the ``escalations`` table +
Slack notification (when configured). Operator triages, optionally
responds via web app, marks resolved via the inbox API.

EscalationRuntime guarantees:
- DB insert succeeds independently of Slack delivery (Slack is
  best-effort; a Slack outage must NOT lose an escalation).
- decision_log emit fires regardless of Slack.
- No Slack notifier configured → silent no-op (fail-clean).
- Slack notifier raises → log + continue (DB row already saved).
"""
from __future__ import annotations

import pytest

from systems.beacon.reply.escalation import (
    EscalationRuntime,
    ESCALATION_TYPES,
)


# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #


class FakeEscalationBackend:
    def __init__(self) -> None:
        self.inserted: list[dict] = []
        self.resolved: list[dict] = []
        self.dismissed: list[dict] = []

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
        eid = f"esc-{len(self.inserted) + 1}"
        self.inserted.append(
            {
                "id": eid,
                "client_id": client_id,
                "contact_id": contact_id,
                "reply_id": reply_id,
                "escalation_type": escalation_type,
                "summary": summary,
                "raw_data": raw_data,
            }
        )
        return eid

    async def mark_resolved(
        self, escalation_id: str, *, resolved_by: str
    ) -> None:
        self.resolved.append(
            {"escalation_id": escalation_id, "resolved_by": resolved_by}
        )

    async def mark_dismissed(
        self, escalation_id: str, *, dismissed_by: str
    ) -> None:
        self.dismissed.append(
            {"escalation_id": escalation_id, "dismissed_by": dismissed_by}
        )

    async def list_open(self, client_id: str) -> list[dict]:
        return [
            row for row in self.inserted if row["client_id"] == client_id
        ]


class FakeSlackNotifier:
    def __init__(self, *, raise_on_send: Exception | None = None) -> None:
        self._raise = raise_on_send
        self.calls: list[str] = []

    async def notify(self, message: str) -> None:
        if self._raise is not None:
            raise self._raise
        self.calls.append(message)


class FakeDecisionLogger:
    def __init__(self) -> None:
        self.emits: list[dict] = []

    async def emit(
        self,
        *,
        client_id: str,
        decision_type: str,
        contact_id: str,
        payload: dict,
    ) -> None:
        self.emits.append(
            {
                "client_id": client_id,
                "decision_type": decision_type,
                "contact_id": contact_id,
                "payload": payload,
            }
        )


def _runtime(*, backend=None, slack=None, logger=None):
    return EscalationRuntime(
        backend=backend or FakeEscalationBackend(),
        slack_notifier=slack,
        decision_logger=logger or FakeDecisionLogger(),
    )


# --------------------------------------------------------------------------- #
# Happy paths                                                                 #
# --------------------------------------------------------------------------- #


async def test_enqueue_creates_db_row():
    backend = FakeEscalationBackend()
    runtime = _runtime(backend=backend)

    eid = await runtime.enqueue(
        client_id="c1",
        contact_id="u1",
        reply_id="reply-1",
        escalation_type="cannot_classify_reply",
        summary="Reply was ambiguous; needs human triage.",
        raw_data={"body": "what?"},
    )
    assert eid == "esc-1"
    assert len(backend.inserted) == 1
    row = backend.inserted[0]
    assert row["client_id"] == "c1"
    assert row["contact_id"] == "u1"
    assert row["reply_id"] == "reply-1"
    assert row["escalation_type"] == "cannot_classify_reply"
    assert row["summary"] == "Reply was ambiguous; needs human triage."


async def test_enqueue_emits_decision_log():
    logger = FakeDecisionLogger()
    runtime = _runtime(logger=logger)

    await runtime.enqueue(
        client_id="c1",
        contact_id="u1",
        reply_id=None,
        escalation_type="auto_respond_failed",
        summary="Validator rejected rendered reply.",
        raw_data={},
    )
    assert len(logger.emits) == 1
    emit = logger.emits[0]
    assert emit["client_id"] == "c1"
    assert emit["decision_type"] == "reply_handling"
    assert emit["contact_id"] == "u1"
    assert emit["payload"]["escalation_type"] == "auto_respond_failed"


# --------------------------------------------------------------------------- #
# Slack                                                                       #
# --------------------------------------------------------------------------- #


async def test_enqueue_sends_slack_notification_when_notifier_configured():
    slack = FakeSlackNotifier()
    runtime = _runtime(slack=slack)

    await runtime.enqueue(
        client_id="c1",
        contact_id="u1",
        reply_id="reply-1",
        escalation_type="low_confidence_reply",
        summary="Reply confidence 0.4; needs review.",
        raw_data={},
    )
    assert len(slack.calls) == 1
    msg = slack.calls[0]
    # Slack message includes the type + summary so the operator can triage
    # without opening the web app.
    assert "low_confidence_reply" in msg
    assert "Reply confidence 0.4; needs review." in msg
    assert "c1" in msg
    assert "u1" in msg


async def test_enqueue_no_op_when_slack_notifier_not_configured():
    """When slack_notifier is None, DB insert + decision_log still fire."""
    backend = FakeEscalationBackend()
    logger = FakeDecisionLogger()
    runtime = _runtime(backend=backend, slack=None, logger=logger)

    await runtime.enqueue(
        client_id="c1",
        contact_id="u1",
        reply_id=None,
        escalation_type="cannot_classify_reply",
        summary="x",
        raw_data={},
    )
    assert len(backend.inserted) == 1
    assert len(logger.emits) == 1


async def test_slack_failure_does_not_block_db_insert():
    """Slack outage must not lose the escalation. DB row + decision_log
    still saved; Slack failure logged but swallowed."""
    backend = FakeEscalationBackend()
    slack = FakeSlackNotifier(raise_on_send=RuntimeError("slack 500"))
    logger = FakeDecisionLogger()
    runtime = _runtime(backend=backend, slack=slack, logger=logger)

    eid = await runtime.enqueue(
        client_id="c1",
        contact_id="u1",
        reply_id="reply-1",
        escalation_type="spam_marked_reply",
        summary="Recipient marked as spam.",
        raw_data={},
    )
    assert eid is not None
    assert len(backend.inserted) == 1
    assert len(logger.emits) == 1
    # Slack call was attempted but raised
    assert slack.calls == []


# --------------------------------------------------------------------------- #
# Resolve / dismiss                                                           #
# --------------------------------------------------------------------------- #


async def test_resolve_marks_db_row_resolved():
    backend = FakeEscalationBackend()
    runtime = _runtime(backend=backend)

    await runtime.resolve("esc-1", resolved_by="kirsten@aios.dev")

    assert backend.resolved == [
        {"escalation_id": "esc-1", "resolved_by": "kirsten@aios.dev"}
    ]


async def test_dismiss_marks_db_row_dismissed():
    backend = FakeEscalationBackend()
    runtime = _runtime(backend=backend)

    await runtime.dismiss("esc-1", dismissed_by="kirsten@aios.dev")

    assert backend.dismissed == [
        {"escalation_id": "esc-1", "dismissed_by": "kirsten@aios.dev"}
    ]


# --------------------------------------------------------------------------- #
# list_open                                                                   #
# --------------------------------------------------------------------------- #


async def test_list_open_returns_all_open_for_client():
    backend = FakeEscalationBackend()
    runtime = _runtime(backend=backend)

    await runtime.enqueue(
        client_id="c1", contact_id="u1", reply_id=None,
        escalation_type="manual_flag", summary="x", raw_data={},
    )
    await runtime.enqueue(
        client_id="c1", contact_id="u2", reply_id=None,
        escalation_type="manual_flag", summary="y", raw_data={},
    )
    await runtime.enqueue(
        client_id="c2", contact_id="u3", reply_id=None,
        escalation_type="manual_flag", summary="z", raw_data={},
    )

    open_for_c1 = await runtime.list_open("c1")
    assert len(open_for_c1) == 2
    assert all(r["client_id"] == "c1" for r in open_for_c1)


# --------------------------------------------------------------------------- #
# Validation                                                                  #
# --------------------------------------------------------------------------- #


async def test_enqueue_with_invalid_escalation_type_raises():
    runtime = _runtime()
    with pytest.raises(ValueError) as exc:
        await runtime.enqueue(
            client_id="c1", contact_id="u1", reply_id=None,
            escalation_type="not_a_real_type",
            summary="x", raw_data={},
        )
    assert "not_a_real_type" in str(exc.value)


def test_canonical_escalation_types_match_schema():
    """The Python ESCALATION_TYPES enum must match the migration 018
    CHECK constraint values, otherwise schema-valid escalations fail
    at the DB layer or vice versa."""
    expected = {
        "low_confidence_reply",
        "cannot_classify_reply",
        "auto_respond_failed",
        "spam_marked_reply",
        "out_of_office_reply",
        "manual_flag",
    }
    assert set(ESCALATION_TYPES) == expected
