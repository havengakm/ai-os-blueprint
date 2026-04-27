"""Plan 2 Phase 3 Task 2.3.1: Haiku reply classifier tests.

The classifier takes one inbound reply (subject, body, sender) and
returns a typed verdict:

  - classification ∈ {positive_interest, meeting_request,
    objection_pricing, objection_timing, objection_authority,
    objection_other, negative, unsubscribe, out_of_office, bounce,
    wrong_person, spam_marked, cannot_classify}
  - confidence ∈ [0, 1]
  - summary: 1-line human-readable
  - recommended_action ∈ {auto_respond, escalate_to_human, archive,
    add_to_dnd, wait_for_human_review}

Below-threshold confidence (<0.7) overrides any recommended_action to
``wait_for_human_review`` so escalation is the safe default.

Tests use a stub Anthropic client that returns canned JSON, so no
network calls + deterministic assertions on the mapping logic.
"""
from __future__ import annotations

import json

import pytest

from systems.beacon.reply.classifier import (
    ClassifyResult,
    ReplyClassifier,
)


# --------------------------------------------------------------------------- #
# Stub Anthropic client                                                       #
# --------------------------------------------------------------------------- #


class _StubMessage:
    def __init__(self, text: str) -> None:
        self.content = [type("Block", (), {"text": text, "type": "text"})()]
        self.stop_reason = "end_turn"
        self.usage = type("Usage", (), {"input_tokens": 100, "output_tokens": 50})()


class StubAnthropicClient:
    """Captures the create() call + returns a pre-canned JSON response."""

    def __init__(self, response_json: dict | str | Exception) -> None:
        self._response = response_json
        self.messages = self
        self.create_calls: list[dict] = []

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        if isinstance(self._response, dict):
            text = json.dumps(self._response)
        else:
            text = self._response
        return _StubMessage(text)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _classifier(response, *, with_api_key: bool = True, monkeypatch=None):
    if monkeypatch is not None:
        if with_api_key:
            monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        else:
            monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    stub = StubAnthropicClient(response)
    return ReplyClassifier(anthropic_client=stub), stub


# --------------------------------------------------------------------------- #
# Happy-path classification mapping                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "classification,reply_body,expected_action",
    [
        ("positive_interest", "Yes, I'm interested. Let's chat.", "auto_respond"),
        (
            "meeting_request",
            "Send me a calendar invite for Tue afternoon.",
            "auto_respond",
        ),
        ("objection_pricing", "Way too expensive for our team.", "auto_respond"),
        ("objection_timing", "Not now — circle back next quarter.", "auto_respond"),
        (
            "objection_authority",
            "I'm not the right person, talk to our COO.",
            "auto_respond",
        ),
        ("objection_other", "We've already got a vendor for this.", "auto_respond"),
        ("negative", "No thanks, not interested.", "archive"),
        ("unsubscribe", "Take me off your list. STOP.", "add_to_dnd"),
        (
            "out_of_office",
            "I am out of the office until 5/15.",
            "wait_for_human_review",
        ),
        ("bounce", "550 user unknown @ acme.com", "archive"),
        ("wrong_person", "I left Acme last year, please remove me.", "archive"),
        (
            "spam_marked",
            "[Marked as spam by recipient]",
            "wait_for_human_review",
        ),
        ("cannot_classify", "????", "escalate_to_human"),
    ],
)
async def test_classifier_returns_each_classification_value(
    classification, reply_body, expected_action, monkeypatch
):
    classifier, stub = _classifier(
        {
            "classification": classification,
            "confidence": 0.9,
            "summary": "deterministic test",
            "recommended_action": expected_action,
        },
        monkeypatch=monkeypatch,
    )
    result = await classifier.classify(
        subject="Re: hi",
        body=reply_body,
        from_email="contact@acme.com",
    )

    assert result.ok
    assert result.classification == classification
    assert result.confidence == 0.9
    assert result.recommended_action == expected_action
    assert result.summary == "deterministic test"
    assert result.reason == "ok"
    assert len(stub.create_calls) == 1


# --------------------------------------------------------------------------- #
# Confidence threshold escalation                                             #
# --------------------------------------------------------------------------- #


async def test_low_confidence_overrides_action_to_wait_for_human_review(monkeypatch):
    """Even when the model recommends auto_respond, low confidence
    forces escalation to human review."""
    classifier, _ = _classifier(
        {
            "classification": "objection_pricing",
            "confidence": 0.45,
            "summary": "ambiguous",
            "recommended_action": "auto_respond",
        },
        monkeypatch=monkeypatch,
    )
    result = await classifier.classify(
        subject="?",
        body="ambiguous reply text",
        from_email="x@y.com",
    )
    assert result.ok
    assert result.classification == "objection_pricing"
    assert result.confidence == 0.45
    assert result.recommended_action == "wait_for_human_review"
    assert "low_confidence" in result.reason


