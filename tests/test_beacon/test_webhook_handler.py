"""Plan 2 Phase 2 Task 2.2.4: WebhookHandler unit tests.

Beacon webhook handler dispatches Instantly v2 webhook events:

  Status-changing events (update outreach_send_log.status + emit decision_log):
    email_sent       → status='sent'
    email_bounced    → status='bounced'
    email_deferred   → status='deferred'
    email_failed     → status='failed'
    email_complained → status='complained'

  Engagement events (no status change, structlog only — keep decision_log
  signal-to-noise high; engagement timeline can be reconstructed from
  outreach_send_log.raw_data archive):
    email_opened
    email_link_clicked

  Reply events (insert outreach_reply + emit decision_log):
    reply_received

  Anything else returns ``UNKNOWN_EVENT`` and is acknowledged with no DB
  write — webhooks must be idempotent at the receiver, and unknown event
  types should not 500 the endpoint (ESP can add new event types over time).
"""
from __future__ import annotations

import pytest

from systems.beacon.pipeline.webhook_handler import (
    WebhookHandler,
    WebhookEventResult,
    SendLogRef,
)


# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #


class FakeWebhookBackend:
    """In-memory backend mock — captures all Beacon webhook DB ops."""

    def __init__(
        self,
        send_logs_by_esp_id: dict[str, SendLogRef] | None = None,
    ):
        self._send_logs_by_esp_id = send_logs_by_esp_id or {}
        self.status_updates: list[dict] = []
        self.replies_inserted: list[dict] = []

    async def find_send_log_by_esp_message_id(
        self, esp_message_id: str
    ) -> SendLogRef | None:
        return self._send_logs_by_esp_id.get(esp_message_id)

    async def update_send_log_status(
        self,
        send_log_id: str,
        status: str,
        error: str | None,
        raw_data: dict,
    ) -> None:
        self.status_updates.append(
            {
                "send_log_id": send_log_id,
                "status": status,
                "error": error,
                "raw_data": raw_data,
            }
        )

    async def insert_reply(
        self,
        client_id: str,
        contact_id: str,
        send_log_id: str | None,
        from_email: str,
        subject: str | None,
        body: str,
        replied_to_message_id: str | None,
        raw_data: dict,
    ) -> str:
        reply_id = f"reply-{len(self.replies_inserted) + 1}"
        self.replies_inserted.append(
            {
                "reply_id": reply_id,
                "client_id": client_id,
                "contact_id": contact_id,
                "send_log_id": send_log_id,
                "from_email": from_email,
                "subject": subject,
                "body": body,
                "replied_to_message_id": replied_to_message_id,
                "raw_data": raw_data,
            }
        )
        return reply_id


class FakeDecisionLogger:
    """Captures emit calls for assertions."""

    def __init__(self):
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


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _backend_with_known_msg(esp_id: str = "msg-1") -> FakeWebhookBackend:
    return FakeWebhookBackend(
        send_logs_by_esp_id={
            esp_id: SendLogRef(
                send_log_id="log-1",
                contact_id="contact-1",
                client_id="client-1",
            )
        }
    )


def _make_handler(
    backend: FakeWebhookBackend, logger: FakeDecisionLogger | None = None
) -> tuple[WebhookHandler, FakeDecisionLogger]:
    logger = logger or FakeDecisionLogger()
    return WebhookHandler(backend=backend, decision_logger=logger), logger


# --------------------------------------------------------------------------- #
# Status-changing events                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_email_sent_updates_status_to_sent():
    backend = _backend_with_known_msg("msg-1")
    handler, logger = _make_handler(backend)

    payload = {
        "event_type": "email_sent",
        "message_id": "msg-1",
        "lead_email": "alice@acme.com",
        "campaign_id": "camp-1",
        "timestamp": "2026-04-27T12:00:00Z",
    }
    result = await handler.handle(payload)

    assert result == WebhookEventResult.UPDATED
    assert len(backend.status_updates) == 1
    update = backend.status_updates[0]
    assert update["send_log_id"] == "log-1"
    assert update["status"] == "sent"
    assert update["error"] is None
    assert update["raw_data"] == payload

    assert len(logger.emits) == 1
    emit = logger.emits[0]
    assert emit["decision_type"] == "send_event"
    assert emit["client_id"] == "client-1"
    assert emit["contact_id"] == "contact-1"
    assert emit["payload"]["event"] == "email_sent"
    assert emit["payload"]["new_status"] == "sent"


