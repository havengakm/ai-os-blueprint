"""Scrape Google Maps for a brand/category across a list of postal codes.

⚠ PARKED 2026-04-25. Currently writes 0 rows on every run.

The list-card website extractor (`a[aria-label^="Website"]` selector)
hits zero on every modern Google Maps result card. The website link is
either absent from list cards entirely or behind a different selector;
without DOM inspection we can't tell which. Either way: 100% drop at
the no_website gate.

Discovery (list of `(name, address, gmaps_url)` per ZIP) still works —
that half is salvageable.

Resumption architecture (when an agency-client deployment needs local-
business sourcing): split into three independent stages. Google Maps
becomes discovery-only; a new `scripts/_website_resolver.py` does
Google Search knowledge-panel lookups per `(name, city)` to add the
website column (per the operator's screenshot 2026-04-25 confirming the
knowledge panel reliably surfaces a Website button); the existing
enrichment pipeline runs unchanged. See `memory/INDEX.md` Open Loops.

Reason for parking: gyms / local-business sourcing isn't Clymb's ICP
(operator decision 2026-04-25). The capability is reusable for future
agency-client deployments. Plan 1.5 acceptance pivots to creative_branding.

Two-stage pipeline (current, broken):

1. Playwright visits `google.com/maps/search/{query}+near+{zip}` for each
   postal code. Extracts each visible result card's name / address / website
   / phone. Dedupes by (name, address) across zips.

2. For each unique location, one Claude Sonnet call with `web_search`
   resolves the named decision-maker (owner / franchisee / GM) + their
   LinkedIn URL. Output is normalised to the schema the
   `scripts/ingest_preresolved_contacts.py` ingester expects.

This script is franchise/brand-aware: for F45, Anytime Fitness, OrangeTheory,
etc., each location is typically a separate franchisee with a locally
identifiable owner.

Usage:
    set -a && source .env && set +a
    uv run python scripts/scrape_google_maps.py \\
        --query="F45 Training" \\
        --country="United States" \\
        --niche=fitness_wellness \\
        --zips=90001,90210,92101,94102,94601,95110,95814,93101 \\
        --limit=10 \\
        --output=data/test_contacts_california_f45.csv

Exit codes:
    0  success — CSV written with >= 1 row
    1  partial — wrote fewer than `--limit` rows (still usable)
    2  discovery phase produced zero candidates
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

from playwright.async_api import async_playwright  # noqa: E402

# Reuse the mindbody row helpers (pure functions, zero coupling to Mindbody).
from scripts.scrape_mindbody import (  # noqa: E402
    _parse_claude_json,
    email_from_owner,
    fallback_email,
    normalise_domain,
    resolve_is_match,
    short_name_from_company,
    validate_row,
    write_csv,
)
from scripts._owner_extraction import extract_owner_with_haiku  # noqa: E402
from scripts._website_fetcher import fetch_website_about_text  # noqa: E402

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────────────

GMAPS_SEARCH_URL = "https://www.google.com/maps/search/{query}"
# Viewport-anchored URL forces Google Maps to bias results to the given
# lat/lng/zoom, defeating the client-IP "near me" default.
GMAPS_ANCHORED_URL = "https://www.google.com/maps/search/{query}/@{lat},{lng},{zoom}z"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
FEED_SELECTOR = 'div[role="feed"]'
CARD_SELECTOR = 'div[role="feed"] > div > div[jsaction]'
PAGE_GAP_SECONDS = 2.5
# Post-Phase-2: Haiku has no web_search, ~2-4k input tokens/call. Drop the
# large rate-limit gap — Playwright's 15s per-page timeout is now the
# natural pacing.
CLAUDE_GAP_SECONDS = 2.0
# Haiku 4.5 per CLAUDE.md cost rules.
HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 800


# ── Parsers (pure functions) ─────────────────────────────────────────────────

def build_search_query(query: str, zip_code: str) -> str:
    """URL-ready search slug: `F45 Training near 90001` → quoted."""
    return quote(f"{query} near {zip_code}", safe="")


def dedupe_candidates(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    """Collapse duplicates by (name, address) tuple; preserve first-seen."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for c in candidates:
        key = (
            (c.get("name") or "").strip().lower(),
            (c.get("address") or "").strip().lower(),
        )
        if not key[0]:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


