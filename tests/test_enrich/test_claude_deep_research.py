"""Tests for ClaudeDeepResearchAdapter (Task 12b.2).

All tests inject mocked browser + anthropic client — no real network or API calls.
Fixtures are loaded from tests/test_enrich/fixtures/*.html.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# --------------------------------------------------------------------------- #
# Fixture loader                                                                #
# --------------------------------------------------------------------------- #

_FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (_FIXTURE_DIR / name).read_text()


# --------------------------------------------------------------------------- #
# Fake browser                                                                  #
# --------------------------------------------------------------------------- #

class _FakePage:
    def __init__(self, html: str | None, status: int = 200):
        self._html = html
        self._status = status

    async def goto(self, url: str, **kwargs):
        if self._html is None:
            raise TimeoutError(f"Fake timeout for {url}")
        resp = MagicMock()
        resp.status = self._status
        return resp

    async def content(self) -> str:
        return self._html or ""


class _FakeContext:
    def __init__(self, page: _FakePage):
        self._page = page

    async def new_page(self) -> _FakePage:
        return self._page

    async def close(self) -> None:
        pass


class _FakeBrowser:
    """Returns pre-configured pages per URL, or a default page for unspecified URLs.

    Tracks new_context call count so skip-path tests can assert no network happened.
    """

    def __init__(
        self,
        url_map: dict[str, str | None] | None = None,
        default_html: str | None = "",
    ):
        self._url_map = url_map or {}
        self._default_html = default_html
        self.close = AsyncMock()
        self.new_context_calls = 0

    async def new_context(self) -> _FakeContext:
        self.new_context_calls += 1
        return _FakeContext(_FakeUrlDispatchPage(self._url_map, self._default_html))


class _FakeUrlDispatchPage:
    """Dispatches goto() to per-URL HTML strings."""

    def __init__(self, url_map: dict[str, str | None], default_html: str | None):
        self._url_map = url_map
        self._default_html = default_html
        self._current_url: str | None = None

    async def goto(self, url: str, **kwargs):
        self._current_url = url
        html = self._url_map.get(url, self._default_html)
        if html is None:
            raise TimeoutError(f"Fake timeout for {url}")
        resp = MagicMock()
        resp.status = 200
        return resp

    async def content(self) -> str:
        html = self._url_map.get(self._current_url, self._default_html)
        return html or ""

    async def close(self) -> None:
        pass


# --------------------------------------------------------------------------- #
# Fake Anthropic client                                                         #
# --------------------------------------------------------------------------- #

class _FakeAnthropic:
    """Mock Anthropic client. Tracks create() call count for skip-path assertions."""

    def __init__(self, response_json: str):
        self._response_json = response_json
        self.messages = self
        self.close = AsyncMock()
        self.create_calls = 0

    async def create(self, **kwargs):
        self.create_calls += 1
        resp = MagicMock()
        resp.content = [MagicMock(text=self._response_json)]
        return resp


def _full_response(**overrides) -> str:
    """Return a valid full JSON response for the deep research adapter."""
    payload = {
        "citable_details": [
            {
                "type": "case_study",
                "detail": "Ravenna AI 3x pipeline in 90 days via 40-account ICP outbound motion",
                "source": "case_studies",
            },
        ],
        "buying_signals": [
            {
                "category": "hiring",
                "detail": "Hiring two senior SDR managers to support Q3 EMEA expansion",
                "source": "about",
            },
        ],
        "pain_match": "Outbound pipeline consistency needed to support Series A growth targets",
        "pain_category": "pipeline",
        "confidence": 0.82,
        "reasoning": "Company scrape shows active hiring and client results — pipeline scale is the clear constraint.",
    }
    payload.update(overrides)
    return json.dumps(payload)


# --------------------------------------------------------------------------- #
# Env fixture                                                                   #
# --------------------------------------------------------------------------- #

@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-sonnet-key")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.setenv("ZEROBOUNCE_API_KEY", "zb-test")
    from config.settings import get_settings
    get_settings.cache_clear()


def _adapter(browser, fake_client, monkeypatch=None):
    # Patch asyncio.sleep to avoid real waits
    import asyncio
    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    return ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)


# --------------------------------------------------------------------------- #
# Helper to build fixture-backed browser                                        #
# --------------------------------------------------------------------------- #

def _fixture_browser() -> _FakeBrowser:
    """Browser that returns fixture HTML for the 4 content pages, empty for everything else."""
    about_html = _load_fixture("about_page.html")
    services_html = _load_fixture("services_page.html")
    case_studies_html = _load_fixture("case_studies_page.html")
    testimonials_html = _load_fixture("testimonials_page.html")

    url_map = {
        "https://acme-consulting.com/about": about_html,
        "https://acme-consulting.com/about-us": about_html,
        "https://acme-consulting.com/services": services_html,
        "https://acme-consulting.com/case-studies": case_studies_html,
        "https://acme-consulting.com/testimonials": testimonials_html,
    }
    return _FakeBrowser(url_map=url_map, default_html="")


def _linkedin_only_browser() -> _FakeBrowser:
    """Browser where company pages are all empty but LinkedIn pages return content.

    Exercises the company-pages-exhaust-then-LinkedIn path — this path was broken
    in the original commit (URL slicing cut LinkedIn at positions 15-16).
    """
    linkedin_html = _load_fixture("linkedin_company_page.html")
    url_map = {
        "https://www.linkedin.com/company/acme-consulting/": linkedin_html,
        "https://www.linkedin.com/company/acme-consulting/posts/": linkedin_html,
    }
    return _FakeBrowser(url_map=url_map, default_html="")


_CONTACT = {
    "contact_id": "c-deep-001",
    "company": "Acme Consulting",
    "company_domain": "acme-consulting.com",
    "industry": "Business Consulting",
    "employees": 12,
    "title": "Head of Growth",
}


# --------------------------------------------------------------------------- #
# Tests                                                                         #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_deep_research_happy_path(_env, monkeypatch):
    """4 fixture pages load, Claude returns full JSON → ok=True, citable_details≥1, signals≥1, cost=3."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _fixture_browser()
    fake_client = _FakeAnthropic(_full_response())

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.ok is True
    assert result.cost_cents == 3
    assert result.adapter_name == "claude_deep_research"
    assert result.reason == "research_complete"
    assert len(result.data["citable_details"]) >= 1
    assert len(result.data["buying_signals"]) >= 1
    assert isinstance(result.data["sources_fetched"], list)
    assert len(result.data["sources_fetched"]) >= 1


