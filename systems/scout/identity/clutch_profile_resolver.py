"""Clutch profile-page resolver — cheap-tier company-data resolver.

Per the 2026-04-29 Pattern C decision doc: cheap_resolve runs between pull
and score_v1 to fill company-level fields (especially company_domain) so
score_v1 can fairly evaluate fit, AND so the downstream identity stage
(Apollo / Hunter — both REQUIRE a domain) actually has something to
search against.

This resolver targets contacts pulled from Clutch (source like ``clutch:*``).
It navigates to the agency's Clutch profile page via the same
Playwright + stealth + headed Chrome pattern documented in
``skills/playbooks/build-cloudflare-protected-scraper.md`` and extracts
the company website from the ``provider_website=<domain>`` query
parameter that appears in every Clutch ``r.clutch.co/redirect?...`` URL
on a profile page.

Returns ``{"company_domain": str}`` on success; ``{}`` on miss. Empty
dict (not None) so the cheap_resolve stage's "merge results into contact"
step is uniform across resolvers.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote


# Match Clutch's redirect URL pattern: ...provider_website=<value>...
# Value can be a bare domain ("wantbranding.com") or full URL (rare). We
# parse and normalise downstream.
_PROVIDER_WEBSITE_PATTERN = re.compile(
    r"provider_website=([^&\"']+)",
)


def _normalise_domain(value: str) -> str | None:
    """Strip protocol, www., and trailing paths from a website value."""
    if not value:
        return None
    v = unquote(value).strip().lower()
    # Strip protocol if present
    for prefix in ("https://", "http://"):
        if v.startswith(prefix):
            v = v[len(prefix):]
    # Strip www. and trailing path
    if v.startswith("www."):
        v = v[4:]
    v = v.split("/", 1)[0]
    v = v.split("?", 1)[0]
    return v or None


def extract_company_domain_from_profile_html(html: str) -> str | None:
    """Extract the agency's website domain from a Clutch profile page HTML.

    Pattern: every Clutch profile page has multiple ``r.clutch.co/redirect``
    links whose query string includes ``provider_website=<domain>``. All
    occurrences point at the SAME domain (Clutch instruments different
    "Visit website" CTAs the same way). Take the first match.
    """
    match = _PROVIDER_WEBSITE_PATTERN.search(html)
    if not match:
        return None
    return _normalise_domain(match.group(1))


class ClutchProfileResolver:
    """Cheap-tier resolver for Clutch-sourced contacts. name='clutch_profile'.

    Public contract:
      - ``applies_to(contact)`` → bool (does this resolver have anything to
        say about this contact?)
      - ``resolve(contact)`` → dict with newly-discovered company fields.
        Empty dict on miss.

    Test seam: pass ``html_fetcher`` (a callable ``async (url) -> str``)
    to inject a mock that returns canned profile HTML. Production wiring
    passes None; the resolver instantiates its own Playwright session.
    """

    name: str = "clutch_profile"

    def __init__(
        self,
        html_fetcher: Any | None = None,
        *,
        playwright_headless: bool = False,
        playwright_challenge_wait_ms: int = 5_000,
    ) -> None:
        self._html_fetcher = html_fetcher
        self._playwright_headless = playwright_headless
        self._playwright_challenge_wait_ms = playwright_challenge_wait_ms

    def applies_to(self, contact: dict[str, Any]) -> bool:
        """Apply only to Clutch-sourced contacts. ``raw_data.profile_url``
        must be present (it's set by ClutchAdapter's pull-stage parser)."""
        source = (contact.get("source") or "").lower()
        if not source.startswith("clutch:") and source != "clutch":
            return False
        raw_data = contact.get("raw_data") or {}
        return bool(raw_data.get("profile_url"))

    async def resolve(self, contact: dict[str, Any]) -> dict[str, Any]:
        """Fetch the Clutch profile page and extract company_domain."""
        if not self.applies_to(contact):
            return {}
        if contact.get("company_domain"):
            return {}  # already resolved; nothing to do

        raw_data = contact.get("raw_data") or {}
        profile_url = raw_data.get("profile_url")
        if not profile_url:
            return {}

        html = await self._fetch_html(profile_url)
        if not html:
            return {}

        domain = extract_company_domain_from_profile_html(html)
        if not domain:
            return {}
        return {"company_domain": domain}

    async def _fetch_html(self, url: str) -> str:
        """Production: Playwright + stealth + headed (matches ClutchAdapter
        pattern). Test: injected callable."""
        if self._html_fetcher is not None:
            return await self._html_fetcher(url)

        # Lazy imports — keep test environments without browsers happy.
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self._playwright_headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            try:
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                await Stealth().apply_stealth_async(context)
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30_000)
                await page.wait_for_timeout(self._playwright_challenge_wait_ms)
                title = await page.title()
                if "Just a moment" in title or "challenge" in title.lower():
                    await page.wait_for_timeout(
                        self._playwright_challenge_wait_ms * 2,
                    )
                return await page.content()
            finally:
                await browser.close()
