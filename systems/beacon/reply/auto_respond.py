"""Auto-respond runtime — operator-template-driven reply automation.

Plan 2 Phase 3 Task 2.3.2. For each ``ClassifyResult`` with
``recommended_action == 'auto_respond'``, this runtime:

  1. Picks the operator-authored template for the classification
     (objection_pricing.md / objection_timing.md / objection_authority.md
     / objection_other.md / meeting_request.md / positive_interest.md).
  2. Fills placeholders from the contact + client_facts:
        {first_name}, {company}, {calendly_url}, {sender_name}.
  3. Validates the rendered body against the same banned-words /
     em-dash / diagnostic-phrase rules as the icebreaker adapter
     (URL bans + anti-stalker bans skipped — calendly URLs are
     legitimate here).
  4. Calls ``ReplyResponder.send_reply`` to dispatch as a thread
     follow-up.
  5. Emits ``decision_log`` entries: ``reply_classification`` (always,
     records the verdict) + ``send_attempt`` (only when actually
     sending or in dry_run for parity with the live path).

Verdicts:
  - ``sent`` — happy path, response_message_id set
  - ``skipped:auto_respond_disabled`` — runtime parked at the system level
    via ``auto_respond_enabled=False``. Per the 2026-04-28 manual-first
    directional decision: replies stay operator-handled until 30+
    {classifier_prediction, operator_reply, actual_outcome} triples per
    classification class show ≥80% classifier accuracy. Classifier
    output is still recorded as training signal for future promotion.
  - ``skipped:not_auto_respond`` — recommended_action != 'auto_respond'
  - ``skipped:no_template`` — classification has no matching template
  - ``skipped:no_calendly_url`` — meeting_request / positive_interest
    template references {calendly_url} but client_facts has none
  - ``skipped:validator_failed`` — banned word / em-dash in rendered body
  - ``skipped:dry_run`` — dry_run=True
  - ``failed:responder_error`` — adapter raised on send

Templates are operator-authored per ``feedback_copy_architecture``:
humans write them, AI fills placeholders only. Production templates
live at
``data/reference/sequences/<niche>/components/reply_responses/``.

Per-call cost: 0¢ (no LLM call — pure templating + send). Cost
discipline lives in the upstream classifier (Haiku, ~$0.0005/call).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import structlog

from systems.beacon.reply.classifier import ClassifyResult


log = structlog.get_logger(__name__)


# Mapping from classification → template file (relative to templates_dir).
# Classifications NOT in this map cannot be auto-responded to even if the
# classifier sets action=auto_respond — they fall through to skipped:no_template.
CLASSIFICATION_TO_TEMPLATE: dict[str, str] = {
    "objection_pricing": "objection_pricing.md",
    "objection_timing": "objection_timing.md",
    "objection_authority": "objection_authority.md",
    "objection_other": "objection_other.md",
    "meeting_request": "meeting_request.md",
    "positive_interest": "positive_interest.md",
}

# Templates that reference {calendly_url}. Skipped if client_facts
# doesn't carry one, since dropping into the body without a URL would
# leave the placeholder visible.
#
# objection_pricing joined this set per operator decision 2026-04-28:
# pricing replies redirect to a live call (per
# data/reference/frameworks/objection-handling.md "SELL THE MEETING,
# NOT THE PRODUCT"), and the redirect requires a Calendly URL. Without
# one, the runtime escalates to operator's manual queue instead of
# sending a broken-link email.
_CALENDLY_REQUIRED: frozenset[str] = frozenset(
    {"meeting_request", "positive_interest", "objection_pricing"}
)


# Verdict constants (mirror SendStage's prefix pattern for grouping in
# decision_log queries).
VERDICT_SENT = "sent"
VERDICT_SKIPPED_DISABLED = "skipped:auto_respond_disabled"
VERDICT_SKIPPED_NOT_AUTO_RESPOND = "skipped:not_auto_respond"
VERDICT_SKIPPED_NO_TEMPLATE = "skipped:no_template"
VERDICT_SKIPPED_NO_CALENDLY = "skipped:no_calendly_url"
VERDICT_SKIPPED_VALIDATOR_FAILED = "skipped:validator_failed"
VERDICT_SKIPPED_DRY_RUN = "skipped:dry_run"
VERDICT_FAILED_RESPONDER_ERROR = "failed:responder_error"


# --------------------------------------------------------------------------- #
# Result                                                                      #
# --------------------------------------------------------------------------- #


@dataclass
class AutoRespondResult:
    verdict: str
    reason: str
    rendered_body: str | None = None
    response_message_id: str | None = None


# --------------------------------------------------------------------------- #
# Protocols                                                                   #
# --------------------------------------------------------------------------- #


class ReplyResponder(Protocol):
    async def send_reply(
        self,
        *,
        in_reply_to_message_id: str,
        subject: str,
        body: str,
        from_email: str,
    ) -> str:
        """Send a reply within an existing email thread. Returns the
        ESP message_id of the response."""
        ...


class AutoRespondBackend(Protocol):
    async def fetch_contact(self, contact_id: str) -> dict | None: ...
    async def fetch_client_facts(self, client_id: str) -> dict: ...


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
# Validator — reuse icebreaker rules minus URL + anti-stalker bans            #
# --------------------------------------------------------------------------- #


def _validate_response_body(body: str) -> tuple[bool, str]:
    """Apply the writing rules to a rendered reply response.

    Reuses the regex from ``systems.scout.enrich.icebreaker_adapter``
    so banned words, em-dashes, and diagnostic phrases stay consistent
    across the icebreaker + reply-response surfaces.

    Skipped checks (vs the icebreaker validator):
      - URL fragments (calendly URLs are required for some classifications)
      - Anti-stalker phrases (irrelevant for replies)
    """
    from systems.scout.enrich.icebreaker_adapter import (
        _BANNED_CHARS,
        _BANNED_DIAGNOSTIC_PHRASES,
        _BANNED_WORDS_RE,
    )

    for ch in _BANNED_CHARS:
        if ch in body:
            return False, f"banned_char:{ch!r}"
    if _BANNED_WORDS_RE.search(body):
        match = _BANNED_WORDS_RE.search(body)
        return False, f"banned_word:{match.group(0) if match else '?'}"
    lower = body.lower()
    for phrase in _BANNED_DIAGNOSTIC_PHRASES:
        if phrase.lower() in lower:
            return False, f"banned_phrase:{phrase}"
    return True, "ok"


# --------------------------------------------------------------------------- #
# Runtime                                                                     #
# --------------------------------------------------------------------------- #


class AutoRespondRuntime:
    def __init__(
        self,
        *,
        responder: ReplyResponder,
        backend: AutoRespondBackend,
        decision_logger: DecisionLogger,
        templates_dir: Path,
        auto_respond_enabled: bool = False,
    ) -> None:
        self._responder = responder
        self._backend = backend
        self._logger = decision_logger
        self._templates_dir = Path(templates_dir)
        # Defaults to False per the 2026-04-28 manual-first decision: the
        # runtime stays parked until calibration evidence justifies
        # promotion. Production DI must opt-in explicitly via client_config.
        self._auto_respond_enabled = auto_respond_enabled

    async def respond(
        self,
        *,
        client_id: str,
        contact_id: str,
        in_reply_to_message_id: str,
        original_subject: str,
        classify_result: ClassifyResult,
        dry_run: bool = False,
    ) -> AutoRespondResult:
        # Always emit reply_classification — records what the classifier
        # decided, regardless of whether we end up auto-responding. The
        # prediction is training signal for any future autonomy promotion.
        await self._emit_classification(client_id, contact_id, classify_result)

        # Gate 0: system-level enablement. Per the 2026-04-28 manual-first
        # decision, the runtime parks at this gate until calibration
        # evidence (30+ {prediction, reply, outcome} triples per class with
        # ≥80% classifier accuracy) justifies promotion. Production DI
        # opts in via client_config; default is parked.
        if not self._auto_respond_enabled:
            return AutoRespondResult(
                verdict=VERDICT_SKIPPED_DISABLED,
                reason=(
                    "auto_respond_enabled=False — runtime parked at suggest "
                    "autonomy; reply routes to operator's manual queue"
                ),
            )

        # Gate 1: action must be auto_respond.
        if classify_result.recommended_action != "auto_respond":
            return AutoRespondResult(
                verdict=VERDICT_SKIPPED_NOT_AUTO_RESPOND,
                reason=(
                    f"recommended_action={classify_result.recommended_action} "
                    f"!= 'auto_respond'"
                ),
            )

        # Gate 2: classification must have a matching template.
        template_filename = CLASSIFICATION_TO_TEMPLATE.get(
            classify_result.classification
        )
        if not template_filename:
            return AutoRespondResult(
                verdict=VERDICT_SKIPPED_NO_TEMPLATE,
                reason=f"no template for classification={classify_result.classification!r}",
            )

        # Load contact + client_facts in parallel-ish (sequential but
        # both small).
        contact = await self._backend.fetch_contact(contact_id) or {}
        client_facts = await self._backend.fetch_client_facts(client_id) or {}

        # Gate 3: calendly-required templates need a URL.
        calendly_url = client_facts.get("calendly_url") or ""
        if (
            classify_result.classification in _CALENDLY_REQUIRED
            and not calendly_url
        ):
            return AutoRespondResult(
                verdict=VERDICT_SKIPPED_NO_CALENDLY,
                reason=(
                    "client_facts.calendly_url required for "
                    f"classification={classify_result.classification}"
                ),
            )

        # Render template.
        template_text = (self._templates_dir / template_filename).read_text()
        rendered = template_text.format(
            first_name=contact.get("first_name") or "",
            company=contact.get("company") or "",
            calendly_url=calendly_url,
            sender_name=client_facts.get("sender_name") or "",
        )

        # Gate 4: writing-rules validator.
        ok, reason = _validate_response_body(rendered)
        if not ok:
            log.warning(
                "beacon.auto_respond.validator_failed",
                contact_id=contact_id,
                reason=reason,
            )
            return AutoRespondResult(
                verdict=VERDICT_SKIPPED_VALIDATOR_FAILED,
                reason=f"validator: {reason}",
                rendered_body=rendered,
            )

        # Subject prefix.
        subject = original_subject if original_subject.lower().startswith(
            "re:"
        ) else f"Re: {original_subject}"

        from_email = contact.get("email") or ""

        # Gate 5: dry_run.
        if dry_run:
            await self._emit_send_attempt(
                client_id=client_id,
                contact_id=contact_id,
                in_reply_to_message_id=in_reply_to_message_id,
                response_message_id=None,
                rendered_body=rendered,
                dry_run=True,
            )
            return AutoRespondResult(
                verdict=VERDICT_SKIPPED_DRY_RUN,
                reason="dry_run=True",
                rendered_body=rendered,
            )

        # Live send.
        try:
            response_message_id = await self._responder.send_reply(
                in_reply_to_message_id=in_reply_to_message_id,
                subject=subject,
                body=rendered,
                from_email=from_email,
            )
        except Exception as exc:
            log.exception(
                "beacon.auto_respond.responder_error",
                contact_id=contact_id,
            )
            return AutoRespondResult(
                verdict=VERDICT_FAILED_RESPONDER_ERROR,
                reason=str(exc),
                rendered_body=rendered,
            )

        await self._emit_send_attempt(
            client_id=client_id,
            contact_id=contact_id,
            in_reply_to_message_id=in_reply_to_message_id,
            response_message_id=response_message_id,
            rendered_body=rendered,
            dry_run=False,
        )

        return AutoRespondResult(
            verdict=VERDICT_SENT,
            reason="ok",
            rendered_body=rendered,
            response_message_id=response_message_id,
        )

    async def _emit_classification(
        self, client_id: str, contact_id: str, result: ClassifyResult
    ) -> None:
        await self._logger.emit(
            client_id=client_id,
            decision_type="reply_classification",
            contact_id=contact_id,
            payload={
                "classification": result.classification,
                "confidence": result.confidence,
                "summary": result.summary,
                "recommended_action": result.recommended_action,
                "reason": result.reason,
            },
        )

    async def _emit_send_attempt(
        self,
        *,
        client_id: str,
        contact_id: str,
        in_reply_to_message_id: str,
        response_message_id: str | None,
        rendered_body: str,
        dry_run: bool,
    ) -> None:
        await self._logger.emit(
            client_id=client_id,
            decision_type="send_attempt",
            contact_id=contact_id,
            payload={
                "kind": "auto_respond",
                "in_reply_to_message_id": in_reply_to_message_id,
                "response_message_id": response_message_id,
                "dry_run": dry_run,
                "body_preview": rendered_body[:200],
            },
        )
