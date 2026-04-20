"""Claude-backed identity scraper — tier-3 fallback in the identity waterfall.

Uses Playwright to fetch public pages (company /team, LinkedIn People, Google SERP)
and Claude Haiku to extract the primary decision-maker from each page's HTML.
Runs only when Apollo (tier 1) and Hunter (tier 2) have both returned None.

Throttle: 1 scrape-chain per 15 seconds to avoid hammering targets.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Callable

from systems.scout.identity.base import IdentityResult, is_generic_email


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level throttle state
# ---------------------------------------------------------------------------
_THROTTLE_LOCK: asyncio.Lock | None = None  # created lazily (event loop may not exist at import)
_LAST_REQUEST_TS: float = 0.0
_THROTTLE_SECONDS: float = 15.0

# Warn once at module load if API key is missing, not per-call
_API_KEY_WARNED: bool = False


def _get_throttle_lock() -> asyncio.Lock:
    """Return the module-level asyncio.Lock, creating it on first access."""
    global _THROTTLE_LOCK
    if _THROTTLE_LOCK is None:
        _THROTTLE_LOCK = asyncio.Lock()
    return _THROTTLE_LOCK


async def _await_throttle(clock: Callable[[], float]) -> None:
    global _LAST_REQUEST_TS
    lock = _get_throttle_lock()
    async with lock:
        now = clock()
        gap = now - _LAST_REQUEST_TS
        if gap < _THROTTLE_SECONDS:
            await asyncio.sleep(_THROTTLE_SECONDS - gap)
        _LAST_REQUEST_TS = clock()


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------
_SCRIPT_RE = re.compile(r"<script[^>]*>.*?</script>", re.I | re.S)
_STYLE_RE = re.compile(r"<style[^>]*>.*?</style>", re.I | re.S)
_NAV_RE = re.compile(r"<nav[^>]*>.*?</nav>", re.I | re.S)
_HTML_TRUNCATE_CHARS = 15_000


def _clean_html(raw: str) -> str:
    """Strip scripts, styles, and navs; truncate to ~15 000 chars."""
    html = _SCRIPT_RE.sub("", raw)
    html = _STYLE_RE.sub("", html)
    html = _NAV_RE.sub("", html)
    return html[:_HTML_TRUNCATE_CHARS]


# ---------------------------------------------------------------------------
# Playwright fetch helper
# ---------------------------------------------------------------------------
async def _fetch_html(browser: Any, url: str) -> str | None:
    """Fetch a page via Playwright; return HTML or None on failure."""
    context = await browser.new_context()
    try:
        page = await context.new_page()
        response = await page.goto(url, timeout=15000, wait_until="domcontentloaded")
        if not response or response.status >= 400:
            return None
        html = await page.content()
        return html
    except Exception:
        return None
    finally:
        await context.close()


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------
_TEAM_PATHS = ("/team", "/about", "/leadership", "/about-us", "/our-team")


def _team_page_urls(domain: str) -> list[str]:
    base = domain.rstrip("/")
    if not base.startswith("http"):
        base = f"https://{base}"
    return [f"{base}{path}" for path in _TEAM_PATHS]


def _linkedin_people_url(company: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")
    return f"https://www.linkedin.com/company/{slug}/people/"


def _google_serp_url(company: str) -> str:
    import urllib.parse
    q = urllib.parse.quote_plus(f'{company} "CEO" OR "founder"')
    return f"https://www.google.com/search?q={q}"


# ---------------------------------------------------------------------------
# Claude extraction
# ---------------------------------------------------------------------------
_HAIKU_MODEL = "claude-haiku-4-5-20251001"

_EXTRACTION_PROMPT = """\
You are extracting the primary decision-maker (founder, CEO, owner, or equivalent) from an HTML page about a company.

Company: {company}
Company domain: {domain}
Page source: {page_source}

Return STRICTLY valid JSON with this shape. No prose. No markdown fences.

{{
  "first_name": "...",
  "last_name": "...",
  "title": "Founder" | "CEO" | "President" | "Owner" | null,
  "email": "person@company.com" | null,
  "linkedin_url": "https://linkedin.com/in/..." | null,
  "confidence": 0.0 to 1.0
}}

Rules:
- Only return a decision-maker: founder, CEO, president, owner, managing director, managing partner, or C-suite.
- Do NOT return generic mailboxes (info@, contact@, hello@, sales@, team@, admin@, support@, help@). If that's all you see, return {{"first_name": null, "last_name": null, "email": null, "confidence": 0.0}}.
- Do NOT guess or invent. If first/last name aren't BOTH present with high certainty, return {{"first_name": null, "last_name": null, "email": null, "confidence": 0.0}}.
- Do NOT return "Unknown" or "N/A" for any field.

