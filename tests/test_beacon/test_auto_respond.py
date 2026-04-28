"""Plan 2 Phase 3 Task 2.3.2: AutoRespondRuntime tests.

Runtime takes a ``ClassifyResult`` + reply context, picks the operator-
authored template for the classification, fills placeholders, validates
the rendered body (banned words / em-dash / diagnostic phrases), and
sends via the injected ``ReplyResponder``.

Skip / failure verdicts:
- ``skipped:not_auto_respond`` — recommended_action != 'auto_respond'
- ``skipped:no_template`` — classification has no matching template
- ``skipped:no_calendly_url`` — meeting_request without client.calendly_url
- ``skipped:validator_failed`` — rendered body has banned words / em-dash
- ``skipped:dry_run`` — dry_run=True; decision_log still emits
- ``failed:responder_error`` — adapter raised on send

Decision log emits:
- ``reply_classification`` — once per call (records the verdict)
- ``send_attempt`` — only when an actual send occurs

Tests use ``tmp_path`` with seeded templates so each assertion is
isolated from the production template content.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from systems.beacon.reply.auto_respond import (
    AutoRespondBackend,
    AutoRespondRuntime,
    ReplyResponder,
)
from systems.beacon.reply.classifier import ClassifyResult


# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #


class FakeBackend:
    def __init__(
        self,
        contacts: dict[str, dict] | None = None,
        client_facts: dict[str, dict] | None = None,
    ) -> None:
        self._contacts = contacts or {}
        self._facts = client_facts or {}

    async def fetch_contact(self, contact_id: str) -> dict | None:
        return self._contacts.get(contact_id)

    async def fetch_client_facts(self, client_id: str) -> dict:
        return self._facts.get(client_id, {})


class FakeResponder:
    def __init__(self, *, raise_on_send: Exception | None = None) -> None:
        self._raise = raise_on_send
        self.calls: list[dict] = []

    async def send_reply(
        self,
        *,
        in_reply_to_message_id: str,
        subject: str,
        body: str,
        from_email: str,
    ) -> str:
        if self._raise is not None:
            raise self._raise
        self.calls.append(
            {
                "in_reply_to_message_id": in_reply_to_message_id,
                "subject": subject,
                "body": body,
                "from_email": from_email,
            }
        )
        return f"resp-msg-{len(self.calls)}"


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


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def templates_dir(tmp_path: Path) -> Path:
    """Seed a templates_dir with skeletons covering the 6 auto-respond
    classifications. Each template uses a distinct marker so tests can
    assert on rendering accuracy."""
    d = tmp_path / "reply_responses"
    d.mkdir()
    (d / "objection_pricing.md").write_text(
        "Hi {first_name},\n\n[PRICING] Got it. Tell me a budget for {company}.\n\n{sender_name}\n"
    )
    (d / "objection_timing.md").write_text(
        "Hi {first_name},\n\n[TIMING] Makes sense. When should I circle back?\n\n{sender_name}\n"
    )
    (d / "objection_authority.md").write_text(
        "Hi {first_name},\n\n[AUTHORITY] Thanks. Who's the right person?\n\n{sender_name}\n"
    )
    (d / "objection_other.md").write_text(
        "Hi {first_name},\n\n[OTHER] Got it, thanks for the context.\n\n{sender_name}\n"
    )
    (d / "meeting_request.md").write_text(
        "Hi {first_name},\n\n[MEETING] Yes, pick a time: {calendly_url}\n\n{sender_name}\n"
    )
    (d / "positive_interest.md").write_text(
        "Hi {first_name},\n\n[POSITIVE] Glad it landed. Pick a time: {calendly_url}\n\n{sender_name}\n"
    )
    return d


@pytest.fixture
def standard_backend() -> FakeBackend:
    return FakeBackend(
        contacts={
            "u1": {
                "id": "u1",
                "email": "alice@acme.com",
                "first_name": "Alice",
                "company": "Acme",
            }
        },
        client_facts={
            "c1": {
                "sender_name": "Kirsten",
                "calendly_url": "https://cal.com/kirsten/15min",
            }
        },
    )


def _make_runtime(templates_dir, backend, responder=None, logger=None):
    return AutoRespondRuntime(
        responder=responder or FakeResponder(),
        backend=backend,
        decision_logger=logger or FakeDecisionLogger(),
        templates_dir=templates_dir,
    )


def _classify(
    classification: str,
    *,
    confidence: float = 0.9,
    action: str = "auto_respond",
) -> ClassifyResult:
    return ClassifyResult(
        ok=True,
        classification=classification,
        confidence=confidence,
        summary="test",
        recommended_action=action,
        cost_cents=0,
        reason="ok",
    )


# --------------------------------------------------------------------------- #
# Skip: action != auto_respond                                                #
# --------------------------------------------------------------------------- #


async def test_skips_when_recommended_action_is_not_auto_respond(
    templates_dir, standard_backend
):
    responder = FakeResponder()
    logger = FakeDecisionLogger()
    runtime = _make_runtime(templates_dir, standard_backend, responder, logger)

    result = await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="hi",
        classify_result=_classify(
            "cannot_classify", action="wait_for_human_review"
        ),
    )

    assert result.verdict == "skipped:not_auto_respond"
    assert responder.calls == []
    # decision_log records the classification but not a send_attempt
    decision_types = [e["decision_type"] for e in logger.emits]
    assert "reply_classification" in decision_types
    assert "send_attempt" not in decision_types


# --------------------------------------------------------------------------- #
# Each template renders + sends                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "classification,marker",
    [
        ("objection_pricing", "[PRICING]"),
        ("objection_timing", "[TIMING]"),
        ("objection_authority", "[AUTHORITY]"),
        ("objection_other", "[OTHER]"),
        ("positive_interest", "[POSITIVE]"),
        ("meeting_request", "[MEETING]"),
    ],
)
async def test_renders_and_sends_per_classification(
    classification, marker, templates_dir, standard_backend
):
    responder = FakeResponder()
    logger = FakeDecisionLogger()
    runtime = _make_runtime(templates_dir, standard_backend, responder, logger)

    result = await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="introduction",
        classify_result=_classify(classification),
    )

    assert result.verdict == "sent"
    assert result.response_message_id == "resp-msg-1"
    assert len(responder.calls) == 1

    sent = responder.calls[0]
    assert marker in sent["body"]
    assert "Alice" in sent["body"]  # first_name placeholder filled
    assert sent["from_email"] == "alice@acme.com"
    assert sent["in_reply_to_message_id"] == "msg-1"
    assert sent["subject"] == "Re: introduction"


async def test_meeting_request_renders_calendly_url(
    templates_dir, standard_backend
):
    responder = FakeResponder()
    runtime = _make_runtime(templates_dir, standard_backend, responder)
    result = await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="hi",
        classify_result=_classify("meeting_request"),
    )
    assert result.verdict == "sent"
    assert "https://cal.com/kirsten/15min" in responder.calls[0]["body"]


async def test_meeting_request_skips_when_no_calendly_url(templates_dir):
    backend = FakeBackend(
        contacts={"u1": {"email": "alice@acme.com", "first_name": "Alice", "company": "Acme"}},
        client_facts={"c1": {"sender_name": "K"}},  # no calendly_url
    )
    responder = FakeResponder()
    runtime = _make_runtime(templates_dir, backend, responder)
    result = await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="hi",
        classify_result=_classify("meeting_request"),
    )
    assert result.verdict == "skipped:no_calendly_url"
    assert responder.calls == []


async def test_positive_interest_skips_when_no_calendly_url(templates_dir):
    """positive_interest also references calendly_url, so the same gate applies."""
    backend = FakeBackend(
        contacts={"u1": {"email": "alice@acme.com", "first_name": "Alice", "company": "Acme"}},
        client_facts={"c1": {"sender_name": "K"}},
    )
    responder = FakeResponder()
    runtime = _make_runtime(templates_dir, backend, responder)
    result = await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="hi",
        classify_result=_classify("positive_interest"),
    )
    assert result.verdict == "skipped:no_calendly_url"


async def test_objection_pricing_skips_when_no_calendly_url(templates_dir):
    """objection_pricing redirects to a live call per the objection-handling
    framework — the redirect requires a Calendly URL. Without one, the
    runtime skips to the operator's manual queue."""
    backend = FakeBackend(
        contacts={"u1": {"email": "alice@acme.com", "first_name": "Alice", "company": "Acme"}},
        client_facts={"c1": {"sender_name": "K"}},  # no calendly_url
    )
    responder = FakeResponder()
    runtime = _make_runtime(templates_dir, backend, responder)
    result = await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="hi",
        classify_result=_classify("objection_pricing"),
    )
    assert result.verdict == "skipped:no_calendly_url"
    assert responder.calls == []


