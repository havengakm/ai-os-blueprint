"""Plan 2 Phase 2 Task 2.2.4: Beacon webhook router smoke tests.

These verify the FastAPI wiring of the webhook endpoint:

- Signature middleware is wired against ``settings.instantly_webhook_secret``.
- Endpoint dispatches the parsed JSON to a ``WebhookHandler`` instance
  pulled from the dependency container.
- Endpoint returns 200 + the handler's verdict on happy path.

Handler-side dispatch logic is exhaustively unit-tested in
``tests/test_beacon/test_webhook_handler.py``; this file only covers the
HTTP edge.
"""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from systems.beacon.pipeline.webhook_handler import (
    SendLogRef,
    WebhookEventResult,
    WebhookHandler,
)


def _hmac_hex(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


# --------------------------------------------------------------------------- #
# Fakes — same shape as the handler unit tests                                #
# --------------------------------------------------------------------------- #


class FakeWebhookBackend:
    def __init__(self, send_logs: dict[str, SendLogRef] | None = None):
        self._logs = send_logs or {}
        self.status_updates: list = []
        self.replies_inserted: list = []

    async def find_send_log_by_esp_message_id(self, esp_message_id):
        return self._logs.get(esp_message_id)

    async def update_send_log_status(self, send_log_id, status, error, raw_data):
        self.status_updates.append(
            {"send_log_id": send_log_id, "status": status, "error": error}
        )

    async def insert_reply(
        self,
        client_id,
        contact_id,
        send_log_id,
        from_email,
        subject,
        body,
        replied_to_message_id,
        raw_data,
    ):
        rid = f"reply-{len(self.replies_inserted) + 1}"
        self.replies_inserted.append(
            {"reply_id": rid, "from_email": from_email, "body": body}
        )
        return rid


class FakeDecisionLogger:
    def __init__(self):
        self.emits: list = []

    async def emit(self, *, client_id, decision_type, contact_id, payload):
        self.emits.append({"decision_type": decision_type, "payload": payload})


# --------------------------------------------------------------------------- #
# App fixture                                                                 #
# --------------------------------------------------------------------------- #


@pytest.fixture
def app_with_webhook_router(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("INSTANTLY_WEBHOOK_SECRET", "wh-secret")

    from config.settings import get_settings

    get_settings.cache_clear()

    from api.main import create_app
    from api.routers import beacon_webhooks

    backend = FakeWebhookBackend(
        send_logs={
            "msg-1": SendLogRef(
                send_log_id="log-1",
                contact_id="contact-1",
                client_id="client-1",
            )
        }
    )
    logger = FakeDecisionLogger()
    handler = WebhookHandler(backend=backend, decision_logger=logger)

    app = create_app()

    app.dependency_overrides[beacon_webhooks.get_webhook_handler] = lambda: handler
    return app, backend, logger


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #


def test_webhook_endpoint_accepts_signed_status_event(app_with_webhook_router):
    app, backend, logger = app_with_webhook_router
    client = TestClient(app)

    payload_bytes = json.dumps(
        {
            "event_type": "email_sent",
            "message_id": "msg-1",
            "lead_email": "alice@acme.com",
        }
    ).encode()
    signature = _hmac_hex(payload_bytes, "wh-secret")

    r = client.post(
        "/api/beacon/webhooks/instantly",
        content=payload_bytes,
        headers={
            "X-Webhook-Signature": signature,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200
    assert r.json() == {"result": WebhookEventResult.UPDATED.value}
    assert len(backend.status_updates) == 1
    assert backend.status_updates[0]["status"] == "sent"


def test_webhook_endpoint_rejects_bad_signature(app_with_webhook_router):
    app, backend, logger = app_with_webhook_router
    client = TestClient(app)

    payload = json.dumps({"event_type": "email_sent", "message_id": "msg-1"}).encode()

    r = client.post(
        "/api/beacon/webhooks/instantly",
        content=payload,
        headers={
            "X-Webhook-Signature": "deadbeef",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 401
    assert backend.status_updates == []
    assert logger.emits == []


def test_webhook_endpoint_dispatches_reply_event(app_with_webhook_router):
    app, backend, logger = app_with_webhook_router
    client = TestClient(app)

    payload = json.dumps(
        {
            "event_type": "reply_received",
            "in_reply_to_message_id": "msg-1",
            "lead_email": "alice@acme.com",
            "reply_subject": "Re: hi",
            "reply_text": "yes please",
        }
    ).encode()
    signature = _hmac_hex(payload, "wh-secret")

    r = client.post(
        "/api/beacon/webhooks/instantly",
        content=payload,
        headers={
            "X-Webhook-Signature": signature,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200
    assert r.json() == {"result": WebhookEventResult.REPLY_INSERTED.value}
    assert len(backend.replies_inserted) == 1
    assert backend.replies_inserted[0]["from_email"] == "alice@acme.com"
    assert len(logger.emits) == 1
    assert logger.emits[0]["decision_type"] == "reply_received"


def test_webhook_endpoint_acknowledges_unknown_event_with_200(
    app_with_webhook_router,
):
    """ESPs add new event types over time; the receiver must not 500
    on unknown events. Acknowledge with 200 + UNKNOWN_EVENT verdict."""
    app, backend, logger = app_with_webhook_router
    client = TestClient(app)

    payload = json.dumps(
        {"event_type": "campaign_completed", "campaign_id": "camp-1"}
    ).encode()
    signature = _hmac_hex(payload, "wh-secret")

    r = client.post(
        "/api/beacon/webhooks/instantly",
        content=payload,
        headers={
            "X-Webhook-Signature": signature,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200
    assert r.json() == {"result": WebhookEventResult.UNKNOWN_EVENT.value}