# ── Playwright: Google Maps scrape ───────────────────────────────────────────

async def _scrape_one_zip(
    *,
    browser: Any,
    query: str,
    zip_code: str,
    timeout_ms: int = 30_000,
    scrolls: int = 3,
    anchor: tuple[float, float] | None = None,
    zoom: int = 12,
) -> list[dict[str, str]]:
    """Fetch Google Maps results for one zip code. Returns raw cards.

    If ``anchor`` (lat, lng) is provided, the URL is viewport-anchored so
    Google Maps biases results to the given coordinates. This defeats the
    client-IP "near me" default when scraping foreign regions.

    When anchor is set, the query text is the raw brand/category string
    without "near {zip}" — the viewport does the geo work, and the text
    would otherwise confuse the ranking.
    """
    if anchor is not None:
        lat, lng = anchor
        slug = quote(query, safe="")
        url = GMAPS_ANCHORED_URL.format(query=slug, lat=lat, lng=lng, zoom=zoom)
    else:
        slug = build_search_query(query, zip_code)
        url = GMAPS_SEARCH_URL.format(query=slug)
    context = await browser.new_context(
        user_agent=USER_AGENT,
        locale="en-US",
        viewport={"width": 1400, "height": 1000},
    )
    cards: list[dict[str, str]] = []
    try:
        page = await context.new_page()
        resp = await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        if not resp or resp.status >= 400:
            logger.warning(
                "gmaps fetch failed zip=%s status=%s",
                zip_code, resp.status if resp else None,
            )
            return []

        # Google sometimes shows a consent interstitial; best-effort accept.
        for btn_text in ("Accept all", "I agree", "Reject all"):
            try:
                btn = page.get_by_role("button", name=btn_text)
                if await btn.count() > 0:
                    await btn.first.click(timeout=2_000)
                    await page.wait_for_timeout(1_000)
                    break
            except Exception:
                pass

        # Wait for results feed to mount.
        try:
            await page.wait_for_selector(FEED_SELECTOR, timeout=15_000)
        except Exception:
            logger.info("no feed on zip=%s — likely zero results", zip_code)
            return []

        # Scroll the feed to load more cards. Feed is virtualised so we
        # capture after each scroll.
        for _ in range(scrolls):
            try:
                await page.eval_on_selector(
                    FEED_SELECTOR,
                    "el => el.scrollBy(0, 1800)",
                )
            except Exception:
                break
            await page.wait_for_timeout(1_200)

        # Extract cards. Each card has an <a> whose `aria-label` is the
        # business name. Address, phone, website appear as sibling nodes.
        raw = await page.eval_on_selector_all(
            CARD_SELECTOR,
            """els => els.map(el => {
                const nameAnchor = el.querySelector('a[aria-label]');
                const name = nameAnchor ? nameAnchor.getAttribute('aria-label') : '';
                const href = nameAnchor ? nameAnchor.getAttribute('href') : '';
                // Website link inside the card (if any). Its aria-label
                // usually starts with 'Website'.
                const websiteA = el.querySelector('a[aria-label^="Website"]');
                const website = websiteA ? websiteA.getAttribute('href') : '';
                // Phone: aria-label starts with 'Phone'.
                const phoneSpan = el.querySelector('[aria-label^="Phone"], [data-tooltip="Copy phone number"]');
                const phone = phoneSpan ? (phoneSpan.getAttribute('aria-label') || phoneSpan.textContent || '').replace('Phone: ', '').trim() : '';
                // Address: heuristic — look for text nodes with commas
                // that aren't the name. Google's DOM is noisy, but the
                // address tends to appear in a span class prefixed 'W4Efsd'.
                const spans = [...el.querySelectorAll('div.W4Efsd span, div.W4Efsd')];
                let address = '';
                for (const s of spans) {
                    const t = (s.textContent || '').trim();
                    if (/\\d/.test(t) && t.includes(',') && t !== name) { address = t; break; }
                }
                return { name, href, website, phone, address };
            })""",
        )
    finally:
        await context.close()

    for c in raw:
        if not (c.get("name") or "").strip():
            continue
        cards.append({
            "name": (c.get("name") or "").strip(),
            "website": (c.get("website") or "").strip(),
            "phone": (c.get("phone") or "").strip(),
            "address": (c.get("address") or "").strip(),
            "gmaps_url": ("https://www.google.com" + c.get("href"))
                if (c.get("href") or "").startswith("/maps/") else (c.get("href") or ""),
            "zip_source": zip_code,
        })
    return cards


