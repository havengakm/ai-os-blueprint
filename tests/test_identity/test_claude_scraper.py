"""Tests for ClaudeIdentityScraper — tier-3 identity fallback adapter."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from systems.scout.identity.claude_identity_scraper import (
    ClaudeIdentityScraper,
    _THROTTLE_SECONDS,
    _await_throttle,
)
from systems.scout.identity.base import IdentityResult


# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------
FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


# ---------------------------------------------------------------------------
# Helpers — mock browser and Anthropic client
# ---------------------------------------------------------------------------

def _make_browser(responses: dict[str, str | None]) -> Any:
    """Build a mock Playwright Browser that returns HTML by URL pattern.

    responses: {url_substring: html_or_None}
    If url_substring is "*", it's the default fallback.
    """
    async def _new_context():
        ctx = AsyncMock()

        async def _new_page():
            page = AsyncMock()

            async def _goto(url, timeout=15000, wait_until="domcontentloaded"):
                for key, html in responses.items():
                    if key == "*" or key in url:
                        if html is None:
                            return None
                        mock_response = MagicMock()
                        mock_response.status = 200
                        page._current_html = html
                        return mock_response
                # default: 404
                mock_response = MagicMock()
                mock_response.status = 404
                page._current_html = ""
                return mock_response

            async def _content():
                return getattr(page, "_current_html", "")

            page.goto = _goto
            page.content = _content
            return page

        ctx.new_page = _new_page
        ctx.close = AsyncMock()
        return ctx

    browser = AsyncMock()
    browser.new_context = _new_context
    return browser


def _make_anthropic(responses: list[str]) -> Any:
    """Build a mock AsyncAnthropic that returns pre-baked response strings in order."""
    call_count = [0]

    async def _create(**kwargs):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        content_block = MagicMock()
        content_block.text = responses[idx]
        mock_resp = MagicMock()
        mock_resp.content = [content_block]
        return mock_resp

    client = AsyncMock()
    client.messages.create = _create
    return client


# ---------------------------------------------------------------------------
# Standard env fixture
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    """Reset module-level throttle state and API-key-warned flag between tests."""
    import systems.scout.identity.claude_identity_scraper as mod
    monkeypatch.setattr(mod, "_LAST_REQUEST_TS", 0.0)
    monkeypatch.setattr(mod, "_THROTTLE_LOCK", None)
    monkeypatch.setattr(mod, "_API_KEY_WARNED", False)


@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")


# ---------------------------------------------------------------------------
# JSON stubs
# ---------------------------------------------------------------------------
_CEO_JSON = '{"first_name": "Sarah", "last_name": "Mitchell", "title": "CEO", "email": "sarah@acmecorp.com", "linkedin_url": "https://linkedin.com/in/sarahmitchell", "confidence": 0.92}'
_LINKEDIN_CEO_JSON = '{"first_name": "James", "last_name": "Carter", "title": "Co-Founder", "email": "james@acmecorp.com", "linkedin_url": "https://linkedin.com/in/james-carter", "confidence": 0.88}'
_GOOGLE_CEO_JSON = '{"first_name": "Michael", "last_name": "Torres", "title": "Founder", "email": "michael@acmecorp.com", "linkedin_url": null, "confidence": 0.75}'
_NULL_JSON = '{"first_name": null, "last_name": null, "title": null, "email": null, "linkedin_url": null, "confidence": 0.0}'
_GENERIC_EMAIL_JSON = '{"first_name": "John", "last_name": "Doe", "title": "CEO", "email": "info@foo.com", "linkedin_url": null, "confidence": 0.5}'
_UNKNOWN_NAME_JSON = '{"first_name": "Unknown", "last_name": "Person", "title": "CEO", "email": "someone@foo.com", "linkedin_url": null, "confidence": 0.6}'
_HIGH_CONF_JSON = '{"first_name": "Alice", "last_name": "Wong", "title": "CEO", "email": "alice@testco.com", "linkedin_url": null, "confidence": 0.99}'


# ---------------------------------------------------------------------------
# Test 1: resolves from team page
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scraper_resolves_from_team_page(_env):
    html = _load_fixture("team_page_success.html")
    browser = _make_browser({"/team": html})
    anthropic = _make_anthropic([_CEO_JSON])

    scraper = ClaudeIdentityScraper(browser=browser, anthropic_client=anthropic)
    result = await scraper.resolve(company="Acme Corp", company_domain="acmecorp.com")

    assert result is not None
    assert isinstance(result, IdentityResult)
    assert result.first_name == "Sarah"
    assert result.last_name == "Mitchell"
    assert result.email == "sarah@acmecorp.com"
    assert result.source == "claude_scraper"
    assert any("acmecorp.com" in url for url in result.sources_attempted)


# ---------------------------------------------------------------------------
# Test 2: falls through to LinkedIn when team page misses
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scraper_falls_through_to_linkedin_when_team_page_misses(_env):
    team_html = _load_fixture("team_page_success.html")
    linkedin_html = _load_fixture("linkedin_people_success.html")

    # Team pages return HTML (so scraper sees a 200 and tries extraction),
    # but Claude returns null JSON. LinkedIn returns the CEO.
    browser = _make_browser({
        "/team": team_html,
        "linkedin.com": linkedin_html,
    })
    anthropic = _make_anthropic([_NULL_JSON, _LINKEDIN_CEO_JSON])

    scraper = ClaudeIdentityScraper(browser=browser, anthropic_client=anthropic)
    result = await scraper.resolve(company="Acme Corp", company_domain="acmecorp.com")

    assert result is not None
    assert result.first_name == "James"
    assert result.last_name == "Carter"
    assert any("linkedin.com" in url for url in result.sources_attempted)


# ---------------------------------------------------------------------------
# Test 3: falls through to Google when team + LinkedIn miss
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scraper_falls_through_to_google_when_team_and_linkedin_miss(_env):
    team_html = _load_fixture("team_page_success.html")
    linkedin_html = _load_fixture("linkedin_people_success.html")
    google_html = _load_fixture("google_serp_success.html")

    browser = _make_browser({
        "/team": team_html,
        "linkedin.com": linkedin_html,
        "google.com": google_html,
    })
    anthropic = _make_anthropic([_NULL_JSON, _NULL_JSON, _GOOGLE_CEO_JSON])

    scraper = ClaudeIdentityScraper(browser=browser, anthropic_client=anthropic)
    result = await scraper.resolve(company="Acme Corp", company_domain="acmecorp.com")

    assert result is not None
    assert result.first_name == "Michael"
    assert result.last_name == "Torres"
    assert any("google.com" in url for url in result.sources_attempted)


# ---------------------------------------------------------------------------
# Test 4: returns None when all three sources miss
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scraper_returns_none_when_all_three_sources_miss(_env):
    html = _load_fixture("team_page_success.html")
    browser = _make_browser({"*": html})
    anthropic = _make_anthropic([_NULL_JSON, _NULL_JSON, _NULL_JSON])

    scraper = ClaudeIdentityScraper(browser=browser, anthropic_client=anthropic)
    result = await scraper.resolve(company="Acme Corp", company_domain="acmecorp.com")

    assert result is None


# ---------------------------------------------------------------------------
# Test 5: skips generic emails
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scraper_skips_generic_emails(_env):
    team_html = _load_fixture("team_page_generic_only.html")
    linkedin_html = _load_fixture("linkedin_people_success.html")

    browser = _make_browser({
        "/team": team_html,
        "linkedin.com": linkedin_html,
    })
    # First call returns generic email, second returns a real CEO from LinkedIn
    anthropic = _make_anthropic([_GENERIC_EMAIL_JSON, _LINKEDIN_CEO_JSON])

    scraper = ClaudeIdentityScraper(browser=browser, anthropic_client=anthropic)
    result = await scraper.resolve(company="Generic Corp", company_domain="genericcorp.com")

    # Generic email from team page was rejected; LinkedIn result returned
    assert result is not None
    assert result.first_name == "James"
    assert result.email == "james@acmecorp.com"


# ---------------------------------------------------------------------------
# Test 6: skips Unknown names
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scraper_skips_unknown_names(_env):
    team_html = _load_fixture("team_page_success.html")
    linkedin_html = _load_fixture("linkedin_people_success.html")

    browser = _make_browser({
        "/team": team_html,
        "linkedin.com": linkedin_html,
    })
    anthropic = _make_anthropic([_UNKNOWN_NAME_JSON, _LINKEDIN_CEO_JSON])

    scraper = ClaudeIdentityScraper(browser=browser, anthropic_client=anthropic)
    result = await scraper.resolve(company="Acme Corp", company_domain="acmecorp.com")

    assert result is not None
    assert result.first_name == "James"  # from LinkedIn, not the "Unknown" from team page


# ---------------------------------------------------------------------------
# Test 7: clamps confidence at 0.85
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scraper_clamps_confidence_at_085(_env):
    html = _load_fixture("team_page_success.html")
    browser = _make_browser({"/team": html})
    anthropic = _make_anthropic([_HIGH_CONF_JSON])  # confidence: 0.99

    scraper = ClaudeIdentityScraper(browser=browser, anthropic_client=anthropic)
    result = await scraper.resolve(company="Test Co", company_domain="testco.com")

    assert result is not None
    assert result.confidence == 0.85


# ---------------------------------------------------------------------------
# Test 8: returns None without ANTHROPIC_API_KEY
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scraper_returns_none_without_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    browser = AsyncMock()  # should never be called
    anthropic = AsyncMock()  # should never be called

    scraper = ClaudeIdentityScraper(browser=browser, anthropic_client=anthropic)
    result = await scraper.resolve(company="Acme Corp", company_domain="acmecorp.com")

    assert result is None
    browser.new_context.assert_not_called()
    anthropic.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# Test 9: returns None with empty company
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scraper_returns_none_with_empty_company(_env):
    browser = AsyncMock()

    scraper = ClaudeIdentityScraper(browser=browser)
    result = await scraper.resolve(company="", company_domain="acmecorp.com")

    assert result is None
    browser.new_context.assert_not_called()


# ---------------------------------------------------------------------------
# Test 10: throttles between calls
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scraper_throttles_between_calls(_env, monkeypatch):
    import systems.scout.identity.claude_identity_scraper as mod

    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    # Fake clock: first call at t=0, second at t=5 (well inside the 15s window)
    tick = [0.0]

    def _fake_clock() -> float:
        return tick[0]

    monkeypatch.setattr(mod, "_LAST_REQUEST_TS", 0.0)
    monkeypatch.setattr(mod, "_THROTTLE_LOCK", None)

    html = _load_fixture("team_page_success.html")
    browser = _make_browser({"/team": html})
    anthropic = _make_anthropic([_CEO_JSON, _CEO_JSON])

    # First resolve at t=0 — sets _LAST_REQUEST_TS to 0
    with patch("systems.scout.identity.claude_identity_scraper.asyncio.sleep", side_effect=_fake_sleep):
        scraper = ClaudeIdentityScraper(browser=browser, anthropic_client=anthropic, clock=_fake_clock)
        await scraper.resolve(company="Acme Corp", company_domain="acmecorp.com")

        # Advance fake clock by only 5 seconds, well within throttle window
        tick[0] = 5.0

        await scraper.resolve(company="Acme Corp", company_domain="acmecorp.com")

    # asyncio.sleep should have been called once (for the 2nd resolve), approx 10s
    assert len(sleep_calls) >= 1
    assert abs(sleep_calls[-1] - (_THROTTLE_SECONDS - 5.0)) < 0.5


# ---------------------------------------------------------------------------
# Test 11: handles malformed Claude JSON — falls through to next source
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scraper_handles_malformed_claude_json(_env):
    team_html = _load_fixture("team_page_success.html")
    linkedin_html = _load_fixture("linkedin_people_success.html")

    browser = _make_browser({
        "/team": team_html,
        "linkedin.com": linkedin_html,
    })
    # Team page returns malformed JSON, LinkedIn returns valid CEO
    anthropic = _make_anthropic(["not valid json", _LINKEDIN_CEO_JSON])

    scraper = ClaudeIdentityScraper(browser=browser, anthropic_client=anthropic)
    result = await scraper.resolve(company="Acme Corp", company_domain="acmecorp.com")

    assert result is not None
    assert result.first_name == "James"
    assert result.last_name == "Carter"
    assert result.source == "claude_scraper"


# ---------------------------------------------------------------------------
# Test 12: aclose() closes lazily-created browser + playwright context
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scraper_aclose_closes_lazy_browser():
    """Lazily-created browser and playwright ctx are closed on aclose()."""
    fake_browser = AsyncMock()
    fake_playwright_ctx = AsyncMock()

    async def _fake_start():
        return fake_playwright_ctx

    fake_playwright_ctx.chromium = AsyncMock()
    fake_playwright_ctx.chromium.launch = AsyncMock(return_value=fake_browser)

    scraper = ClaudeIdentityScraper(browser=None, anthropic_client=None)

    with patch(
        "systems.scout.identity.claude_identity_scraper.async_playwright",
        return_value=AsyncMock(start=_fake_start),
    ):
        await scraper._ensure_browser()

    await scraper.aclose()

    fake_browser.close.assert_called_once()
    fake_playwright_ctx.stop.assert_called_once()


# ---------------------------------------------------------------------------
# Test 13: aclose() does NOT close an injected browser
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scraper_aclose_does_not_close_injected_browser():
    """Injected browser is not owned by the scraper; aclose() must not close it."""
    injected_browser = AsyncMock()

    scraper = ClaudeIdentityScraper(browser=injected_browser, anthropic_client=None)
    await scraper.aclose()

    injected_browser.close.assert_not_called()


# ---------------------------------------------------------------------------
# Test 14: aclose() is idempotent
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scraper_aclose_idempotent():
    """Calling aclose() twice must not raise and browser.close() called exactly once."""
    fake_browser = AsyncMock()
    fake_playwright_ctx = AsyncMock()

    async def _fake_start():
        return fake_playwright_ctx

    fake_playwright_ctx.chromium = AsyncMock()
    fake_playwright_ctx.chromium.launch = AsyncMock(return_value=fake_browser)

    scraper = ClaudeIdentityScraper(browser=None, anthropic_client=None)

    with patch(
        "systems.scout.identity.claude_identity_scraper.async_playwright",
        return_value=AsyncMock(start=_fake_start),
    ):
        await scraper._ensure_browser()

    await scraper.aclose()
    await scraper.aclose()  # second call must not raise

    fake_browser.close.assert_called_once()
    fake_playwright_ctx.stop.assert_called_once()


