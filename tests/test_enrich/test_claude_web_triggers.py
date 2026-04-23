"""Tests for ClaudeWebTriggersAdapter (Task 12b.3a).

All tests inject a fake Anthropic client — no real API calls.
"""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from systems.scout.enrich.base import EnrichResult


# --------------------------------------------------------------------------- #
# Fake Anthropic client                                                         #
# --------------------------------------------------------------------------- #

class _FakeAnthropic:
    def __init__(self, response_json: str, raises: Exception | None = None):
        self._response_json = response_json
        self._raises = raises
        self.messages = self
        self.close = AsyncMock()
        self.create_calls = 0

    async def create(self, **kwargs):
        self.create_calls += 1
        if self._raises:
            raise self._raises
        # Simulate Anthropic's response.content structure — text block at the end.
        # web_search tool results appear earlier; text block last.
        fake_response = MagicMock()
        fake_text_block = MagicMock()
        fake_text_block.text = self._response_json
        fake_response.content = [fake_text_block]
        # Simulate usage with no web search info (basic mock)
        fake_response.usage = MagicMock(spec=[])
        return fake_response


def _make_client(response_json: str, raises: Exception | None = None) -> _FakeAnthropic:
    return _FakeAnthropic(response_json=response_json, raises=raises)


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _contact(**kwargs) -> dict:
    base = {
        "contact_id": "c1",
        "company": "Acme Corp",
        "company_domain": "acmecorp.com",
        "industry": "SaaS",
        "employees": 200,
        "title": "CEO",
    }
    base.update(kwargs)
    return base


def _triggers_response(events: list[dict], confidence: float = 0.8, reasoning: str = "Found news") -> str:
    return json.dumps({
        "trigger_events": events,
        "confidence": confidence,
        "reasoning": reasoning,
    })


def _event(
    type_: str = "funding_round",
    detail: str = "Raised $10M Series A",
    source_url: str = "https://techcrunch.com/acme",
    event_date: str | None = "2026-03-15",
    recency_days: int | None = 36,
    confidence: float = 0.9,
) -> dict:
    return {
        "type": type_,
        "detail": detail,
        "source_url": source_url,
        "event_date": event_date,
        "recency_days": recency_days,
        "confidence": confidence,
    }


# --------------------------------------------------------------------------- #
# Tests                                                                         #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_web_triggers_happy_path(monkeypatch):
    """Valid JSON with 2 trigger events → ok=True, cost=5, reason='triggers_found', events populated."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    events = [
        _event(type_="funding_round", recency_days=30),
        _event(type_="executive_hire", detail="New CRO hired", recency_days=45),
    ]
    client = _make_client(_triggers_response(events))

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact())

    assert isinstance(result, EnrichResult)
    assert result.ok is True
    assert result.cost_cents == 5
    assert result.reason == "triggers_found"
    assert result.adapter_name == "claude_web_triggers"
    assert len(result.data["trigger_events"]) == 2
    assert result.data["has_active_trigger"] is True  # recency_days <= 60
    assert result.data["confidence"] == pytest.approx(0.8)
    assert client.create_calls == 1


@pytest.mark.asyncio
async def test_web_triggers_no_events_found(monkeypatch):
    """Claude returns empty trigger_events → ok=True, cost=5, reason='no_triggers_found'."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _make_client(_triggers_response([], confidence=0.0, reasoning="No news found"))

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact())

    assert result.ok is True
    assert result.cost_cents == 5
    assert result.reason == "no_triggers_found"
    assert result.data["trigger_events"] == []
    assert result.data["has_active_trigger"] is False
    assert client.create_calls == 1


@pytest.mark.asyncio
async def test_web_triggers_no_api_key(monkeypatch):
    """ANTHROPIC_API_KEY unset → ok=False, cost=0, reason='no_api_key', client NOT called."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    client = _make_client(_triggers_response([]))

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact())

    assert result.ok is False
    assert result.cost_cents == 0
    assert result.reason == "no_api_key"
    assert client.create_calls == 0


@pytest.mark.asyncio
async def test_web_triggers_no_company(monkeypatch):
    """Blank company → ok=False, cost=0, reason='no_company', client NOT called."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _make_client(_triggers_response([]))

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact(company=""))

    assert result.ok is False
    assert result.cost_cents == 0
    assert result.reason == "no_company"
    assert client.create_calls == 0


@pytest.mark.asyncio
async def test_web_triggers_dry_run(monkeypatch):
    """dry_run=True → ok=True, cost=0, reason='dry_run_skipped', client NOT called."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _make_client(_triggers_response([]))

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact(), dry_run=True)

    assert result.ok is True
    assert result.cost_cents == 0
    assert result.reason == "dry_run_skipped"
    assert result.adapter_name == "claude_web_triggers"
    assert client.create_calls == 0


@pytest.mark.asyncio
async def test_web_triggers_parse_failure(monkeypatch):
    """Claude returns non-JSON → ok=True, cost=5, reason='parse_failed', empty defaults."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _make_client("not json at all")

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact())

    assert result.ok is True
    assert result.cost_cents == 5
    assert result.reason == "parse_failed"
    assert result.data["trigger_events"] == []
    assert result.data["has_active_trigger"] is False
    assert result.data["confidence"] == 0.0
    assert client.create_calls == 1


