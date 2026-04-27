"""Clutch.co directory adapter — company-level listing scrape.

Ports the n8n workflow `clutch-shopify-scraper.json` (listing-page only, no
detail-page scraping). Downstream stages (Task 9.5 identity lookup) resolve
company_domain when needed via company-name lookup on Apollo/Hunter.

Supports any Clutch category — parameterise via `category_path` (e.g.
'developers/shopify', 'agencies/digital-marketing').

Plan 2 Task 2.0.5 hardening (2026-04-27):
  - Retries transient 429 / 503 / 5xx with exponential backoff before
    raising. Caps at ``max_retries`` per request (default 3).
  - Raises ``ClutchSuspiciousEmptyError`` when page 0 (the FIRST page)
    yields zero parsed entries on a 200 OK response. That shape masquerades
    as a clean empty pull but typically indicates CAPTCHA interstitial,
    soft-block page, or layout drift. The pull stage emits a
    ``decision_type='source_selection'`` decision_log row with reasoning
    set to ``scout.source.empty_first_page`` so the operator sees the
    distinction.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from systems.scout.sources.base import CompanySourceAdapter, RawCompanyContact


CLUTCH_BASE_URL = "https://clutch.co"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
THROTTLE_SECONDS = 4.0
REQUEST_TIMEOUT = 30.0

# HTTP statuses that warrant a retry. 429 = rate limit, 503 = service
# unavailable, 502/504 = transient gateway issues. 403 is treated as
# soft-block-suspect — retry once with longer backoff before giving up.
_RETRY_STATUSES: frozenset[int] = frozenset({429, 502, 503, 504})
_SOFT_BLOCK_STATUSES: frozenset[int] = frozenset({403})

# Default backoff schedule (seconds). Each retry sleeps progressively longer.
_DEFAULT_RETRY_BACKOFF_SECONDS: float = 5.0
_DEFAULT_MAX_RETRIES: int = 3

# Extraction patterns ported verbatim from the n8n workflow (see
# clutch-shopify-scraper.json parse-companies node).
_NAME_PATTERN = re.compile(r'"name"\s*:\s*"([^"]+)"')
_PROFILE_URL_PATTERN = re.compile(r"""href=["'](https?://clutch\.co/profile/[^"']+)["']""")
_LOCATION_PATTERN = re.compile(r"""class=["'][^"']*locality[^"']*["'][^>]*>([^<]+)<""")


class ClutchSuspiciousEmptyError(Exception):
    """Page 0 returned a 200 OK response but parsed to zero entries.

    Raised when the listing-extraction regexes match nothing on the FIRST
    page. Typical causes: CAPTCHA interstitial, soft-block page, or a
    Clutch HTML layout change that broke the parsers. Distinguishes from
    a genuine end-of-listings state (which only fires on page > 0).
    """