async def scrape_all_zips(
    *,
    query: str,
    zips: list[str],
    browser: Any,
    zip_coords: dict[str, tuple[float, float]] | None = None,
) -> list[dict[str, str]]:
    """Sequentially scrape each zip; dedupe the combined results.

    ``zip_coords``: optional zip → (lat, lng) map. When provided, each
    scrape is viewport-anchored to the zip's centroid so Google Maps
    returns results near that region regardless of client IP. When
    absent or a zip is missing, the scrape falls back to text-only
    "near {zip}" which is IP-biased.
    """
    all_cards: list[dict[str, str]] = []
    coords = zip_coords or {}
    for zip_code in zips:
        anchor = coords.get(zip_code)
        logger.info(
            "scraping gmaps zip=%s query=%r anchor=%s",
            zip_code, query, anchor,
        )
        cards = await _scrape_one_zip(
            browser=browser, query=query, zip_code=zip_code, anchor=anchor,
        )
        logger.info("  zip=%s got %d cards", zip_code, len(cards))
        all_cards.extend(cards)
        await asyncio.sleep(PAGE_GAP_SECONDS)
    deduped = dedupe_candidates(all_cards)
    logger.info("scrape total: %d raw → %d unique", len(all_cards), len(deduped))
    return deduped


# ── Claude: resolve decision-maker for each location ─────────────────────────

_CLAUDE_SYSTEM = (
    "You are a B2B research analyst. You use the web_search tool to find "
    "the named franchisee / owner / general manager of a local fitness "
    "location. Only return facts that appear on the location's own website "
    "or LinkedIn. Never invent a name. Return strict JSON only, no prose, "
    "no code fences."
)

_CLAUDE_USER_TEMPLATE = """\
Business: {name}
Address: {address}
Country: {country}
Google Maps profile: {gmaps_url}
Known website (may be blank): {website_hint}
Category filter: {category_filter}

Use the web_search tool (at most 3 searches) to locate:
  1. The location's own website domain (franchise page or local site).
  2. The named decision-maker at THIS location: owner / franchisee /
     general manager / head coach. Must be the person who runs this
     specific address, not the global brand CEO.
  3. Their public LinkedIn URL if visible.
  4. Whether the location fits the category filter above.
  5. Any fresh buying-signal at this location (hiring, new class, press).

CATEGORY MATCH RULES (STRICT):
  - is_match=true ONLY if the business's PRIMARY offering matches the category
    filter. Secondary, supplementary, or hybrid offerings do NOT count.
  - is_match=false if the primary offering is something else.
  - Examples for filter = "F45 Training branded franchise location":
      * F45 Training Downtown LA → is_match=true
      * F45 Training San Diego North → is_match=true
      * Some other gym that happens to offer F45-style classes → is_match=false
      * CrossFit / Orangetheory / Anytime Fitness / generic gym → is_match=false
      * Martial arts / BJJ / boxing → is_match=false
      * Hotel gym hosting F45 classes but not an F45 franchise → is_match=false
  - You MUST produce `category_reasoning` describing why is_match is true or
    false. Put the reasoning field first in the JSON.

Return STRICT JSON exactly matching this shape, in this field order, no prose,
no code fences:

{{
  "category_reasoning": "1 short sentence: is the PRIMARY offering a match?",
  "is_match": true | false,
  "domain": "example.com" | null,
  "first_name": "Jane" | null,
  "last_name": "Doe" | null,
  "title": "Owner" | "Franchisee" | "General Manager" | "Head Coach" | null,
  "linkedin_url": "https://..." | null,
  "notes": "1 sentence signal or blank",
  "confidence": 0.0
}}

Rules:
  - domain must be the location's OWN site (or the brand's local-page URL),
    not google, facebook, instagram, yelp, or a directory.
  - first_name + last_name must BOTH be set if you claim a decision-maker.
  - If you cannot find a named decision-maker at this specific location,
    set first_name/last_name/title to null.
  - Never fabricate. Null is always acceptable.
  - confidence reflects your certainty that the returned decision-maker is
    real and currently runs THIS address.
"""


def _extract_text_blocks(response: Any) -> str:
    parts: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts)