# --------------------------------------------------------------------------- #
# Placeholders                                                                #
# --------------------------------------------------------------------------- #


async def test_renders_first_name_company_calendly_sender(
    templates_dir, standard_backend
):
    responder = FakeResponder()
    runtime = _make_runtime(templates_dir, standard_backend, responder)
    await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="hi",
        classify_result=_classify("objection_pricing"),
    )
    body = responder.calls[0]["body"]
    assert "Alice" in body  # first_name
    assert "Acme" in body  # company
    assert "Kirsten" in body  # sender_name


async def test_subject_is_prefixed_with_re_when_not_already(
    templates_dir, standard_backend
):
    responder = FakeResponder()
    runtime = _make_runtime(templates_dir, standard_backend, responder)
    await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="introduction",
        classify_result=_classify("objection_other"),
    )
    assert responder.calls[0]["subject"] == "Re: introduction"


async def test_subject_not_double_prefixed_when_already_re(
    templates_dir, standard_backend
):
    responder = FakeResponder()
    runtime = _make_runtime(templates_dir, standard_backend, responder)
    await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="Re: introduction",
        classify_result=_classify("objection_other"),
    )
    assert responder.calls[0]["subject"] == "Re: introduction"


# --------------------------------------------------------------------------- #
# Skip: no_template for unmapped classification                               #
# --------------------------------------------------------------------------- #