@pytest.mark.asyncio
async def test_email_bounced_updates_status_and_records_error():
    backend = _backend_with_known_msg("msg-1")
    handler, logger = _make_handler(backend)

    payload = {
        "event_type": "email_bounced",
        "message_id": "msg-1",
        "lead_email": "alice@acme.com",
        "bounce_reason": "550 5.1.1 user unknown",
    }
    result = await handler.handle(payload)

    assert result == WebhookEventResult.UPDATED
    update = backend.status_updates[0]
    assert update["status"] == "bounced"
    assert update["error"] == "550 5.1.1 user unknown"

    assert logger.emits[0]["payload"]["new_status"] == "bounced"


@pytest.mark.asyncio
async def test_email_deferred_updates_status_to_deferred():
    backend = _backend_with_known_msg("msg-1")
    handler, _ = _make_handler(backend)

    result = await handler.handle(
        {"event_type": "email_deferred", "message_id": "msg-1"}
    )

    assert result == WebhookEventResult.UPDATED
    assert backend.status_updates[0]["status"] == "deferred"


@pytest.mark.asyncio
async def test_email_failed_updates_status_to_failed():
    backend = _backend_with_known_msg("msg-1")
    handler, _ = _make_handler(backend)

    result = await handler.handle(
        {
            "event_type": "email_failed",
            "message_id": "msg-1",
            "error": "SMTP connection refused",
        }
    )

    assert result == WebhookEventResult.UPDATED
    update = backend.status_updates[0]
    assert update["status"] == "failed"
    assert update["error"] == "SMTP connection refused"


@pytest.mark.asyncio
async def test_email_complained_updates_status_to_complained():
    backend = _backend_with_known_msg("msg-1")
    handler, _ = _make_handler(backend)

    result = await handler.handle(
        {"event_type": "email_complained", "message_id": "msg-1"}
    )

    assert result == WebhookEventResult.UPDATED
    assert backend.status_updates[0]["status"] == "complained"


# --------------------------------------------------------------------------- #
# Engagement events (no status change, no decision_log emit)                  #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_email_opened_logs_no_state_change_no_decision_emit():
    backend = _backend_with_known_msg("msg-1")
    handler, logger = _make_handler(backend)

    result = await handler.handle(
        {"event_type": "email_opened", "message_id": "msg-1"}
    )

    assert result == WebhookEventResult.LOGGED_NO_STATE_CHANGE
    assert backend.status_updates == []
    assert logger.emits == []  # opens are noise; no decision_log entry


@pytest.mark.asyncio
async def test_email_link_clicked_logs_no_state_change_no_decision_emit():
    backend = _backend_with_known_msg("msg-1")
    handler, logger = _make_handler(backend)

    result = await handler.handle(
        {
            "event_type": "email_link_clicked",
            "message_id": "msg-1",
            "url": "https://example.com",
        }
    )

    assert result == WebhookEventResult.LOGGED_NO_STATE_CHANGE
    assert backend.status_updates == []
    assert logger.emits == []


# --------------------------------------------------------------------------- #
# Reply events                                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_reply_received_inserts_reply_and_emits_decision_log():
    backend = _backend_with_known_msg("msg-1")
    handler, logger = _make_handler(backend)

    payload = {
        "event_type": "reply_received",
        "in_reply_to_message_id": "msg-1",
        "lead_email": "alice@acme.com",
        "reply_subject": "Re: introduction",
        "reply_text": "Sounds interesting, can we chat next week?",
        "timestamp": "2026-04-27T13:00:00Z",
    }
    result = await handler.handle(payload)

    assert result == WebhookEventResult.REPLY_INSERTED
    assert backend.status_updates == []  # reply doesn't change send_log status
    assert len(backend.replies_inserted) == 1

    reply = backend.replies_inserted[0]
    assert reply["client_id"] == "client-1"
    assert reply["contact_id"] == "contact-1"
    assert reply["send_log_id"] == "log-1"
    assert reply["from_email"] == "alice@acme.com"
    assert reply["subject"] == "Re: introduction"
    assert reply["body"] == "Sounds interesting, can we chat next week?"
    assert reply["replied_to_message_id"] == "msg-1"
    assert reply["raw_data"] == payload

    assert len(logger.emits) == 1
    emit = logger.emits[0]
    assert emit["decision_type"] == "reply_received"
    assert emit["client_id"] == "client-1"
    assert emit["contact_id"] == "contact-1"
    assert emit["payload"]["from_email"] == "alice@acme.com"
    assert emit["payload"]["reply_id"] == "reply-1"


