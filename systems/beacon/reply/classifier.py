"""Reply classifier — Haiku-backed classification of inbound replies.

Plan 2 Phase 3 Task 2.3.1. Takes a single inbound reply (subject + body
+ from_email) and returns a typed verdict the auto-respond runtime
(Task 2.3.2) and the escalation queue (Task 2.3.3) consume.

Cost target: ~$0.0005 per call (Haiku, ~200 output tokens). Cost
column on the result is left at 0 — reply classification cost is
post-send and not part of the per-contact cost ceiling that gates
SendStage.

Confidence-threshold escalation: if the model's confidence is below
``CONFIDENCE_ESCALATE_THRESHOLD`` (0.7), the model's recommended_action
is overridden to ``wait_for_human_review`` and the result reason is
prefixed with ``low_confidence``. This is the "safe default" rule from
the Plan 2 doc — we never auto-respond on a verdict the model isn't
confident about.

Skip paths (no Anthropic call, ``ok=False``):
  - dry_run=True            → reason='dry_run_skipped'
  - ANTHROPIC_API_KEY unset → reason='no_api_key'

Failure paths (Anthropic called, parse / validation rejected):
  - reason='parse_failed'                — body wasn't parseable JSON
  - reason='invalid_classification_enum' — model hallucinated a label
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 250
CONFIDENCE_ESCALATE_THRESHOLD = 0.7

_PROMPT_PATH = Path(__file__).parent / "prompts" / "classify_reply.md"


VALID_CLASSIFICATIONS = frozenset(
    {
        "positive_interest", "meeting_request",
        "objection_pricing", "objection_timing",
        "objection_authority", "objection_other",
        "negative", "unsubscribe",
        "out_of_office", "bounce", "wrong_person", "spam_marked",
        "cannot_classify",
    }
)

VALID_ACTIONS = frozenset(
    {
        "auto_respond",
        "escalate_to_human",
        "archive",
        "add_to_dnd",
        "wait_for_human_review",
    }
)


_CODE_FENCE_OPEN_RE = re.compile(r"^\s*```(?:json)?\s*", re.IGNORECASE)
_CODE_FENCE_CLOSE_RE = re.compile(r"\s*```\s*$")


def _strip_code_fences(text: str) -> str:
    out = _CODE_FENCE_OPEN_RE.sub("", text)
    out = _CODE_FENCE_CLOSE_RE.sub("", out)
    return out.strip()


@dataclass
class ClassifyResult:
    """Single-reply classification verdict.

    ``ok`` is True only when the model returned a parseable, enum-valid
    response. All failure / skip paths return ``ok=False`` with a
    ``cannot_classify`` classification + ``wait_for_human_review`` action
    so callers always have a safe default to act on.
    """

    ok: bool
    classification: str
    confidence: float
    summary: str
    recommended_action: str
    cost_cents: int
    reason: str


def _failed(reason: str, *, classification: str = "cannot_classify",
            recommended_action: str = "wait_for_human_review") -> ClassifyResult:
    return ClassifyResult(
        ok=False,
        classification=classification,
        confidence=0.0,
        summary="",
        recommended_action=recommended_action,
        cost_cents=0,
        reason=reason,
    )


class ReplyClassifier:
    name: str = "reply_classifier"
    cost_cents_per_call: int = 0  # Haiku ~$0.0005 per call; rounds to 0c

    def __init__(self, *, anthropic_client: Any | None = None) -> None:
        self._anthropic_client = anthropic_client
        self._anthropic_provided = anthropic_client is not None
        self._prompt_template: str = _PROMPT_PATH.read_text()

    async def _ensure_anthropic_client(self) -> Any:
        if self._anthropic_client is None:
            from anthropic import AsyncAnthropic
            self._anthropic_client = AsyncAnthropic()
        return self._anthropic_client

    async def aclose(self) -> None:
        if self._anthropic_client is not None and not self._anthropic_provided:
            try:
                await self._anthropic_client.close()
            finally:
                self._anthropic_client = None

    async def classify(
        self,
        *,
        subject: str,
        body: str,
        from_email: str,
        dry_run: bool = False,
    ) -> ClassifyResult:
        if dry_run:
            return _failed("dry_run_skipped")

        if not os.environ.get("ANTHROPIC_API_KEY"):
            return _failed("no_api_key")

        client = await self._ensure_anthropic_client()
        prompt = self._prompt_template.format(
            subject=subject or "",
            from_email=from_email or "",
            body=body or "",
        )

        msg = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            text = msg.content[0].text
        except (AttributeError, IndexError):
            return _failed("parse_failed")

        try:
            data = json.loads(_strip_code_fences(text))
        except (json.JSONDecodeError, ValueError):
            return _failed("parse_failed")

        if not isinstance(data, dict):
            return _failed("parse_failed")

        classification = data.get("classification")
        if classification not in VALID_CLASSIFICATIONS:
            return _failed("invalid_classification_enum")

        action = data.get("recommended_action")
        if action not in VALID_ACTIONS:
            return _failed("invalid_action_enum")

        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            return _failed("parse_failed")

        summary = str(data.get("summary") or "")[:500]

        # Confidence-threshold escalation: low confidence forces
        # wait_for_human_review regardless of what the model recommended.
        reason = "ok"
        if confidence < CONFIDENCE_ESCALATE_THRESHOLD:
            action = "wait_for_human_review"
            reason = f"low_confidence:{confidence:.2f}"

        return ClassifyResult(
            ok=True,
            classification=classification,
            confidence=confidence,
            summary=summary,
            recommended_action=action,
            cost_cents=0,
            reason=reason,
        )
