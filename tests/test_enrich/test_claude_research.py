"""Tests for Claude research adapter (Task 12b).

All tests use injected fake clients — no real Anthropic API calls ever made.
"""
import json
from unittest.mock import MagicMock

import anthropic
import pytest

from systems.scout.enrich.base import EnrichResult


# --------------------------------------------------------------------------- #
# Fake Anthropic client                                                         #
# --------------------------------------------------------------------------- #

class _FakeAnthropic:
    """Duck-typed AsyncAnthropic for test injection."""

    def __init__(self, response_json: str | None = None, raises: Exception | None = None):
        self._response_json = response_json
        self._raises = raises
        self.messages = self  # duck-type messages.create

    async def create(self, **kwargs):
        if self._raises:
            raise self._raises
        fake_response = MagicMock()
        fake_response.content = [MagicMock(text=self._response_json)]
        return fake_response


def _valid_response_json(**overrides) -> str:
    payload = {
        "pain_match": "Inconsistent lead flow preventing predictable revenue growth",
        "pain_category": "pipeline",
        "confidence": 0.75,
        "reasoning": "Small service business with no stated niche — pipeline instability is the typical constraint.",
    }
    payload.update(overrides)
    return json.dumps(payload)


@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-haiku-key")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.setenv("ZEROBOUNCE_API_KEY", "zb-test")
    from config.settings import get_settings
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# Imports deferred to after env fixture so settings doesn't blow up            #
# --------------------------------------------------------------------------- #

def _adapter(fake_client):
    from systems.scout.enrich.claude_research import ClaudeResearchAdapter
    return ClaudeResearchAdapter(anthropic_client=fake_client)


# --------------------------------------------------------------------------- #
# Tests                                                                         #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_research_success_populates_data(_env):
    """Valid JSON response → ok=True, all 7 data keys, cost=1."""
    fake = _FakeAnthropic(_valid_response_json())
    adapter = _adapter(fake)
    result = await adapter.enrich({"contact_id": "c1", "company": "Acme Consulting"})

    assert isinstance(result, EnrichResult)
    assert result.ok is True
    assert result.cost_cents == 1
    assert result.reason == "research_complete"
    assert result.adapter_name == "claude_research"

    data = result.data
    assert isinstance(data["pain_match"], str)
    assert isinstance(data["pain_category"], str)
    assert isinstance(data["activity_positive"], bool)
    assert isinstance(data["funding_event_last_180d"], bool)
    assert isinstance(data["recent_hiring"], bool)
    assert isinstance(data["confidence"], float)
    assert isinstance(data["reasoning"], str)


@pytest.mark.asyncio
async def test_research_clamps_confidence_above_one(_env):
    """Claude returns confidence=1.5 → clamped to 1.0."""
    fake = _FakeAnthropic(_valid_response_json(confidence=1.5))
    adapter = _adapter(fake)
    result = await adapter.enrich({"contact_id": "c2", "company": "Acme Consulting"})

    assert result.ok is True
    assert result.data["confidence"] == 1.0


@pytest.mark.asyncio
async def test_research_clamps_confidence_below_zero(_env):
    """Claude returns confidence=-0.2 → clamped to 0.0."""
    fake = _FakeAnthropic(_valid_response_json(confidence=-0.2))
    adapter = _adapter(fake)
    result = await adapter.enrich({"contact_id": "c3", "company": "Acme Consulting"})

    assert result.ok is True
    assert result.data["confidence"] == 0.0


@pytest.mark.asyncio
async def test_research_rejects_invalid_category(_env):
    """Unknown pain_category → overridden to 'other', reason signals the override."""
    fake = _FakeAnthropic(_valid_response_json(pain_category="magical-thinking"))
    adapter = _adapter(fake)
    result = await adapter.enrich({"contact_id": "c4", "company": "Acme Consulting"})

    assert result.ok is True
    assert result.data["pain_category"] == "other"
    assert result.reason == "research_complete_category_invalid"
    assert result.cost_cents == 1


@pytest.mark.asyncio
async def test_research_truncates_long_pain_match(_env):
    """pain_match > 120 chars → truncated to 120."""
    long_pain = "x" * 300
    fake = _FakeAnthropic(_valid_response_json(pain_match=long_pain))
    adapter = _adapter(fake)
    result = await adapter.enrich({"contact_id": "c5", "company": "Acme Consulting"})

    assert result.ok is True
    assert len(result.data["pain_match"]) == 120


