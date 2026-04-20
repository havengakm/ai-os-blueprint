"""Clutch.co directory adapter — company-level listing scrape.

Ports the n8n workflow `clutch-shopify-scraper.json` (listing-page only, no
detail-page scraping). Downstream stages (Task 9.5 identity lookup) resolve
company_domain when needed via company-name lookup on Apollo/Hunter.

Supports any Clutch category — parameterise via `category_path` (e.g.
'developers/shopify', 'agencies/digital-marketing').
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

# Extraction patterns ported verbatim from the n8n workflow (see
# clutch-shopify-scraper.json parse-companies node).
_NAME_PATTERN = re.compile(r'"name"\s*:\s*"([^"]+)"')
_PROFILE_URL_PATTERN = re.compile(r"""href=["'](https?://clutch\.co/profile/[^"']+)["']""")
_LOCATION_PATTERN = re.compile(r"""class=["'][^"']*locality[^"']*["'][^>]*>([^<]+)<""")


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


class ClutchAdapter:
    """Clutch.co listing-page adapter. name='clutch:{category_path}'.

    Paginates through `https://clutch.co/{category_path}?page=N`, throttled
    at 4s between pages. Listing-page only — no detail scraping.
    """

    def __init__(
        self,
        category_path: str,
        http_client: httpx.AsyncClient | None = None,
        throttle_seconds: float = THROTTLE_SECONDS,
    ) -> None:
        """category_path: e.g. 'developers/shopify' (no leading/trailing slash).
        http_client: inject a mock in tests to avoid real HTTP calls.
        throttle_seconds: pause between pages; tests pass 0 to skip waits.
        """
        self.category_path = category_path.strip("/")
        self._http_client = http_client
        self._throttle_seconds = throttle_seconds

    @property
    def name(self) -> str:
        return f"clutch:{self.category_path}"

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
                response = await client.get(url)
                response.raise_for_status()
                html = response.text

                parsed = _parse_listing_page(html)
                if not parsed:
                    break  # empty page = end of listings

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