@pytest.mark.asyncio
async def test_web_triggers_drops_invalid_event_types(monkeypatch):
    """Events with invalid type (e.g., 'rumor') dropped; valid ones retained."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    events = [
        _event(type_="funding_round"),         # valid
        _event(type_="rumor", detail="Maybe"),  # invalid — dropped
        _event(type_="executive_hire"),          # valid
        _event(type_="acquisition"),             # invalid — dropped
    ]
    client = _make_client(_triggers_response(events))

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact())

    assert result.ok is True
    kept_types = [e["type"] for e in result.data["trigger_events"]]
    assert "funding_round" in kept_types
    assert "executive_hire" in kept_types
    assert "rumor" not in kept_types
    assert "acquisition" not in kept_types
    assert len(result.data["trigger_events"]) == 2


@pytest.mark.asyncio
async def test_web_triggers_drops_events_missing_source_url(monkeypatch):
    """Events without source_url are dropped (no fabrication)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    events = [
        _event(type_="funding_round", source_url="https://tc.com/acme"),  # valid
        {   # missing source_url
            "type": "product_launch",
            "detail": "Launched new product",
            "event_date": "2026-03-10",
            "recency_days": 40,
            "confidence": 0.7,
        },
        _event(type_="expansion", source_url="https://news.com/acme"),   # valid
    ]
    client = _make_client(_triggers_response(events))

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact())

    assert result.ok is True
    kept_types = [e["type"] for e in result.data["trigger_events"]]
    assert "product_launch" not in kept_types
    assert len(result.data["trigger_events"]) == 2


@pytest.mark.asyncio
async def test_web_triggers_caps_at_8_events(monkeypatch):
    """12 events returned → capped at 8, sorted by confidence desc."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    events = [
        _event(
            type_="funding_round",
            detail=f"Event {i}",
            source_url=f"https://news.com/{i}",
            confidence=round(i / 12, 2),
        )
        for i in range(1, 13)  # 12 events, confidence 0.08..1.0
    ]
    client = _make_client(_triggers_response(events))

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact())

    kept = result.data["trigger_events"]
    assert len(kept) == 8
    confidences = [e["confidence"] for e in kept]
    assert confidences == sorted(confidences, reverse=True)


@pytest.mark.asyncio
async def test_web_triggers_truncates_long_fields(monkeypatch):
    """detail >200 chars truncated to 200; reasoning >240 chars truncated to 240."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    long_detail = "X" * 250
    long_reasoning = "Y" * 300

    events = [_event(type_="funding_round", detail=long_detail)]
    payload = json.dumps({
        "trigger_events": events,
        "confidence": 0.7,
        "reasoning": long_reasoning,
    })
    client = _make_client(payload)

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact())

    assert result.ok is True
    assert len(result.data["trigger_events"][0]["detail"]) == 200
    assert len(result.data["reasoning"]) == 240


@pytest.mark.asyncio
async def test_web_triggers_active_trigger_from_recency(monkeypatch):
    """1 event recency_days=30 + 1 with recency_days=85 → has_active_trigger=True."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    events = [
        _event(type_="funding_round", recency_days=30),
        _event(type_="expansion", recency_days=85),
    ]
    client = _make_client(_triggers_response(events))

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact())

    assert result.ok is True
    assert result.data["has_active_trigger"] is True


@pytest.mark.asyncio
async def test_web_triggers_active_trigger_false_when_all_old(monkeypatch):
    """All events with recency_days > 60 → has_active_trigger=False."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    events = [
        _event(type_="funding_round", recency_days=70),
        _event(type_="expansion", recency_days=88),
    ]
    client = _make_client(_triggers_response(events))

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact())

    assert result.ok is True
    assert result.data["has_active_trigger"] is False


@pytest.mark.asyncio
async def test_web_triggers_raises_on_anthropic_error(monkeypatch):
    """client.messages.create raises APIError → propagates (no retry)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    import anthropic
    fake_request = MagicMock()
    error = anthropic.APIStatusError(
        "Internal server error",
        response=MagicMock(status_code=500),
        body={"error": {"message": "Internal server error"}},
    )
    client = _make_client("", raises=error)

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)

    with pytest.raises(anthropic.APIStatusError):
        await adapter.enrich(_contact())

    assert client.create_calls == 1


@pytest.mark.asyncio
async def test_web_triggers_parses_fenced_json(monkeypatch):
    """Claude wraps JSON in ```json ... ``` fences → parses cleanly."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    payload = _triggers_response([_event()])
    wrapped = f"```json\n{payload}\n```"
    client = _make_client(wrapped)

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact())

    assert result.ok is True
    assert result.reason == "triggers_found"
    assert len(result.data["trigger_events"]) == 1


