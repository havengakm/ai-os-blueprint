"""Smoke test: production reply-response templates pass the validator.

Catches the case where an operator edits a template and accidentally
introduces a banned word, em-dash, or diagnostic phrase. Runs against
the actual files in
``data/reference/sequences/creative_branding/components/reply_responses/``
so a bad commit fails CI.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from systems.beacon.reply.auto_respond import (
    AutoRespondRuntime,
    CLASSIFICATION_TO_TEMPLATE,
    VERDICT_SENT,
)
from systems.beacon.reply.classifier import ClassifyResult


PROD_TEMPLATES_DIR = Path(
    "data/reference/sequences/creative_branding/components/reply_responses"
)


class _Backend:
    async def fetch_contact(self, contact_id):
        return {
            "id": contact_id,
            "email": "alice@acme.com",
            "first_name": "Alice",
            "company": "Acme",
        }

    async def fetch_client_facts(self, client_id):
        return {
            "sender_name": "Kirsten",
            "calendly_url": "https://cal.com/kirsten/15min",
        }


class _Responder:
    def __init__(self):
        self.calls = []

    async def send_reply(self, **kwargs):
        self.calls.append(kwargs)
        return f"resp-{len(self.calls)}"


class _DecisionLogger:
    async def emit(self, **kwargs):
        pass


@pytest.mark.parametrize("classification", list(CLASSIFICATION_TO_TEMPLATE.keys()))
async def test_production_template_renders_and_validates(classification):
    """Every production template must render cleanly + pass the validator
    + result in a sent verdict against a representative sample contact."""
    if not PROD_TEMPLATES_DIR.exists():
        pytest.skip("production templates dir not present (deployment-specific)")

    responder = _Responder()
    runtime = AutoRespondRuntime(
        responder=responder,
        backend=_Backend(),
        decision_logger=_DecisionLogger(),
        templates_dir=PROD_TEMPLATES_DIR,
    )
    result = await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="introduction",
        classify_result=ClassifyResult(
            ok=True,
            classification=classification,
            confidence=0.9,
            summary="test",
            recommended_action="auto_respond",
            cost_cents=0,
            reason="ok",
        ),
    )
    assert result.verdict == VERDICT_SENT, (
        f"{classification}: verdict={result.verdict}, reason={result.reason}, "
        f"body={result.rendered_body!r}"
    )
    # Sanity: rendered body has placeholders filled
    body = responder.calls[0]["body"]
    assert "Alice" in body
    assert "{first_name}" not in body
    assert "{sender_name}" not in body