def _ensure_anthropic_client(client: Any = None) -> Any:
    if client is not None:
        return client
    from anthropic import Anthropic
    return Anthropic()


def resolve_location_with_claude(
    *,
    candidate: dict[str, str],
    country: str,
    category_filter: str,
    client: Any = None,
) -> dict[str, Any]:
    client = _ensure_anthropic_client(client)
    user_message = _CLAUDE_USER_TEMPLATE.format(
        name=candidate.get("name", ""),
        address=candidate.get("address", ""),
        country=country,
        gmaps_url=candidate.get("gmaps_url", ""),
        website_hint=candidate.get("website", ""),
        category_filter=category_filter,
    )
    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=MAX_TOKENS,
        system=_CLAUDE_SYSTEM,
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
        }],
        messages=[{"role": "user", "content": user_message}],
    )
    raw_text = _extract_text_blocks(response)
    parsed = _parse_claude_json(raw_text) or {}
    notes = (parsed.get("notes") or "").strip()
    category_reasoning = (parsed.get("category_reasoning") or "").strip()
    is_match, override_reason = resolve_is_match(
        parsed.get("is_match"), category_reasoning, notes,
    )
    if override_reason:
        notes = (notes + f" [is_match overridden: {override_reason}]").strip()
    out = {
        "domain": normalise_domain(parsed.get("domain")),
        "first_name": parsed.get("first_name") or None,
        "last_name": parsed.get("last_name") or None,
        "title": parsed.get("title") or None,
        "linkedin_url": parsed.get("linkedin_url") or None,
        "is_match": is_match,
        "category_reasoning": category_reasoning,
        "notes": notes,
        "confidence": float(parsed.get("confidence") or 0.0),
        "raw_text": raw_text[:500],
    }
    if out["domain"] in {
        "google.com", "facebook.com", "instagram.com",
        "yelp.com", "linkedin.com", "mindbodyonline.com",
    }:
        out["domain"] = None
    return out


# ── Row builder ──────────────────────────────────────────────────────────────

def build_row(
    *,
    candidate: dict[str, str],
    resolved: dict[str, Any],
    country: str,
    niche: str,
) -> dict[str, str] | None:
    domain = resolved.get("domain")
    if not domain:
        return None

    name = candidate.get("name", "")
    short = short_name_from_company(name)
    first = (resolved.get("first_name") or "").strip() or None
    last = (resolved.get("last_name") or "").strip() or None
    title = (resolved.get("title") or "").strip() or None
    linkedin_url = (resolved.get("linkedin_url") or "").strip()

    notes_bits: list[str] = [
        f"Google Maps source: {candidate.get('gmaps_url','')}",
        f"Address: {candidate.get('address','')}",
        f"Country: {country}",
    ]
    if candidate.get("phone"):
        notes_bits.append(f"Phone: {candidate['phone']}")
    extra = (resolved.get("notes") or "").strip()
    if extra:
        notes_bits.append(extra)

    if first:
        email = email_from_owner(first, domain)
        notes_bits.append("Email guessed firstname@domain — verify before send.")
    else:
        email = fallback_email(domain)
        first = "Owner"
        notes_bits.append(
            "No named decision-maker found, using generic info@; "
            "placeholder first_name='Owner'."
        )

    row = {
        "company": name,
        "domain": domain,
        "linkedin_url": linkedin_url,
        "first_name": first,
        "last_name": last or "",
        "title": title or "",
        "email": email or "",
        "short_company_name": short,
        "niche": niche,
        "notes": " | ".join(notes_bits),
    }
    return row


# ── Orchestrator ─────────────────────────────────────────────────────────────

