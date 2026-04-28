"""Beacon ESP webhook event handler.

Plan 2 Phase 2 Task 2.2.4. Dispatches Instantly v2 webhook events:

- Status-changing events (sent / bounced / deferred / failed / complained)
  → update ``outreach_send_log.status`` + emit ``decision_log`` row
  with ``decision_type='send_event'``.
- Engagement events (opened / link_clicked) → structlog only. No DB
  write, no decision_log emit. Engagement timeline can be reconstructed
  from the ``outreach_send_log.raw_data`` archive if needed; keeping
  these out of decision_log preserves signal-to-noise.
- Reply events (reply_received) → insert ``outreach_reply`` row + emit
  ``decision_log`` row with ``decision_type='reply_received'``. Phase 3's
  classifier picks up unclassified replies via the
  ``idx_reply_pending_classification`` partial index.
- Anything else → ``UNKNOWN_EVENT``, acknowledged with no DB write
  (webhook receivers must be idempotent + tolerant of new event types
  that the ESP may add over time).

Module structure mirrors ``send_stage.py``:
- Protocols (``BeaconWebhookBackend``, ``DecisionLogger``) for DI.
- Dataclasses (``SendLogRef``) for typed return values.
- Enum (``WebhookEventResult``) for handler verdicts.
- ``WebhookHandler`` class — single ``handle(payload)`` entry point.

Real Supabase backend impl lives at
``systems/beacon/storage/webhook_supabase_backend.py`` (separate module,
lands with the router wiring).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import structlog


log = structlog.get_logger(__name__)


# --------------------------------------------------------------------------- #
# Result enum                                                                 #
# --------------------------------------------------------------------------- #


class WebhookEventResult(str, Enum):
    """Verdict emitted per webhook event after dispatch."""

    UPDATED = "updated"
    """Status-changing event correlated to a send_log row + status updated."""

    REPLY_INSERTED = "reply_inserted"
    """reply_received event inserted into outreach_reply."""

    LOGGED_NO_STATE_CHANGE = "logged_no_state_change"
    """Engagement event (open/click) — no DB write."""

    ORPHAN = "orphan"
    """ESP sent a reference to a message_id we don't have a send_log for.
    No DB write; webhook acknowledged."""

    UNKNOWN_EVENT = "unknown_event"
    """Event type not in the known set, or required field missing.
    No DB write; webhook acknowledged so the ESP doesn't retry."""


# --------------------------------------------------------------------------- #
# Dataclasses                                                                 #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SendLogRef:
    """Minimal projection of an outreach_send_log row needed for webhook
    correlation. Backend looks this up by ``esp_message_id``."""

    send_log_id: str
    contact_id: str
    client_id: str


# --------------------------------------------------------------------------- #
# Protocols                                                                   #
# --------------------------------------------------------------------------- #


class BeaconWebhookBackend(Protocol):
    async def find_send_log_by_esp_message_id(
        self, esp_message_id: str
    ) -> SendLogRef | None: ...

    async def update_send_log_status(
        self,
        send_log_id: str,
        status: str,
        error: str | None,
        raw_data: dict,
    ) -> None: ...

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
    ) -> str: ...


class DecisionLogger(Protocol):
    async def emit(
        self,
        *,
        client_id: str,
        decision_type: str,
        contact_id: str,
        payload: dict,
    ) -> None: ...


# --------------------------------------------------------------------------- #
# Event-type → status mapping                                                 #
# --------------------------------------------------------------------------- #


_STATUS_EVENTS: dict[str, str] = {
    "email_sent": "sent",
    "email_bounced": "bounced",
    "email_deferred": "deferred",
    "email_failed": "failed",
    "email_complained": "complained",
}

_ENGAGEMENT_EVENTS: frozenset[str] = frozenset({"email_opened", "email_link_clicked"})


def _extract_error(payload: dict) -> str | None:
    """Pull a human-readable error from the event payload. Instantly uses
    ``bounce_reason`` for bounces and ``error`` for SMTP failures."""
    return payload.get("bounce_reason") or payload.get("error")