@pytest.mark.asyncio
async def test_deep_research_no_api_key(monkeypatch):
    """ANTHROPIC_API_KEY unset → ok=False, cost=0, no network."""
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.setenv("ZEROBOUNCE_API_KEY", "zb-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from config.settings import get_settings
    get_settings.cache_clear()

    browser = _FakeBrowser()
    fake_client = _FakeAnthropic(_full_response())

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.ok is False
    assert result.cost_cents == 0
    assert result.reason == "no_api_key"
    # Money defense: no network call, no Anthropic call when API key is missing
    assert browser.new_context_calls == 0
    assert fake_client.create_calls == 0


@pytest.mark.asyncio
async def test_deep_research_no_company(_env):
    """Blank company → ok=False, cost=0, no network."""
    browser = _FakeBrowser()
    fake_client = _FakeAnthropic(_full_response())
    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich({
        "contact_id": "c1", "company": "", "company_domain": "acme.com"
    })
    assert result.ok is False
    assert result.cost_cents == 0
    assert result.reason == "no_company"
    # Money defense: no network call, no Anthropic call when company is blank
    assert browser.new_context_calls == 0
    assert fake_client.create_calls == 0


@pytest.mark.asyncio
async def test_deep_research_no_domain(_env):
    """Blank domain → ok=False, cost=0, no network."""
    browser = _FakeBrowser()
    fake_client = _FakeAnthropic(_full_response())
    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich({
        "contact_id": "c2", "company": "Acme", "company_domain": ""
    })
    assert result.ok is False
    assert result.cost_cents == 0
    assert result.reason == "no_domain"
    # Money defense: no network call, no Anthropic call when domain is blank
    assert browser.new_context_calls == 0
    assert fake_client.create_calls == 0


@pytest.mark.asyncio
async def test_deep_research_dry_run(_env):
    """dry_run=True → ok=True, cost=0, no network, no Anthropic call."""
    browser = _FakeBrowser()
    fake_client = _FakeAnthropic(_full_response())
    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT, dry_run=True)
    assert result.ok is True
    assert result.cost_cents == 0
    assert result.reason == "dry_run_skipped"
    # Money defense: dry-run never touches network or billed API
    assert browser.new_context_calls == 0
    assert fake_client.create_calls == 0