async def test_high_confidence_preserves_model_action(monkeypatch):
    classifier, _ = _classifier(
        {
            "classification": "positive_interest",
            "confidence": 0.95,
            "summary": "yes",
            "recommended_action": "auto_respond",
        },
        monkeypatch=monkeypatch,
    )
    result = await classifier.classify(
        subject="Re: hi", body="yes please", from_email="x@y.com"
    )
    assert result.recommended_action == "auto_respond"
    assert result.reason == "ok"


# --------------------------------------------------------------------------- #
# Skip paths (no Anthropic call)                                              #
# --------------------------------------------------------------------------- #


async def test_dry_run_skips_call(monkeypatch):
    classifier, stub = _classifier({"classification": "negative"}, monkeypatch=monkeypatch)
    result = await classifier.classify(
        subject="?", body="?", from_email="x@y.com", dry_run=True
    )
    assert not result.ok
    assert result.reason == "dry_run_skipped"
    assert result.classification == "cannot_classify"
    assert result.confidence == 0.0
    assert stub.create_calls == []


async def test_no_api_key_skips_call(monkeypatch):
    classifier, stub = _classifier(
        {"classification": "negative"},
        with_api_key=False,
        monkeypatch=monkeypatch,
    )
    result = await classifier.classify(
        subject="?", body="?", from_email="x@y.com",
    )
    assert not result.ok
    assert result.reason == "no_api_key"
    assert stub.create_calls == []


# --------------------------------------------------------------------------- #
# Parse-failure path                                                          #
# --------------------------------------------------------------------------- #


async def test_parse_failure_when_response_not_json(monkeypatch):
    classifier, _ = _classifier("not valid json at all", monkeypatch=monkeypatch)
    result = await classifier.classify(
        subject="?", body="?", from_email="x@y.com",
    )
    assert not result.ok
    assert result.reason == "parse_failed"
    assert result.classification == "cannot_classify"
    assert result.recommended_action == "wait_for_human_review"


async def test_parse_failure_on_invalid_classification_enum(monkeypatch):
    """Model hallucinated a classification not in the canonical set —
    fall back to cannot_classify + escalation."""
    classifier, _ = _classifier(
        {
            "classification": "super_interested",  # not in enum
            "confidence": 0.9,
            "summary": "x",
            "recommended_action": "auto_respond",
        },
        monkeypatch=monkeypatch,
    )
    result = await classifier.classify(
        subject="?", body="?", from_email="x@y.com",
    )
    assert not result.ok
    assert result.reason == "invalid_classification_enum"
    assert result.classification == "cannot_classify"
    assert result.recommended_action == "wait_for_human_review"


async def test_parse_succeeds_when_response_wrapped_in_code_fences(monkeypatch):
    """Defensive: Haiku occasionally wraps JSON in ```json ... ``` fences."""
    response_with_fence = (
        "```json\n"
        '{"classification": "negative", "confidence": 0.9, '
        '"summary": "no", "recommended_action": "archive"}\n'
        "```"
    )
    classifier, _ = _classifier(response_with_fence, monkeypatch=monkeypatch)
    result = await classifier.classify(
        subject="?", body="No thanks", from_email="x@y.com",
    )
    assert result.ok
    assert result.classification == "negative"


# --------------------------------------------------------------------------- #
# Prompt assembly                                                             #
# --------------------------------------------------------------------------- #


async def test_prompt_includes_reply_body_and_subject_and_sender(monkeypatch):
    classifier, stub = _classifier(
        {
            "classification": "negative",
            "confidence": 0.9,
            "summary": "x",
            "recommended_action": "archive",
        },
        monkeypatch=monkeypatch,
    )
    await classifier.classify(
        subject="Re: introduction",
        body="No thanks, not interested.",
        from_email="alice@acme.com",
    )
    call = stub.create_calls[0]
    # User message contains the reply context
    user_content = call["messages"][0]["content"]
    assert "Re: introduction" in user_content
    assert "No thanks, not interested." in user_content
    assert "alice@acme.com" in user_content
    # Model is Haiku per CLAUDE.md cost rules
    assert "haiku" in call["model"].lower()


async def test_classifier_uses_haiku_4_5_model(monkeypatch):
    classifier, stub = _classifier(
        {
            "classification": "negative",
            "confidence": 0.9,
            "summary": "x",
            "recommended_action": "archive",
        },
        monkeypatch=monkeypatch,
    )
    await classifier.classify(subject="?", body="no", from_email="x@y.com")
    assert stub.create_calls[0]["model"] == "claude-haiku-4-5-20251001"


# --------------------------------------------------------------------------- #
# Result type sanity                                                          #
# --------------------------------------------------------------------------- #


def test_classify_result_has_expected_fields():
    """Sanity test on the ClassifyResult dataclass shape."""
    r = ClassifyResult(
        ok=True,
        classification="negative",
        confidence=0.9,
        summary="no",
        recommended_action="archive",
        cost_cents=0,
        reason="ok",
    )
    assert r.ok
    assert r.classification == "negative"