# --------------------------------------------------------------------------- #
# Handler                                                                     #
# --------------------------------------------------------------------------- #


class WebhookHandler:
    def __init__(
        self,
        *,
        backend: BeaconWebhookBackend,
        decision_logger: DecisionLogger,
    ):
        self._backend = backend
        self._logger = decision_logger

    async def handle(self, payload: dict) -> WebhookEventResult:
        event_type = payload.get("event_type")
        if not event_type:
            log.warning("beacon.webhook.missing_event_type", payload=payload)
            return WebhookEventResult.UNKNOWN_EVENT

        if event_type in _STATUS_EVENTS:
            return await self._handle_status_event(event_type, payload)

        if event_type in _ENGAGEMENT_EVENTS:
            log.info(
                "beacon.webhook.engagement_event",
                event_type=event_type,
                message_id=payload.get("message_id"),
            )
            return WebhookEventResult.LOGGED_NO_STATE_CHANGE

        if event_type == "reply_received":
            return await self._handle_reply_event(payload)

        log.info("beacon.webhook.unknown_event_type", event_type=event_type)
        return WebhookEventResult.UNKNOWN_EVENT

    async def _handle_status_event(
        self, event_type: str, payload: dict
    ) -> WebhookEventResult:
        message_id = payload.get("message_id")
        if not message_id:
            log.warning(
                "beacon.webhook.status_event_missing_message_id",
                event_type=event_type,
            )
            return WebhookEventResult.UNKNOWN_EVENT

        ref = await self._backend.find_send_log_by_esp_message_id(message_id)
        if ref is None:
            log.warning(
                "beacon.webhook.orphan_status_event",
                event_type=event_type,
                message_id=message_id,
            )
            return WebhookEventResult.ORPHAN

        new_status = _STATUS_EVENTS[event_type]
        error = _extract_error(payload)

        await self._backend.update_send_log_status(
            send_log_id=ref.send_log_id,
            status=new_status,
            error=error,
            raw_data=payload,
        )
        await self._logger.emit(
            client_id=ref.client_id,
            decision_type="send_event",
            contact_id=ref.contact_id,
            payload={
                "event": event_type,
                "new_status": new_status,
                "send_log_id": ref.send_log_id,
                "error": error,
            },
        )
        return WebhookEventResult.UPDATED

    async def _handle_reply_event(self, payload: dict) -> WebhookEventResult:
        replied_to = payload.get("in_reply_to_message_id")
        # Reply correlation uses in_reply_to_message_id. Without a known
        # send_log, we can't determine client_id / contact_id, so the reply
        # is dropped (orphan). Phase 3 may revisit if this becomes
        # load-bearing — e.g. by looking up contact_id via lead_email.
        if not replied_to:
            log.warning("beacon.webhook.reply_missing_in_reply_to", payload=payload)
            return WebhookEventResult.ORPHAN

        ref = await self._backend.find_send_log_by_esp_message_id(replied_to)
        if ref is None:
            log.warning(
                "beacon.webhook.orphan_reply",
                in_reply_to_message_id=replied_to,
                lead_email=payload.get("lead_email"),
            )
            return WebhookEventResult.ORPHAN

        from_email = payload.get("lead_email", "")
        subject = payload.get("reply_subject")
        body = payload.get("reply_text") or payload.get("reply_html") or ""

        reply_id = await self._backend.insert_reply(
            client_id=ref.client_id,
            contact_id=ref.contact_id,
            send_log_id=ref.send_log_id,
            from_email=from_email,
            subject=subject,
            body=body,
            replied_to_message_id=replied_to,
            raw_data=payload,
        )
        await self._logger.emit(
            client_id=ref.client_id,
            decision_type="reply_received",
            contact_id=ref.contact_id,
            payload={
                "reply_id": reply_id,
                "send_log_id": ref.send_log_id,
                "from_email": from_email,
                "in_reply_to_message_id": replied_to,
            },
        )
        return WebhookEventResult.REPLY_INSERTED