@pytest.mark.asyncio
async def test_deep_research_all_pages_miss(_env, monkeypatch):
    """No pages return content → ok=True, reason='no_content_scraped', cost=0."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    # Browser returns empty string for every URL
    browser = _FakeBrowser(url_map={}, default_html="")
    fake_client = _FakeAnthropic(_full_response())

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.ok is True
    assert result.cost_cents == 0
    assert result.reason == "no_content_scraped"
    assert result.data["citable_details"] == []
    assert result.data["buying_signals"] == []


@pytest.mark.asyncio
async def test_deep_research_parse_failure(_env, monkeypatch):
    """Claude returns unparseable JSON → ok=True, reason='parse_failed', cost=3."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _FakeBrowser(url_map={}, default_html="<p>Some content here</p>")
    fake_client = _FakeAnthropic("not valid json {{{")

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.ok is True
    assert result.reason == "parse_failed"
    assert result.cost_cents == 3


@pytest.mark.asyncio
async def test_deep_research_rejects_invalid_pain_category(_env, monkeypatch):
    """Unknown pain_category → overridden to 'other'."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _FakeBrowser(url_map={}, default_html="<p>content</p>")
    fake_client = _FakeAnthropic(_full_response(pain_category="magical-thinking"))

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.ok is True
    assert result.data["pain_category"] == "other"


@pytest.mark.asyncio
async def test_deep_research_drops_invalid_citable_entries(_env, monkeypatch):
    """Entries missing required keys dropped; valid entries kept."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _FakeBrowser(url_map={}, default_html="<p>content</p>")
    payload = {
        "citable_details": [
            {"type": "case_study", "detail": "Valid result", "source": "case_studies"},
            {"type": "testimonial"},                           # missing detail + source
            {"detail": "Missing type", "source": "about"},    # missing type
        ],
        "buying_signals": [],
        "pain_match": "pipeline issue",
        "pain_category": "pipeline",
        "confidence": 0.7,
        "reasoning": "test",
    }
    fake_client = _FakeAnthropic(json.dumps(payload))

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.ok is True
    assert len(result.data["citable_details"]) == 1
    assert result.data["citable_details"][0]["detail"] == "Valid result"


@pytest.mark.asyncio
async def test_deep_research_drops_invalid_signal_categories(_env, monkeypatch):
    """Signals with invalid category dropped; valid ones kept."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _FakeBrowser(url_map={}, default_html="<p>content</p>")
    payload = {
        "citable_details": [],
        "buying_signals": [
            {"category": "hiring", "detail": "SDR managers needed", "source": "about"},
            {"category": "bad-category", "detail": "unknown signal", "source": "about"},
        ],
        "pain_match": "pipeline",
        "pain_category": "pipeline",
        "confidence": 0.6,
        "reasoning": "test",
    }
    fake_client = _FakeAnthropic(json.dumps(payload))

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.ok is True
    signals = result.data["buying_signals"]
    assert len(signals) == 1
    assert signals[0]["category"] == "hiring"


@pytest.mark.asyncio
async def test_deep_research_truncates_long_fields(_env, monkeypatch):
    """pain_match > 160 chars truncated to 160; reasoning > 240 truncated to 240."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _FakeBrowser(url_map={}, default_html="<p>content</p>")
    fake_client = _FakeAnthropic(_full_response(
        pain_match="x" * 300,
        reasoning="y" * 500,
    ))

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.ok is True
    assert len(result.data["pain_match"]) == 160
    assert len(result.data["reasoning"]) == 240