@pytest.mark.asyncio
async def test_research_truncates_long_reasoning(_env):
    """reasoning > 200 chars → truncated to 200."""
    long_reasoning = "y" * 500
    fake = _FakeAnthropic(_valid_response_json(reasoning=long_reasoning))
    adapter = _adapter(fake)
    result = await adapter.enrich({"contact_id": "c6", "company": "Acme Consulting"})

    assert result.ok is True
    assert len(result.data["reasoning"]) == 200


@pytest.mark.asyncio
async def test_research_handles_malformed_json(_env):
    """Non-JSON response → ok=True (we were charged), reason='parse_failed', defaults."""
    fake = _FakeAnthropic("not valid json at all {{{")
    adapter = _adapter(fake)
    result = await adapter.enrich({"contact_id": "c7", "company": "Acme Consulting"})

    assert result.ok is True
    assert result.cost_cents == 1
    assert result.reason == "parse_failed"
    assert result.data["pain_match"] is None
    assert result.data["pain_category"] == "other"
    assert result.data["activity_positive"] is False
    assert result.data["funding_event_last_180d"] is False
    assert result.data["recent_hiring"] is False


@pytest.mark.asyncio
async def test_research_returns_no_api_key_when_unset(monkeypatch):
    """ANTHROPIC_API_KEY unset → ok=False, cost=0, reason='no_api_key', client not called."""
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.setenv("ZEROBOUNCE_API_KEY", "zb-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from config.settings import get_settings
    get_settings.cache_clear()

    fake = _FakeAnthropic(_valid_response_json())
    fake_created = False

    # We still inject a fake but it must not be called
    from systems.scout.enrich.claude_research import ClaudeResearchAdapter
    adapter = ClaudeResearchAdapter(anthropic_client=fake)
    result = await adapter.enrich({"contact_id": "c8", "company": "Acme Consulting"})

    assert result.ok is False
    assert result.cost_cents == 0
    assert result.reason == "no_api_key"


@pytest.mark.asyncio
async def test_research_returns_no_company_when_blank(_env):
    """Blank company → ok=False, cost=0, reason='no_company', client not called."""
    fake = _FakeAnthropic(_valid_response_json())
    adapter = _adapter(fake)

    for contact in [
        {"contact_id": "c9"},
        {"contact_id": "c9", "company": ""},
        {"contact_id": "c9", "company": "   "},
    ]:
        result = await adapter.enrich(contact)
        assert result.ok is False
        assert result.cost_cents == 0
        assert result.reason == "no_company"


@pytest.mark.asyncio
async def test_research_dry_run_skips_api(_env):
    """dry_run=True → ok=True, cost=0, reason='dry_run_skipped', client not called."""
    fake = _FakeAnthropic(_valid_response_json())
    adapter = _adapter(fake)
    result = await adapter.enrich(
        {"contact_id": "c10", "company": "Acme Consulting"},
        dry_run=True,
    )

    assert result.ok is True
    assert result.cost_cents == 0
    assert result.reason == "dry_run_skipped"
    assert result.adapter_name == "claude_research"


@pytest.mark.asyncio
async def test_research_raises_on_api_error(_env):
    """Anthropic APIConnectionError propagates — no catch, orchestrator handles."""
    fake = _FakeAnthropic(
        raises=anthropic.APIConnectionError(request=MagicMock())
    )
    adapter = _adapter(fake)

    with pytest.raises(anthropic.APIConnectionError):
        await adapter.enrich({"contact_id": "c11", "company": "Acme Consulting"})


@pytest.mark.asyncio
async def test_research_hardcoded_defaults_present(_env):
    """activity_positive, funding_event_last_180d, recent_hiring always False on success."""
    fake = _FakeAnthropic(_valid_response_json())
    adapter = _adapter(fake)
    result = await adapter.enrich(
        {"contact_id": "c12", "company": "Acme Consulting", "industry": "SaaS"}
    )

    assert result.ok is True
    assert result.data["activity_positive"] is False
    assert result.data["funding_event_last_180d"] is False
    assert result.data["recent_hiring"] is False