async def run(
    *,
    query: str,
    country: str,
    niche: str,
    zips: list[str],
    limit: int,
    output: Path,
    category_filter: str,
    zip_coords: dict[str, tuple[float, float]] | None = None,
    min_candidates: int = 5,
) -> tuple[int, list[dict[str, str]]]:
    """Scrape then resolve. Pipeline per candidate:
      1. Use the candidate's `website` field (already captured from the
         Google Maps card) as the domain seed. Skip candidates without a
         website — they're low-signal for a cold-email workflow anyway.
      2. Playwright fetches the studio's About/Team text via
         _website_fetcher.fetch_website_about_text.
      3. Haiku 4.5 extracts owner + category match from the scraped
         text (no web_search tool).

    Browser stays open throughout so Playwright contexts warm-reuse.
    """
    client = _ensure_anthropic_client()
    rows: list[dict[str, str]] = []
    attempted = 0
    # Plan 1.5 scraper Fix 5: count drops at every gate so the operator
    # can see WHERE the scrape lost candidates.
    drops: dict[str, int] = {
        "no_website": 0,
        "url_normalise": 0,
        "site_unreachable": 0,
        "haiku_failed": 0,
        "category_mismatch": 0,
        "no_domain_after": 0,
        "missing_fields": 0,
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            candidates = await scrape_all_zips(
                query=query, zips=zips, browser=browser,
                zip_coords=zip_coords,
            )

            # Plan 1.5 scraper Fix 3: under-target candidate count is a
            # warning, not an abort. Returns whatever was found instead of
            # producing an empty CSV. Operator can decide to re-run with a
            # broader query if needed.
            if len(candidates) < min_candidates:
                logger.warning(
                    "candidate scrape under target: %d < %d for query=%r — "
                    "proceeding with what was found",
                    len(candidates), min_candidates, query,
                )

            for candidate in candidates:
                if len(rows) >= limit:
                    break
                attempted += 1
                logger.info(
                    "[%d/%d] resolving %s  (%s)",
                    attempted, limit, candidate["name"],
                    candidate.get("address", ""),
                )

                # --- Step 1: domain from card.website (or skip) ---
                website_hint = (candidate.get("website") or "").strip()
                if not website_hint:
                    drops["no_website"] += 1
                    logger.info(
                        "skipped %s — no website on Google Maps card",
                        candidate["name"],
                    )
                    continue
                domain = normalise_domain(website_hint)
                if not domain:
                    drops["url_normalise"] += 1
                    logger.info(
                        "skipped %s — website didn't normalise: %r",
                        candidate["name"], website_hint,
                    )
                    continue

                # --- Step 2: fetch About/Team text ---
                website_text = await fetch_website_about_text(
                    browser=browser,
                    domain=domain,
                    user_agent=USER_AGENT,
                )
                if not website_text.strip():
                    drops["site_unreachable"] += 1
                    logger.info(
                        "skipped %s — site empty/unreachable (%s)",
                        candidate["name"], domain,
                    )
                    continue

                # --- Step 3: Haiku extract ---
                # Plan 1.5 scraper Fix 4: dropped the 5-consecutive-failure
                # kill switch. Single Haiku failures log + skip; loop never
                # aborts on transient errors.
                try:
                    extraction = extract_owner_with_haiku(
                        client=client,
                        studio_name=candidate["name"],
                        website_text=website_text,
                        category_filter=category_filter,
                        country=country,
                        known_domain=domain,
                    )
                except Exception as e:
                    drops["haiku_failed"] += 1
                    logger.warning(
                        "haiku call failed location=%s err=%s — skipping",
                        candidate["name"], e,
                    )
                    time.sleep(CLAUDE_GAP_SECONDS)
                    continue

                if not extraction.is_match:
                    drops["category_mismatch"] += 1
                    logger.info(
                        "skipped %s — category mismatch (%s)",
                        candidate["name"],
                        extraction.category_reasoning or "(no reason)",
                    )
                    time.sleep(CLAUDE_GAP_SECONDS)
                    continue

                resolved = {
                    "domain": extraction.domain,
                    "first_name": extraction.first_name,
                    "last_name": extraction.last_name,
                    "title": extraction.title,
                    "linkedin_url": extraction.linkedin_url,
                    "is_match": extraction.is_match,
                    "notes": extraction.notes,
                    "confidence": extraction.confidence,
                }
                row = build_row(
                    candidate=candidate,
                    resolved=resolved,
                    country=country,
                    niche=niche,
                )
                if row is None:
                    drops["no_domain_after"] += 1
                    logger.info(
                        "skipped %s — no usable domain after extraction",
                        candidate["name"],
                    )
                    time.sleep(CLAUDE_GAP_SECONDS)
                    continue

                missing = validate_row(row)
                if missing:
                    drops["missing_fields"] += 1
                    logger.info(
                        "skipped %s — missing fields: %s",
                        candidate["name"], missing,
                    )
                    continue
                rows.append(row)
                logger.info(
                    "  OK %s → %s <%s>",
                    row["company"], row.get("first_name") or "?", row["email"],
                )
                if len(rows) < limit:
                    time.sleep(CLAUDE_GAP_SECONDS)
        finally:
            await browser.close()

    # Plan 1.5 scraper Fix 5: drop summary so operator sees WHERE the loss
    # happened, not just the final return count.
    logger.info(
        "scrape complete: attempted=%d returned=%d drops=%s",
        attempted, len(rows),
        ", ".join(f"{k}={v}" for k, v in drops.items() if v > 0) or "(none)",
    )
    write_csv(rows, output)
    exit_code = 0 if len(rows) >= limit else (0 if rows else 2)
    logger.info(
        "wrote %d rows → %s (target=%d, attempted=%d)",
        len(rows), output, limit, attempted,
    )
    return exit_code, rows


# ── CLI ──────────────────────────────────────────────────────────────────────

# Centroid lat/lng for the CA zip codes used in the Client-Zero portability
# test. Extend this dict (or load from an external CSV) to support more
# regions. Viewport anchor defeats Google Maps' "near me" IP-bias when the
# scraping host is in a different country.
_CA_ZIP_COORDS: dict[str, tuple[float, float]] = {
    "90001": (33.9731, -118.2479),  # South LA
    "90210": (34.0901, -118.4065),  # Beverly Hills
    "90291": (33.9936, -118.4695),  # Venice
    "92101": (32.7215, -117.1665),  # Downtown San Diego
    "92614": (33.6880, -117.8152),  # Irvine
    "94102": (37.7793, -122.4193),  # SF - Civic Center
    "94301": (37.4447, -122.1603),  # Palo Alto
    "94601": (37.7771, -122.2213),  # Oakland - Fruitvale
    "95110": (37.3541, -121.9094),  # San Jose
    "95814": (38.5787, -121.4924),  # Sacramento
    "93101": (34.4187, -119.7081),  # Santa Barbara
}


def _parse_zip_coord_file(path: Path) -> dict[str, tuple[float, float]]:
    """Load additional zip→lat/lng pairs from a 3-column CSV
    (zip,lat,lng). Lines starting with # are ignored."""
    out: dict[str, tuple[float, float]] = {}
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) < 3:
                continue
            z = parts[0].strip()
            try:
                lat = float(parts[1])
                lng = float(parts[2])
            except ValueError:
                continue
            out[z] = (lat, lng)
    return out


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape Google Maps for a brand/category across postal codes + "
            "resolve decision-makers via Claude web_search."
        ),
    )
    parser.add_argument("--query", required=True, help='e.g. "F45 Training"')
    parser.add_argument("--country", required=True)
    parser.add_argument("--niche", default="fitness_wellness")
    parser.add_argument(
        "--zips", required=True,
        help="Comma-separated postal codes (e.g. 90001,90210,92101).",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--category-filter",
        default=None,
        help=(
            "Plain-language description; defaults to the --query itself. "
            "Claude uses this to reject mis-tagged results."
        ),
    )
    parser.add_argument("--min-candidates", type=int, default=5)
    parser.add_argument(
        "--zip-coords",
        default=None,
        help=(
            "Optional path to a CSV of zip,lat,lng rows. Merges with the "
            "built-in California coord map. When a zip has coordinates, "
            "the Google Maps URL is viewport-anchored to defeat IP-bias."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv or sys.argv[1:])
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        return 2

    zips = [z.strip() for z in args.zips.split(",") if z.strip()]
    if not zips:
        print("ERROR: --zips produced empty list.", file=sys.stderr)
        return 2

    category_filter = args.category_filter or args.query

    output = Path(args.output)
    if not output.is_absolute():
        output = _REPO_ROOT / output

    zip_coords = dict(_CA_ZIP_COORDS)
    if args.zip_coords:
        extra_path = Path(args.zip_coords)
        if not extra_path.is_absolute():
            extra_path = _REPO_ROOT / extra_path
        zip_coords.update(_parse_zip_coord_file(extra_path))

    exit_code, rows = asyncio.run(run(
        query=args.query,
        country=args.country,
        niche=args.niche,
        zips=zips,
        limit=args.limit,
        output=output,
        category_filter=category_filter,
        zip_coords=zip_coords,
    ))

    print(
        f"scrape complete: {len(rows)} rows written to {output} "
        f"(exit={exit_code})"
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