@pytest.mark.asyncio
async def test_deep_research_active_signal_from_category(_env, monkeypatch):
    """Hiring buying_signal → has_active_buying_signal=True."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _FakeBrowser(url_map={}, default_html="<p>content</p>")
    payload = {
        "citable_details": [],
        "buying_signals": [
            {"category": "hiring", "detail": "SDR manager roles open", "source": "about"},
        ],
        "pain_match": "pipeline",
        "pain_category": "pipeline",
        "confidence": 0.7,
        "reasoning": "hiring signal present",
    }
    fake_client = _FakeAnthropic(json.dumps(payload))

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.data["has_active_buying_signal"] is True


@pytest.mark.asyncio
async def test_deep_research_active_signal_from_trigger_recency(_env, monkeypatch):
    """Recent trigger_event (recency_days<90) → has_active_buying_signal=True even with empty signals."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _FakeBrowser(url_map={}, default_html="<p>content</p>")
    payload = {
        "citable_details": [],
        "buying_signals": [],   # no signals from Claude
        "pain_match": "pipeline",
        "pain_category": "pipeline",
        "confidence": 0.5,
        "reasoning": "trigger-driven",
    }
    fake_client = _FakeAnthropic(json.dumps(payload))

    contact = dict(_CONTACT, trigger_events=[
        {"type": "funding_round", "recency_days": 45},
    ])

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(contact)

    assert result.data["has_active_buying_signal"] is True