class ClutchAdapter:
    """Clutch.co listing-page adapter. name='clutch:{category_path}'.

    Paginates through `https://clutch.co/{category_path}?page=N`, throttled
    at 4s between pages. Listing-page only — no detail scraping.

    Resilience:
      - Retries 429 / 502 / 503 / 504 up to ``max_retries`` times with
        exponential backoff (``retry_backoff_seconds * 2**n``).
      - Treats 403 as soft-block-suspect; one retry with the same backoff.
      - Raises ``ClutchSuspiciousEmptyError`` when page 0 parses to zero
        entries (could be CAPTCHA / layout drift; the caller should NOT
        treat this as a clean empty pull).
    """

    def __init__(
        self,
        category_path: str,
        http_client: httpx.AsyncClient | None = None,
        throttle_seconds: float = THROTTLE_SECONDS,
        retry_backoff_seconds: float = _DEFAULT_RETRY_BACKOFF_SECONDS,
        max_retries: int = _DEFAULT_MAX_RETRIES,
    ) -> None:
        """category_path: e.g. 'developers/shopify' (no leading/trailing slash).
        http_client: inject a mock in tests to avoid real HTTP calls.
        throttle_seconds: pause between pages; tests pass 0 to skip waits.
        retry_backoff_seconds: base backoff before retrying transient errors.
            Tests pass 0 to skip waits.
        max_retries: how many times to retry 429/503/5xx before raising.
        """
        self.category_path = category_path.strip("/")
        self._http_client = http_client
        self._throttle_seconds = throttle_seconds
        self._retry_backoff_seconds = retry_backoff_seconds
        self._max_retries = max(0, max_retries)

    @property
    def name(self) -> str:
        return f"clutch:{self.category_path}"

    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> httpx.Response:
        """Get ``url`` with retry on transient HTTP errors. Final HTTP error
        bubbles up as the underlying ``HTTPStatusError``.
        """
        last_exc: BaseException | None = None
        for attempt in range(self._max_retries + 1):
            response = await client.get(url)
            status_code = getattr(response, "status_code", 200)
            if status_code in _RETRY_STATUSES or status_code in _SOFT_BLOCK_STATUSES:
                # Capture the exception via raise_for_status (so we always
                # raise the same shape), but don't propagate yet — retry
                # if we have budget.
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    last_exc = exc
                if attempt < self._max_retries:
                    delay = self._retry_backoff_seconds * (2 ** attempt)
                    if delay > 0:
                        await asyncio.sleep(delay)
                    continue
                raise last_exc  # type: ignore[misc]
            response.raise_for_status()
            return response
        # Defensive: should never reach here because the loop always either
        # returns or raises. Keeps the type checker quiet.
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Clutch fetch exhausted without raising")

    async def pull(
        self,
        client_id: str,
        max_companies: int,
        dry_run: bool = False,
        *,
        max_pages: int = 50,
    ) -> list[RawCompanyContact]:
        """Scrape Clutch listing pages until max_companies or max_pages.

        In dry_run mode: no HTTP calls; returns [].

        Raises:
            ClutchSuspiciousEmptyError: page 0 parsed to zero entries.
            httpx.HTTPStatusError: HTTP error after all retries exhausted.
        """
        if dry_run:
            return []

        client_provided = self._http_client is not None
        client = self._http_client or httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        try:
            results: list[RawCompanyContact] = []
            seen_slugs: set[str] = set()

            for page_num in range(max_pages):
                if len(results) >= max_companies:
                    break

                url = f"{CLUTCH_BASE_URL}/{self.category_path}?page={page_num}"
                response = await self._fetch_with_retry(client, url)
                html = response.text

                parsed = _parse_listing_page(html)
                if not parsed:
                    if page_num == 0:
                        # Suspicious: 200 OK + zero entries on the first page.
                        # Could be CAPTCHA, soft-block, or a layout change.
                        # Don't treat as a clean empty pull.
                        raise ClutchSuspiciousEmptyError(
                            f"Clutch first-page extraction yielded 0 entries "
                            f"for {self.name} — likely CAPTCHA interstitial, "
                            f"soft-block page, or a Clutch layout change. "
                            f"URL: {url}"
                        )
                    break  # genuine end of listings

                for entry in parsed:
                    if len(results) >= max_companies:
                        break
                    slug = _extract_profile_slug(entry["profile_url"]) if entry["profile_url"] else entry["name"].lower().strip()
                    if not slug or slug in seen_slugs:
                        continue
                    seen_slugs.add(slug)

                    # Split location into city/state/geography best-effort.
                    # Clutch locations come as "City, ST" or "City, Country".
                    location = entry["location"]
                    city: str | None = None
                    state: str | None = None
                    geography: str | None = None
                    if "," in location:
                        parts = [p.strip() for p in location.split(",", 1)]
                        city = parts[0] or None
                        tail = parts[1] if len(parts) > 1 else ""
                        # If tail is 2-letter US state, set state; else geography
                        if len(tail) == 2 and tail.isalpha():
                            state = tail.upper()
                        else:
                            geography = tail or None
                    elif location:
                        geography = location

                    results.append(
                        RawCompanyContact(
                            company=entry["name"] or slug,
                            company_domain=None,  # listing-page-only; domain resolved downstream
                            company_website=entry["profile_url"] or None,  # Clutch profile URL
                            industry=None,
                            employees=None,
                            revenue_usd=None,
                            city=city,
                            state=state,
                            geography=geography,
                            source=self.name,
                            source_id=slug,
                            raw_data={
                                "name": entry["name"],
                                "profile_url": entry["profile_url"],
                                "location": entry["location"],
                                "page": page_num,
                            },
                        )
                    )

                # Throttle between pages (except after last fetched page)
                if len(results) < max_companies and page_num < max_pages - 1:
                    if self._throttle_seconds > 0:
                        await asyncio.sleep(self._throttle_seconds)

            return results
        finally:
            if not client_provided:
                await client.aclose()


def _extract_profile_slug(profile_url: str) -> str:
    """Return the path segment after /profile/ as a stable source_id."""
    try:
        path = urlparse(profile_url).path  # e.g. "/profile/acme-co"
        slug = path.removeprefix("/profile/").strip("/").split("/")[0]
        return slug or profile_url
    except Exception:
        return profile_url


def _parse_listing_page(html: str) -> list[dict[str, str]]:
    """Extract {name, profile_url, location} triples from a Clutch listing page.

    Pairs by index. Empty string fallback if one list is shorter (matches n8n).
    Returns empty list if no names found.
    """
    names = _NAME_PATTERN.findall(html)
    profile_urls = _PROFILE_URL_PATTERN.findall(html)
    locations = _LOCATION_PATTERN.findall(html)

    max_items = max(len(names), len(profile_urls))
    rows: list[dict[str, str]] = []
    for i in range(max_items):
        name = names[i] if i < len(names) else ""
        profile_url = profile_urls[i] if i < len(profile_urls) else ""
        location = locations[i].strip() if i < len(locations) else ""
        # Require at least a name OR a profile URL
        if not name and not profile_url:
            continue
        rows.append({
            "name": name,
            "profile_url": profile_url,
            "location": location,
        })
    return rows