@pytest.mark.asyncio
async def test_web_triggers_parses_prose_prefixed_bare_json(monkeypatch):
    """Claude prepends prose then emits bare JSON → parses cleanly."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    payload = _triggers_response([_event()])
    prose = f"Based on the search results, here is the JSON: {payload}"
    client = _make_client(prose)

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact())

    assert result.ok is True
    assert result.reason == "triggers_found"
    assert len(result.data["trigger_events"]) == 1


@pytest.mark.asyncio
async def test_web_triggers_parses_prose_prefixed_fenced_json(monkeypatch):
    """Claude prepends prose AND wraps in fences — the common Sonnet shape."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    payload = _triggers_response([_event(type_="executive_hire", detail="New CRO hired")])
    prose = (
        "Based on the search results, I have found clear, well-sourced "
        "trigger events for PR Worx. Here is the strictly valid JSON output:"
        f"\n\n```json\n{payload}\n```"
    )
    client = _make_client(prose)

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact())

    assert result.ok is True
    assert result.reason == "triggers_found"
    assert len(result.data["trigger_events"]) == 1
    assert result.data["trigger_events"][0]["type"] == "executive_hire"


@pytest.mark.asyncio
async def test_web_triggers_prose_only_no_signals_found(monkeypatch):
    """Prose-only response with 'no trigger events' → reason='no_signals_found'
    (not parse_failed). The pipeline treats this as a legitimate empty result."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    prose = (
        "Based on the search results, no trigger events (funding rounds, "
        "executive hires, product launches, expansions, layoffs, or major "
        "press coverage) from the last 90 days were found for Inkblot Design."
    )
    client = _make_client(prose)

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact())

    assert result.ok is True
    assert result.cost_cents == 5  # billed regardless
    assert result.reason == "no_signals_found"
    assert result.data["trigger_events"] == []
    assert result.data["has_active_trigger"] is False


@pytest.mark.asyncio
async def test_web_triggers_prose_only_no_match_is_parse_failed(monkeypatch):
    """Pure prose with neither a JSON object nor a 'no signals' phrase
    remains parse_failed (genuine failure mode)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    prose = "I think maybe something happened but I can't say what."
    client = _make_client(prose)

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
    adapter = ClaudeWebTriggersAdapter(anthropic_client=client)
    result = await adapter.enrich(_contact())

    assert result.ok is True
    assert result.reason == "parse_failed"
    assert result.data["trigger_events"] == []


@pytest.mark.asyncio
async def test_web_triggers_extract_json_helper_handles_edge_cases():
    """Unit test for _extract_json_object — brace-counting correctness."""
    from systems.scout.enrich.claude_web_triggers import _extract_json_object

    # Bare JSON
    assert _extract_json_object('{"a": 1}') == '{"a": 1}'

    # Fenced JSON
    assert _extract_json_object('```json\n{"a": 1}\n```') == '{"a": 1}'

    # Prose prefix + bare JSON
    assert _extract_json_object('Here: {"a": 1}') == '{"a": 1}'

    # First balanced block wins — stops the scan on nested structures so
    # the caller (json.loads) always sees a well-formed candidate. If an
    # earlier block isn't valid JSON, the caller falls through to
    # parse_failed, which is the safe outcome.
    assert _extract_json_object('prefix {first} later {"a": 1}') == '{first}'

    # Nested objects (must return the OUTER balanced block)
    assert _extract_json_object('{"a": {"b": 1}}') == '{"a": {"b": 1}}'

    # Braces inside strings must not affect the counter
    assert _extract_json_object('{"s": "has } inside"}') == '{"s": "has } inside"}'

    # No JSON at all
    assert _extract_json_object("just prose") is None
    assert _extract_json_object("") is None


@pytest.mark.asyncio
async def test_web_triggers_aclose_lifecycle(monkeypatch):
    """Lazily-created client closed on aclose(); injected client untouched."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter

    # Injected client — should NOT be closed
    injected_client = _make_client(_triggers_response([]))
    adapter_injected = ClaudeWebTriggersAdapter(anthropic_client=injected_client)
    await adapter_injected.aclose()
    injected_client.close.assert_not_called()

    # Lazy client — should be closed on aclose()
    lazy_client = _make_client(_triggers_response([]))

    adapter_lazy = ClaudeWebTriggersAdapter()
    # Inject via internal attribute to avoid real AsyncAnthropic instantiation
    adapter_lazy._anthropic_client = lazy_client
    adapter_lazy._anthropic_provided = False  # we own it

    await adapter_lazy.aclose()
    lazy_client.close.assert_called_once()
    # aclose() idempotent — calling again should not raise
    await adapter_lazy.aclose()