@pytest.mark.asyncio
async def test_deep_research_continues_past_page_error(_env, monkeypatch):
    """One page raises TimeoutError; other pages succeed; Claude still runs."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    about_html = _load_fixture("about_page.html")

    # case-studies raises timeout; work succeeds. Slice 27 (2026-04-29):
    # path order changed to substantive-first (/case-studies, /work, ...);
    # /about is now past the MAX_PAGES budget so the test would never fetch
    # it. Tests use the new high-priority paths.
    url_map: dict[str, str | None] = {
        "https://acme-consulting.com/case-studies": None,    # triggers TimeoutError
        "https://acme-consulting.com/work": about_html,
    }
    browser = _FakeBrowser(url_map=url_map, default_html="")
    fake_client = _FakeAnthropic(_full_response())

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    # Should succeed — /work loaded, Claude ran
    assert result.ok is True
    assert result.reason in ("research_complete", "research_complete_sparse")
    assert "https://acme-consulting.com/work" in result.data["sources_fetched"]


@pytest.mark.asyncio
async def test_deep_research_aclose_closes_lazy_resources(_env):
    """aclose() closes lazily-created resources; injected resources are untouched."""
    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter

    # Injected: should NOT be closed
    injected_browser = MagicMock()
    injected_browser.close = AsyncMock()
    injected_client = MagicMock()
    injected_client.close = AsyncMock()

    adapter = ClaudeDeepResearchAdapter(
        browser=injected_browser, anthropic_client=injected_client
    )
    await adapter.aclose()

    injected_browser.close.assert_not_called()
    injected_client.close.assert_not_called()

    # Lazy: should be closed
    lazy_browser = MagicMock()
    lazy_browser.close = AsyncMock()
    lazy_client = MagicMock()
    lazy_client.close = AsyncMock()

    adapter2 = ClaudeDeepResearchAdapter()
    adapter2._browser = lazy_browser
    adapter2._anthropic_client = lazy_client
    # _browser_provided and _anthropic_provided are False (not injected at __init__)

    await adapter2.aclose()
    lazy_browser.close.assert_awaited_once()
    lazy_client.close.assert_awaited_once()


# --------------------------------------------------------------------------- #
# Structural signals tests (Task C: B2B Signal Taxonomy)                        #
# --------------------------------------------------------------------------- #


# Slice 27 (2026-04-29): path order swapped to substantive-first;
# /about-us is now past the MAX_PAGES budget. Tests use /case-studies.
_STRUCTURAL_SOURCE_URL = "https://acme-consulting.com/case-studies"
_STRUCTURAL_SOURCE_URL_2 = "https://www.linkedin.com/company/acme-consulting/posts/"


def _structural_browser() -> _FakeBrowser:
    """Browser that returns content for about-us and the LinkedIn posts page.

    These two URLs are the source set available for structural_signals tests;
    evidence_urls outside this set must be rejected by the validator.
    """
    about_html = _load_fixture("about_page.html")
    linkedin_html = _load_fixture("linkedin_company_page.html")
    url_map = {
        _STRUCTURAL_SOURCE_URL: about_html,
        _STRUCTURAL_SOURCE_URL_2: linkedin_html,
    }
    return _FakeBrowser(url_map=url_map, default_html="")


def _response_with_structural(structural_signals: list[dict]) -> str:
    """Base response payload with custom structural_signals list."""
    payload = {
        "citable_details": [],
        "buying_signals": [],
        "structural_signals": structural_signals,
        "pain_match": "pipeline",
        "pain_category": "pipeline",
        "confidence": 0.7,
        "reasoning": "structural test",
    }
    return json.dumps(payload)


@pytest.mark.asyncio
async def test_deep_research_structural_signals_happy_path(_env, monkeypatch):
    """Two valid structural_signals (funding + founder_burnout) both kept."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _structural_browser()
    fake_client = _FakeAnthropic(_response_with_structural([
        {
            "category": "financial_growth",
            "type": "funding_round",
            "evidence_url": _STRUCTURAL_SOURCE_URL,
            "summary": "Closed a Series B round in Q1 to fund US expansion",
        },
        {
            "category": "negative_pain",
            "type": "founder_burnout",
            "evidence_url": _STRUCTURAL_SOURCE_URL_2,
            "summary": "Founder posted about 80-hour weeks and hiring delays",
        },
    ]))

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.ok is True
    # structural_signals contribute to research_complete reason (Tier 3 icebreaker feed).
    assert result.reason == "research_complete"
    signals = result.data["structural_signals"]
    assert len(signals) == 2
    assert signals[0]["category"] == "financial_growth"
    assert signals[0]["type"] == "funding_round"
    assert signals[0]["evidence_url"] == _STRUCTURAL_SOURCE_URL
    assert "Series B" in signals[0]["summary"]
    assert signals[1]["category"] == "negative_pain"
    assert signals[1]["type"] == "founder_burnout"


@pytest.mark.asyncio
async def test_deep_research_structural_rejects_unknown_category(_env, monkeypatch):
    """category='made_up_category' → entry dropped."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _structural_browser()
    fake_client = _FakeAnthropic(_response_with_structural([
        {
            "category": "made_up_category",
            "type": "funding_round",
            "evidence_url": _STRUCTURAL_SOURCE_URL,
            "summary": "Should be dropped, bad category",
        },
    ]))

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.ok is True
    assert result.data["structural_signals"] == []


@pytest.mark.asyncio
async def test_deep_research_structural_rejects_invalid_subtype(_env, monkeypatch):
    """Valid category but subtype not in taxonomy → dropped."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _structural_browser()
    fake_client = _FakeAnthropic(_response_with_structural([
        {
            "category": "financial_growth",
            "type": "aliens_landed",
            "evidence_url": _STRUCTURAL_SOURCE_URL,
            "summary": "Valid category, invalid subtype",
        },
    ]))

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.ok is True
    assert result.data["structural_signals"] == []