async def test_skips_when_classification_has_no_template(
    templates_dir, standard_backend
):
    """``negative`` / ``unsubscribe`` / ``out_of_office`` have no
    auto-respond template — classifier should have routed them elsewhere
    (archive / add_to_dnd / wait_for_human_review) but if action=auto_respond
    sneaks through, the runtime returns skipped:no_template."""
    responder = FakeResponder()
    runtime = _make_runtime(templates_dir, standard_backend, responder)
    result = await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="hi",
        classify_result=_classify("negative"),  # no template for negative
    )
    assert result.verdict == "skipped:no_template"
    assert responder.calls == []


# --------------------------------------------------------------------------- #
# Validator                                                                   #
# --------------------------------------------------------------------------- #


async def test_validator_failure_blocks_send(tmp_path, standard_backend):
    """A template containing a banned word (em-dash) should be caught
    by the validator before the responder.send_reply call."""
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    em_dash = chr(8212)  # — character literal so global em-dash sweeps don't strip it
    (bad_dir / "objection_pricing.md").write_text(
        f"Hi {{first_name}},\n\nGot it {em_dash} let's revisit.\n\n{{sender_name}}\n"
    )
    responder = FakeResponder()
    runtime = _make_runtime(bad_dir, standard_backend, responder)

    result = await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="hi",
        classify_result=_classify("objection_pricing"),
    )
    assert result.verdict == "skipped:validator_failed"
    assert responder.calls == []


async def test_validator_rejects_banned_word(tmp_path, standard_backend):
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    # "leverage" is banned per icebreaker_adapter._BANNED_WORDS_RE
    (bad_dir / "objection_pricing.md").write_text(
        "Hi {first_name},\n\nLet me leverage our work for {company}.\n\n{sender_name}\n"
    )
    responder = FakeResponder()
    runtime = _make_runtime(bad_dir, standard_backend, responder)
    result = await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="hi",
        classify_result=_classify("objection_pricing"),
    )
    assert result.verdict == "skipped:validator_failed"


# --------------------------------------------------------------------------- #
# Dry run                                                                     #
# --------------------------------------------------------------------------- #


async def test_dry_run_skips_send_but_emits_decision(
    templates_dir, standard_backend
):
    responder = FakeResponder()
    logger = FakeDecisionLogger()
    runtime = _make_runtime(templates_dir, standard_backend, responder, logger)

    result = await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="hi",
        classify_result=_classify("objection_pricing"),
        dry_run=True,
    )
    assert result.verdict == "skipped:dry_run"
    assert responder.calls == []
    decision_types = [e["decision_type"] for e in logger.emits]
    assert "reply_classification" in decision_types
    assert "send_attempt" in decision_types  # logged but no actual send


# --------------------------------------------------------------------------- #
# Decision log                                                                #
# --------------------------------------------------------------------------- #


async def test_emits_both_decision_log_entries_on_send(
    templates_dir, standard_backend
):
    logger = FakeDecisionLogger()
    runtime = _make_runtime(
        templates_dir, standard_backend, logger=logger
    )
    await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="hi",
        classify_result=_classify("objection_pricing"),
    )
    decision_types = [e["decision_type"] for e in logger.emits]
    assert decision_types.count("reply_classification") == 1
    assert decision_types.count("send_attempt") == 1


# --------------------------------------------------------------------------- #
# Responder failure                                                           #
# --------------------------------------------------------------------------- #


async def test_responder_raises_returns_failed_verdict(
    templates_dir, standard_backend
):
    responder = FakeResponder(raise_on_send=RuntimeError("ESP 500"))
    runtime = _make_runtime(templates_dir, standard_backend, responder)
    result = await runtime.respond(
        client_id="c1",
        contact_id="u1",
        in_reply_to_message_id="msg-1",
        original_subject="hi",
        classify_result=_classify("objection_pricing"),
    )
    assert result.verdict == "failed:responder_error"
    assert "ESP 500" in result.reason