HTML:
{truncated_html}
"""

_CONFIDENCE_CAP = 0.85


async def _extract_from_html(
    anthropic_client: Any,
    html: str,
    company: str,
    domain: str,
    page_source: str,
) -> dict[str, Any] | None:
    """Call Claude Haiku to extract a decision-maker from HTML.

    Returns the parsed JSON dict, or None if extraction fails.
    """
    cleaned = _clean_html(html)
    prompt = _EXTRACTION_PROMPT.format(
        company=company,
        domain=domain or "unknown",
        page_source=page_source,
        truncated_html=cleaned,
    )
    try:
        response = await anthropic_client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("claude_scraper: malformed JSON from Claude for %s (%s)", company, page_source)
        return None
    except Exception as exc:
        logger.warning("claude_scraper: Claude API error for %s (%s): %s", company, page_source, exc)
        return None


def _parse_extraction(
    data: dict[str, Any],
    url: str,
    sources_attempted: list[str],
) -> IdentityResult | None:
    """Validate Claude's JSON output against rejection criteria.

    Returns IdentityResult on success, None on any rejection criterion.
    """
    first = (data.get("first_name") or "").strip()
    last = (data.get("last_name") or "").strip()

    if not first or not last:
        return None
    if first.lower() in {"unknown", "n/a"} or last.lower() in {"unknown", "n/a"}:
        return None

    email = data.get("email")
    if is_generic_email(email):
        return None

    raw_conf = float(data.get("confidence") or 0.0)
    confidence = min(raw_conf, _CONFIDENCE_CAP)

    return IdentityResult(
        first_name=first,
        last_name=last,
        title=data.get("title") or None,
        email=email,  # type: ignore[arg-type]  # validated above (not None, not generic)
        linkedin_url=data.get("linkedin_url") or None,
        source="claude_scraper",
        confidence=confidence,
        sources_attempted=sources_attempted[:],
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------
class ClaudeIdentityScraper:
    """Playwright + Claude Haiku identity scraper. name='claude_scraper'.

    Tier-3 fallback in the Apollo → Hunter → claude_scraper waterfall.
    """

    name: str = "claude_scraper"

    def __init__(
        self,
        browser: Any = None,
        anthropic_client: Any = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """
        browser: a Playwright browser instance for dependency injection in tests.
        anthropic_client: AsyncAnthropic client for dependency injection.
        clock: callable returning current time (defaults to time.monotonic) — used for throttle testing.
        """
        self._browser = browser
        self._anthropic_client = anthropic_client
        self._clock = clock or time.monotonic
        self._playwright_ctx: Any = None  # holds async_playwright() manager

    async def _ensure_browser(self) -> Any:
        """Lazily launch a Playwright browser if none was injected."""
        if self._browser is not None:
            return self._browser
        from playwright.async_api import async_playwright
        self._playwright_ctx = await async_playwright().start()
        self._browser = await self._playwright_ctx.chromium.launch(headless=True)
        return self._browser

    async def _ensure_anthropic_client(self) -> Any:
        """Lazily create an Anthropic async client if none was injected."""
        if self._anthropic_client is not None:
            return self._anthropic_client
        from anthropic import AsyncAnthropic
        self._anthropic_client = AsyncAnthropic()
        return self._anthropic_client

    async def resolve(
        self,
        company: str,
        company_domain: str | None = None,
        **kwargs: Any,
    ) -> IdentityResult | None:
        """Scrape + extract decision-maker for company.

        Returns None if:
        - ANTHROPIC_API_KEY is not set
        - company is empty/whitespace
        - All three sources (team page, LinkedIn, Google) fail rejection criteria
        """
        global _API_KEY_WARNED

        # Guard: empty company
        if not company or not company.strip():
            return None

        # Guard: API key
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            if not _API_KEY_WARNED:
                logger.warning("claude_scraper: ANTHROPIC_API_KEY not set — skipping scraper")
                _API_KEY_WARNED = True
            return None

        await _await_throttle(self._clock)

        browser = await self._ensure_browser()
        anthropic = await self._ensure_anthropic_client()
        domain = company_domain or "unknown"

        sources_attempted: list[str] = []

        # --- Source 1: Company team/about/leadership page ---
        if company_domain:
            team_urls = _team_page_urls(company_domain)
            for url in team_urls:
                html = await _fetch_html(browser, url)
                if html is not None:
                    sources_attempted.append(url)
                    data = await _extract_from_html(anthropic, html, company, domain, "team_page")
                    if data:
                        result = _parse_extraction(data, url, sources_attempted)
                        if result:
                            return result
                    break  # stop at first 200 OK, even if extraction failed

        # --- Source 2: LinkedIn company people page ---
        linkedin_url = _linkedin_people_url(company)
        html = await _fetch_html(browser, linkedin_url)
        if html is not None:
            sources_attempted.append(linkedin_url)
            data = await _extract_from_html(anthropic, html, company, domain, "linkedin_people")
            if data:
                result = _parse_extraction(data, linkedin_url, sources_attempted)
                if result:
                    return result

        # --- Source 3: Google SERP ---
        google_url = _google_serp_url(company)
        html = await _fetch_html(browser, google_url)
        if html is not None:
            sources_attempted.append(google_url)
            data = await _extract_from_html(anthropic, html, company, domain, "google_serp")
            if data:
                result = _parse_extraction(data, google_url, sources_attempted)
                if result:
                    return result

        return None