@pytest.mark.asyncio
async def test_deep_research_structural_rejects_invented_url(_env, monkeypatch):
    """evidence_url not in sources_fetched → dropped (prevents URL hallucination)."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _structural_browser()
    fake_client = _FakeAnthropic(_response_with_structural([
        {
            "category": "financial_growth",
            "type": "funding_round",
            "evidence_url": "https://not-in-sources.com/fake",
            "summary": "Should be dropped, invented URL",
        },
    ]))

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.ok is True
    assert result.data["structural_signals"] == []


@pytest.mark.asyncio
async def test_deep_research_structural_drops_missing_required_keys(_env, monkeypatch):
    """Entry missing 'summary' → dropped; a complete entry in the same list is kept."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _structural_browser()
    fake_client = _FakeAnthropic(_response_with_structural([
        {
            "category": "financial_growth",
            "type": "funding_round",
            "evidence_url": _STRUCTURAL_SOURCE_URL,
            # summary missing
        },
        {
            "category": "operational_organizational",
            "type": "hiring_spike",
            "evidence_url": _STRUCTURAL_SOURCE_URL,
            "summary": "Opened 8 new engineering roles this month",
        },
    ]))

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.ok is True
    signals = result.data["structural_signals"]
    assert len(signals) == 1
    assert signals[0]["type"] == "hiring_spike"


@pytest.mark.asyncio
async def test_deep_research_structural_caps_at_eight(_env, monkeypatch):
    """12 valid entries → validator keeps exactly 8."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _structural_browser()
    # 12 valid entries, all using the same valid category/subtype/url pair
    entries = [
        {
            "category": "operational_organizational",
            "type": "hiring_spike",
            "evidence_url": _STRUCTURAL_SOURCE_URL,
            "summary": f"Hiring signal number {i}",
        }
        for i in range(12)
    ]
    fake_client = _FakeAnthropic(_response_with_structural(entries))

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.ok is True
    assert len(result.data["structural_signals"]) == 8


@pytest.mark.asyncio
async def test_deep_research_structural_truncates_summary(_env, monkeypatch):
    """Summary > 200 chars → truncated to 200."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _structural_browser()
    fake_client = _FakeAnthropic(_response_with_structural([
        {
            "category": "technographic",
            "type": "software_migration",
            "evidence_url": _STRUCTURAL_SOURCE_URL,
            "summary": "x" * 400,
        },
    ]))

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    assert result.ok is True
    signals = result.data["structural_signals"]
    assert len(signals) == 1
    assert len(signals[0]["summary"]) == 200


def test_deep_research_default_data_includes_structural_signals():
    """_default_data() exposes structural_signals: [] so parse-failed rows are well-shaped."""
    from systems.scout.enrich.claude_deep_research import _default_data
    data = _default_data()
    assert "structural_signals" in data
    assert data["structural_signals"] == []


@pytest.mark.asyncio
async def test_deep_research_linkedin_reachable_when_company_pages_empty(_env, monkeypatch):
    """Regression: LinkedIn URLs (positions 15-16 in the combined URL list) were previously
    unreachable because of a bad slice before the fetch loop. This test locks in that
    LinkedIn fills the slack when company pages return nothing."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    browser = _linkedin_only_browser()
    fake_client = _FakeAnthropic(_full_response())

    from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
    adapter = ClaudeDeepResearchAdapter(browser=browser, anthropic_client=fake_client)
    result = await adapter.enrich(_CONTACT)

    # The run must have reached Claude (some content was gathered from LinkedIn)
    assert result.ok is True
    assert result.cost_cents == 3
    assert result.reason == "research_complete"
    # At least one of the two LinkedIn URLs must appear in sources_fetched
    sources = result.data["sources_fetched"]
    assert any("linkedin.com/company/acme-consulting" in s for s in sources), (
        f"LinkedIn URL never reached despite company pages being empty. sources={sources}"
    )