@pytest.mark.asyncio
async def test_reply_received_with_unknown_in_reply_to_inserts_orphan_reply():
    """A reply may arrive after a GC has dropped the send_log row, or the
    in_reply_to header may be absent. Insert the reply anyway so it lands in
    Phase 3's classification queue — but with send_log_id=None and contact_id
    looked up by lead_email instead. For now the safest thing is to skip
    the insert (no contact correlation) and return ORPHAN. Phase 3 can
    revisit if this becomes load-bearing."""
    backend = FakeWebhookBackend(send_logs_by_esp_id={})
    handler, logger = _make_handler(backend)

    payload = {
        "event_type": "reply_received",
        "in_reply_to_message_id": "msg-unknown",
        "lead_email": "stranger@nowhere.com",
        "reply_text": "Wrong person.",
    }
    result = await handler.handle(payload)

    assert result == WebhookEventResult.ORPHAN
    assert backend.replies_inserted == []
    assert logger.emits == []


# --------------------------------------------------------------------------- #
# Edge cases                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_unknown_esp_message_id_for_status_event_returns_orphan():
    """The send_log row may have been GC'd, or the message was sent
    out-of-band and never recorded. Don't 500 — return ORPHAN, no DB write."""
    backend = FakeWebhookBackend(send_logs_by_esp_id={})
    handler, logger = _make_handler(backend)

    result = await handler.handle(
        {"event_type": "email_sent", "message_id": "msg-unknown"}
    )

    assert result == WebhookEventResult.ORPHAN
    assert backend.status_updates == []
    assert logger.emits == []


@pytest.mark.asyncio
async def test_unknown_event_type_returns_unknown_no_crash():
    backend = _backend_with_known_msg("msg-1")
    handler, logger = _make_handler(backend)

    result = await handler.handle(
        {"event_type": "campaign_completed", "campaign_id": "camp-1"}
    )

    assert result == WebhookEventResult.UNKNOWN_EVENT
    assert backend.status_updates == []
    assert logger.emits == []


@pytest.mark.asyncio
async def test_missing_event_type_returns_unknown():
    backend = _backend_with_known_msg("msg-1")
    handler, _ = _make_handler(backend)

    result = await handler.handle({"message_id": "msg-1"})

    assert result == WebhookEventResult.UNKNOWN_EVENT


@pytest.mark.asyncio
async def test_status_event_missing_message_id_returns_unknown():
    """Without a message_id we can't correlate to outreach_send_log."""
    backend = _backend_with_known_msg("msg-1")
    handler, _ = _make_handler(backend)

    result = await handler.handle({"event_type": "email_sent"})

    assert result == WebhookEventResult.UNKNOWN_EVENT
    assert backend.status_updates == []


@pytest.mark.asyncio
async def test_reply_with_missing_body_uses_empty_string():
    """Some webhook providers strip the body in malformed events. Don't
    crash — insert with empty body so the classifier downstream can flag
    'cannot_classify' instead of dropping the reply silently."""
    backend = _backend_with_known_msg("msg-1")
    handler, _ = _make_handler(backend)

    result = await handler.handle(
        {
            "event_type": "reply_received",
            "in_reply_to_message_id": "msg-1",
            "lead_email": "alice@acme.com",
        }
    )

    assert result == WebhookEventResult.REPLY_INSERTED
    assert backend.replies_inserted[0]["body"] == ""
