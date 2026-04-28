"""Beacon escalation runtime — human-attention queue + Slack notify.

Plan 2 Phase 3 Task 2.3.3. Replies that need human attention are
enqueued via this runtime:

  - ``low_confidence_reply`` — classifier returned confidence <0.7
  - ``cannot_classify_reply`` — classifier returned cannot_classify
  - ``auto_respond_failed`` — auto-respond runtime hit a skip / fail
    verdict (validator_failed / no_calendly_url / responder_error)
  - ``spam_marked_reply`` — recipient flagged the message as spam
  - ``out_of_office_reply`` — auto-reply received; needs operator note
  - ``manual_flag`` — operator hand-flagged via the inbox API

Operator triages via the inbox API (``api/routers/inbox.py``):
  - ``POST /api/inbox/escalations/{id}/resolve``
  - ``POST /api/inbox/escalations/{id}/dismiss``
  - ``GET  /api/inbox/escalations``  (list open for client)

Slack notification is best-effort: a Slack outage MUST NOT lose an
escalation. DB insert + decision_log emit fire first; Slack delivery
runs after and any exception is logged + swallowed.

When ``slack_notifier`` is ``None`` (e.g. SLACK_WEBHOOK_URL unset in
deployment), the runtime is silent on the Slack side — DB insert +
decision_log still fire normally.

Decision log: emits ``decision_type='reply_handling'`` with the
escalation_id + type in the payload. This reuses the existing
decision_type from migration 001 — no new migration needed.
"""
from __future__ import annotations

from typing import Protocol

import structlog


log = structlog.get_logger(__name__)


# Canonical escalation types — MUST match the CHECK constraint in
# scripts/sql/018_escalations.sql. Tests assert this in
# test_canonical_escalation_types_match_schema.
ESCALATION_TYPES: tuple[str, ...] = (
    "low_confidence_reply",
    "cannot_classify_reply",
    "auto_respond_failed",
    "spam_marked_reply",
    "out_of_office_reply",
    "manual_flag",
)
_VALID_TYPES = frozenset(ESCALATION_TYPES)


# --------------------------------------------------------------------------- #
# Protocols                                                                   #
# --------------------------------------------------------------------------- #


class EscalationBackend(Protocol):
    async def insert_escalation(
        self,
        *,
        client_id: str,
        contact_id: str,
        reply_id: str | None,
        escalation_type: str,
        summary: str,
        raw_data: dict,
    ) -> str: ...

    async def mark_resolved(
        self, escalation_id: str, *, resolved_by: str
    ) -> None: ...

    async def mark_dismissed(
        self, escalation_id: str, *, dismissed_by: str
    ) -> None: ...

    async def list_open(self, client_id: str) -> list[dict]: ...


class SlackNotifier(Protocol):
    async def notify(self, message: str) -> None: ...


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
# Slack message format                                                        #
# --------------------------------------------------------------------------- #


def _format_slack_message(
    *,
    client_id: str,
    contact_id: str,
    escalation_id: str,
    escalation_type: str,
    summary: str,
) -> str:
    """One-line-per-field Slack message. No emoji, no markdown, no fancy
    blocks — keep it parseable for both Slack's text webhook and a plain
    log tail."""
    return (
        f"Escalation [{escalation_type}] esc_id={escalation_id}\n"
        f"client={client_id} contact={contact_id}\n"
        f"summary: {summary}"
    )


# --------------------------------------------------------------------------- #
# Runtime                                                                     #
# --------------------------------------------------------------------------- #


class EscalationRuntime:
    def __init__(
        self,
        *,
        backend: EscalationBackend,
        decision_logger: DecisionLogger,
        slack_notifier: SlackNotifier | None = None,
    ) -> None:
        self._backend = backend
        self._logger = decision_logger
        self._slack = slack_notifier

    async def enqueue(
        self,
        *,
        client_id: str,
        contact_id: str,
        reply_id: str | None,
        escalation_type: str,
        summary: str,
        raw_data: dict,
    ) -> str:
        if escalation_type not in _VALID_TYPES:
            raise ValueError(
                f"unknown escalation_type {escalation_type!r}; "
                f"must be one of {sorted(_VALID_TYPES)}"
            )

        escalation_id = await self._backend.insert_escalation(
            client_id=client_id,
            contact_id=contact_id,
            reply_id=reply_id,
            escalation_type=escalation_type,
            summary=summary,
            raw_data=raw_data,
        )

        # decision_log fires next so the audit trail is preserved even
        # if Slack delivery fails downstream.
        await self._logger.emit(
            client_id=client_id,
            decision_type="reply_handling",
            contact_id=contact_id,
            payload={
                "escalation_id": escalation_id,
                "escalation_type": escalation_type,
                "summary": summary,
                "reply_id": reply_id,
            },
        )

        # Slack: best-effort. Failure is logged + swallowed so a Slack
        # outage doesn't prevent escalations being recorded.
        if self._slack is not None:
            try:
                message = _format_slack_message(
                    client_id=client_id,
                    contact_id=contact_id,
                    escalation_id=escalation_id,
                    escalation_type=escalation_type,
                    summary=summary,
                )
                await self._slack.notify(message)
            except Exception:
                log.exception(
                    "beacon.escalation.slack_failed",
                    escalation_id=escalation_id,
                )

        return escalation_id

    async def resolve(self, escalation_id: str, *, resolved_by: str) -> None:
        await self._backend.mark_resolved(
            escalation_id, resolved_by=resolved_by
        )

    async def dismiss(self, escalation_id: str, *, dismissed_by: str) -> None:
        await self._backend.mark_dismissed(
            escalation_id, dismissed_by=dismissed_by
        )

    async def list_open(self, client_id: str) -> list[dict]:
        return await self._backend.list_open(client_id)
