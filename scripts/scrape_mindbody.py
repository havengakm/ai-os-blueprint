"""Scrape Mindbody fitness-studio directory → pre-resolved contacts CSV.

Two-stage pipeline:

1. Playwright-scrape the Mindbody `/explore/fitness/studios-{city}` directory
   to collect studio name + Mindbody profile URL for a given city.

2. For each studio, ask Claude Sonnet (with the `web_search` server tool)
   to resolve the studio's own website domain and its named
   decision-maker (owner / founder / GM / head coach). Output is normalised
   to the schema the `scripts/ingest_preresolved_contacts.py` ingester
   expects.

This script is an MVP portability tester. It is intentionally modest:
  - One directory page per run. Multi-city support is handled by running
    the script once per city and concatenating.
  - No retries on Claude calls (every call is billed — retries multiply spend).
  - Zero fabrication. If a decision-maker cannot be resolved, we fall back
    to `info@{domain}` and mark the row in `notes`.
  - If the directory page yields fewer than `--min-studios` studios, the
    script exits 2. Empty CSV is better than fake CSV.

Schema (matches scripts/ingest_preresolved_contacts.py header):
    company, domain, linkedin_url, first_name, last_name,
    title, email, short_company_name, niche, notes

Usage:
    set -a && source .env && set +a
    uv run python scripts/scrape_mindbody.py \\
        --city-slug=cape-town-wc-za \\
        --output=data/test_contacts_fitness_wellness_mvp.csv \\
        --niche=fitness_wellness \\
        --limit=10

Exit codes:
    0  success — CSV written with >= 1 row
    2  directory fetch failed or produced zero studios
    1  partial — wrote fewer than `--limit` rows (still usable)
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

from playwright.async_api import async_playwright  # noqa: E402

from scripts._owner_extraction import (  # noqa: E402
    HAIKU_MODEL as _EXTRACTION_HAIKU_MODEL,  # re-exported for tests
    OwnerExtractionResult,
    extract_owner_with_haiku,
)
from scripts._website_fetcher import fetch_website_about_text  # noqa: E402

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────────────

MINDBODY_BASE = "https://www.mindbodyonline.com"
DIRECTORY_URL_TEMPLATE = MINDBODY_BASE + "/explore/fitness/studios-{city_slug}"
LOCATION_ANCHOR_SELECTOR = 'a[href*="/explore/locations/"]'

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
PAGE_GAP_SECONDS = 2.5
# Post-Phase-2: Haiku has no web_search, ~2-4k input tokens/call.
# Playwright's 15s per-page timeout is now the natural pacing.
CLAUDE_GAP_SECONDS = 2.0
# Haiku 4.5 per CLAUDE.md cost rules.
HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 800

CSV_FIELDNAMES = [
    "company", "domain", "linkedin_url", "first_name", "last_name",
    "title", "email", "short_company_name", "niche", "notes",
]


# ── Parsers (unit-tested — pure functions, no network) ───────────────────────

def _normalise_mindbody_href(href: str) -> str:
    """Return an absolute Mindbody profile URL for a possibly-relative href."""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return MINDBODY_BASE + href
    return MINDBODY_BASE + "/" + href


_LOCATION_RE = re.compile(r'href="(/explore/locations/[^"]+)"', re.IGNORECASE)


def parse_directory_studios(html: str) -> list[dict[str, str]]:
    """Pull studio-profile links from a Mindbody directory HTML blob.

    Static-HTML parser: used by tests against a fixture so we can assert the
    shape without hitting the live site. The live code path uses Playwright's
    DOM query, which handles hydrated markup better, but this parser covers
    the server-rendered subset.

    Returns a list of {"name": ..., "mindbody_url": ..., "slug": ...} dicts.
    Duplicates (same slug) are collapsed; order is preserved.
    """
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for m in _LOCATION_RE.finditer(html):
        path = m.group(1)
        slug = path.rsplit("/", 1)[-1]
        if slug in seen:
            continue
        seen.add(slug)
        # Derive a fallback name from the slug; the Playwright path will
        # override this with the real anchor text when available.
        name = slug.replace("-", " ").title()
        out.append({
            "name": name,
            "mindbody_url": MINDBODY_BASE + path,
            "slug": slug,
        })
    return out


# normalise_domain + resolve_is_match now live in scripts._scrape_common so
# both scrapers and _owner_extraction can share them without a circular
# import. Re-exported here for backward compatibility with test + caller
# code that imports from scripts.scrape_mindbody.
from scripts._scrape_common import (  # noqa: E402
    normalise_domain,
    resolve_is_match,
)


def short_name_from_company(company: str) -> str:
    """Drop common legal suffixes for the mid-sentence short form."""
    s = re.sub(
        r"\s*(?:\(Pty\)\s*Ltd|Pty\s*Ltd|\(Pty\)|Ltd|Inc\.?|LLC|CC)\.?\s*$",
        "",
        company,
        flags=re.IGNORECASE,
    )
    return s.strip()


def email_from_owner(first_name: str | None, domain: str | None) -> str | None:
    """Best-effort `firstname@domain` guess. None if either field missing."""
    if not first_name or not domain:
        return None
    local = re.sub(r"[^a-z]", "", first_name.lower())
    if not local:
        return None
    return f"{local}@{domain}"


def fallback_email(domain: str | None) -> str | None:
    """Generic `info@domain` fallback when no named owner is known."""
    if not domain:
        return None
    return f"info@{domain}"


def validate_row(row: dict[str, str]) -> list[str]:
    """Return list of missing-field names for a CSV row. Empty = valid."""
    required = ["company", "domain", "email", "niche"]
    missing: list[str] = []
    for k in required:
        if not (row.get(k) or "").strip():
            missing.append(k)
    return missing


# ── Playwright: directory scrape ──────────────────────────────────────────────

async def scrape_directory(
    city_slug: str,
    *,
    browser: Any,
    timeout_ms: int = 25_000,
) -> list[dict[str, str]]:
    """Live-scrape the Mindbody city directory. Returns studio list."""
    url = DIRECTORY_URL_TEMPLATE.format(city_slug=city_slug)
    context = await browser.new_context(user_agent=USER_AGENT)
    try:
        page = await context.new_page()
        resp = await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        if not resp or resp.status >= 400:
            logger.warning(
                "directory fetch failed city_slug=%s status=%s",
                city_slug, resp.status if resp else None,
            )
            return []

        try:
            await page.wait_for_selector(LOCATION_ANCHOR_SELECTOR, timeout=10_000)
        except Exception:
            logger.info(
                "no location anchors appeared within 10s city_slug=%s",
                city_slug,
            )

        # Mindbody cards wrap a child `<h3>` with the clean studio name.
        # The anchor's full innerText includes categories + address + reviews
        # + distance, so we prefer the h3 when present and fall back to the
        # slug-derived title only if no h3 exists.
        anchors = await page.eval_on_selector_all(
            LOCATION_ANCHOR_SELECTOR,
            """els => els.map(a => {
                const h = a.querySelector('h3, h2');
                return {
                    href: a.getAttribute('href'),
                    text: h ? (h.innerText || '').trim() : ''
                };
            })""",
        )
    finally:
        await context.close()

    seen: set[str] = set()
    studios: list[dict[str, str]] = []
    for a in anchors:
        href = a.get("href") or ""
        if "/explore/locations/" not in href:
            continue
        abs_url = _normalise_mindbody_href(href)
        slug = abs_url.rstrip("/").rsplit("/", 1)[-1]
        if slug in seen:
            continue
        seen.add(slug)
        name = (a.get("text") or "").strip() or slug.replace("-", " ").title()
        studios.append({
            "name": name,
            "mindbody_url": abs_url,
            "slug": slug,
        })
    return studios


# ── Playwright: extract studio's own website from Mindbody profile ───────────

# Hosts that appear on every Mindbody profile but aren't the studio's own site.
_NON_STUDIO_HOSTS = {
    "mindbodyonline.com", "www.mindbodyonline.com",
    "facebook.com", "www.facebook.com",
    "instagram.com", "www.instagram.com",
    "twitter.com", "x.com", "www.twitter.com", "www.x.com",
    "yelp.com", "www.yelp.com",
    "google.com", "maps.google.com", "www.google.com",
    "linkedin.com", "www.linkedin.com", "za.linkedin.com",
    "tiktok.com", "www.tiktok.com",
    "youtube.com", "www.youtube.com",
    "apple.com", "apps.apple.com",
    "play.google.com",
}


def _host_of(url: str) -> str:
    """Return the hostname in lowercase; empty when url has no scheme."""
    if not url:
        return ""
    m = re.match(r"https?://([^/?#]+)", url, re.IGNORECASE)
    return m.group(1).lower() if m else ""


async def extract_mindbody_profile_website(
    *,
    browser: Any,
    mindbody_url: str,
    timeout_ms: int = 20_000,
    user_agent: str = USER_AGENT,
) -> str | None:
    """Navigate to a Mindbody location profile; return the studio's own
    external website URL. None when no plausible link found.

    Heuristic: the profile page has a "Visit website" anchor, but the
    selector varies across Mindbody templates. We collect all external
    anchors, filter out social / directory / store-listing hosts, and
    return the first remaining one. If zero remain, return None.
    """
    ctx = await browser.new_context(user_agent=user_agent)
    try:
        page = await ctx.new_page()
        try:
            resp = await page.goto(
                mindbody_url, timeout=timeout_ms, wait_until="domcontentloaded",
            )
        except Exception as e:
            logger.debug("mindbody profile nav failed %s: %s", mindbody_url, e)
            return None
        if not resp or resp.status >= 400:
            return None

        anchors = await page.eval_on_selector_all(
            "a[href^='http']",
            "els => els.map(a => a.getAttribute('href'))",
        )
    finally:
        await ctx.close()

    for href in anchors or []:
        host = _host_of(href or "")
        if not host:
            continue
        if host in _NON_STUDIO_HOSTS:
            continue
        # Filter sub-paths of the known Mindbody host variants.
        if host.endswith(".mindbodyonline.com"):
            continue
        return href  # keep first match — ordering reflects page layout
    return None


# ── Claude: resolve website + owner ───────────────────────────────────────────

_CLAUDE_SYSTEM = (
    "You are a B2B research analyst. You use the web_search tool to find the "
    "official website of a fitness/wellness studio and identify its named "
    "owner / founder / general manager / head coach. Only return facts that "
    "appear on the studio's own website or LinkedIn. Never invent a name. "
    "Return strict JSON only, no prose, no code fences."
)

_CLAUDE_USER_TEMPLATE = """\
Studio name: {studio_name}
City: {city}
Country: {country}
Category filter: {category_filter}
Mindbody profile: {mindbody_url}

Use the web_search tool (at most 3 searches) to locate:
  1. The studio's own official website (domain).
  2. The named decision-maker: owner, founder, GM, or head coach.
  3. Their public LinkedIn URL if visible.
  4. Whether this studio fits the category filter above.
  5. Any fresh buying-signal you notice (hiring, new location, recent press).

CATEGORY MATCH RULES (STRICT):
  - is_match=true ONLY if the business's PRIMARY offering matches the category
    filter. Secondary, supplementary, side, or hybrid offerings do NOT count.
  - is_match=false if the primary offering is something else, even if the
    business also teaches what the filter asks for.
  - Examples for filter = "pilates or yoga studio":
      * Dedicated pilates studio  → is_match=true
      * Dedicated yoga studio     → is_match=true
      * Yoga + strength hybrid where yoga is core → is_match=true
      * Ballet company that offers pilates on the side → is_match=false
      * Body sculpting / lymphatic drainage studio → is_match=false
      * IV therapy clinic → is_match=false
      * F45 / CrossFit / general fitness gym → is_match=false
  - You MUST produce `category_reasoning` describing why is_match is true or
    false BEFORE you emit is_match. Put the reasoning field first in the JSON.

Return STRICT JSON exactly matching this shape, in this field order, no prose,
no code fences:

{{
  "category_reasoning": "1 short sentence: is the PRIMARY offering a match?",
  "is_match": true | false,
  "domain": "example.com" | null,
  "first_name": "Jane" | null,
  "last_name": "Doe" | null,
  "title": "Founder" | "Owner" | "General Manager" | "Head Coach" | null,
  "linkedin_url": "https://..." | null,
  "notes": "1 sentence signal or blank",
  "confidence": 0.0
}}

Rules:
  - domain must be the studio's OWN site, not mindbody, facebook, instagram, yelp, or a directory.
  - first_name + last_name must both be set if you claim a decision-maker.
  - If you cannot find a named decision-maker, set first_name/last_name/title to null.
  - Never fabricate. Null is always acceptable.
  - confidence reflects your certainty that the returned decision-maker is real and current.
"""


def _parse_claude_json(raw_text: str) -> dict[str, Any] | None:
    """Strip optional ```json fences and parse. None on failure."""
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# resolve_is_match is now re-exported from scripts._scrape_common at the top
# of this file; the implementation lives there to avoid circular imports
# with _owner_extraction.py. Historical duplicate definition removed.


def _extract_text_blocks(response: Any) -> str:
    """Concatenate all `text`-typed blocks from a Claude response."""
    parts: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts)


def _ensure_anthropic_client(client: Any = None) -> Any:
    """Lazy-import and construct an Anthropic sync client."""
    if client is not None:
        return client
    from anthropic import Anthropic
    return Anthropic()


def resolve_studio_with_claude(
    *,
    studio_name: str,
    mindbody_url: str,
    city: str,
    client: Any = None,
    country: str = "South Africa",
    category_filter: str = "any fitness or wellness studio",
) -> dict[str, Any]:
    """One Claude Sonnet call with web_search → resolved fields.

    Returns a dict with:
      domain, first_name, last_name, title, linkedin_url, is_match, notes,
      confidence, raw_text (for debugging)

    On parse failure, everything is None / empty and notes contains the
    raw_text head for a human to inspect.
    """
    client = _ensure_anthropic_client(client)
    user_message = _CLAUDE_USER_TEMPLATE.format(
        studio_name=studio_name,
        city=city,
        country=country,
        category_filter=category_filter,
        mindbody_url=mindbody_url,
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
        "first_name": (parsed.get("first_name") or None),
        "last_name": (parsed.get("last_name") or None),
        "title": (parsed.get("title") or None),
        "linkedin_url": (parsed.get("linkedin_url") or None),
        "is_match": is_match,
        "category_reasoning": category_reasoning,
        "notes": notes,
        "confidence": float(parsed.get("confidence") or 0.0),
        "raw_text": raw_text[:500],
    }
    # Reject obvious non-studio domains.
    if out["domain"] in {
        "mindbodyonline.com", "facebook.com", "instagram.com",
        "yelp.com", "linkedin.com", "google.com",
    }:
        out["domain"] = None
    return out


# ── Row builder ──────────────────────────────────────────────────────────────

def build_row(
    *,
    studio_name: str,
    mindbody_url: str,
    resolved: dict[str, Any],
    city: str,
    niche: str,
) -> dict[str, str] | None:
    """Combine directory + Claude output → one CSV-ready dict.

    Returns None when we cannot produce a row with at minimum a company +
    domain + email (no domain = no email-guessable path = skip).
    """
    domain = resolved.get("domain")
    if not domain:
        return None

    short = short_name_from_company(studio_name)
    first = (resolved.get("first_name") or "").strip() or None
    last = (resolved.get("last_name") or "").strip() or None
    title = (resolved.get("title") or "").strip() or None
    linkedin_url = (resolved.get("linkedin_url") or "").strip()

    notes_bits: list[str] = [f"Mindbody source: {mindbody_url}", f"City: {city}"]
    extra = (resolved.get("notes") or "").strip()
    if extra:
        notes_bits.append(extra)

    if first:
        email = email_from_owner(first, domain)
        notes_bits.append("Email guessed firstname@domain — verify before send.")
    else:
        email = fallback_email(domain)
        first = "Owner"  # ingester requires first_name; flag via notes.
        notes_bits.append(
            "No named decision-maker found, using generic info@; "
            "placeholder first_name='Owner'."
        )

    row = {
        "company": studio_name,
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


# ── CSV writer ───────────────────────────────────────────────────────────────

def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in CSV_FIELDNAMES})


# ── Orchestrator ─────────────────────────────────────────────────────────────

async def run(
    *,
    city_slug: str,
    city_name: str,
    niche: str,
    limit: int,
    output: Path,
    min_studios: int = 5,
    country: str = "South Africa",
    category_filter: str = "any fitness or wellness studio",
) -> tuple[int, list[dict[str, str]]]:
    """Returns (exit_code, rows).

    Pipeline per studio:
      1. Playwright navigates the Mindbody profile → extracts the
         studio's own-website anchor.
      2. Playwright follows the website → fetches About/Team text
         (via _website_fetcher.fetch_website_about_text).
      3. Haiku 4.5 extracts owner + category match from the scraped
         text (no web_search tool; much cheaper than the prior
         Sonnet+web_search path).

    Browser is kept open through the whole loop so Playwright sessions
    warm-reuse chromium instead of cold-starting per contact.
    """
    client = _ensure_anthropic_client()
    rows: list[dict[str, str]] = []
    attempted = 0
    # Plan 1.5 scraper Fix 5: count drops at every gate so the operator
    # can see WHERE the scrape lost candidates, not just how many returned.
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
            studios = await scrape_directory(city_slug, browser=browser)
            logger.info(
                "directory scrape: %d studios for %s",
                len(studios), city_slug,
            )
            if len(studios) < min_studios:
                logger.error(
                    "too few studios (%d < %d) for city_slug=%s — aborting",
                    len(studios), min_studios, city_slug,
                )
                return 2, []

            for studio in studios:
                if len(rows) >= limit:
                    break
                attempted += 1
                logger.info(
                    "[%d/%d] resolving %s",
                    attempted, limit, studio["name"],
                )

                # --- Step 1: extract the studio's own website URL ---
                website_url = await extract_mindbody_profile_website(
                    browser=browser,
                    mindbody_url=studio["mindbody_url"],
                )
                if not website_url:
                    drops["no_website"] += 1
                    logger.info(
                        "skipped %s — no external website link on Mindbody profile",
                        studio["name"],
                    )
                    continue
                domain = normalise_domain(website_url)
                if not domain:
                    drops["url_normalise"] += 1
                    logger.info(
                        "skipped %s — website URL didn't normalise: %r",
                        studio["name"], website_url,
                    )
                    continue

                # --- Step 2: fetch the studio's About/Team page text ---
                website_text = await fetch_website_about_text(
                    browser=browser,
                    domain=domain,
                    user_agent=USER_AGENT,
                )
                if not website_text.strip():
                    drops["site_unreachable"] += 1
                    logger.info(
                        "skipped %s — studio site empty/unreachable (%s)",
                        studio["name"], domain,
                    )
                    continue

                # --- Step 3: Haiku extraction (no web_search) ---
                # Plan 1.5 scraper Fix 4: dropped the 5-consecutive-failure
                # kill switch. Single Haiku failures are logged + skipped;
                # the loop never aborts the whole batch on transient errors.
                try:
                    extraction = extract_owner_with_haiku(
                        client=client,
                        studio_name=studio["name"],
                        website_text=website_text,
                        category_filter=category_filter,
                        country=country,
                        known_domain=domain,
                    )
                except Exception as e:
                    drops["haiku_failed"] += 1
                    logger.warning(
                        "haiku call failed studio=%s err=%s — skipping",
                        studio["name"], e,
                    )
                    time.sleep(CLAUDE_GAP_SECONDS)
                    continue

                if not extraction.is_match:
                    drops["category_mismatch"] += 1
                    logger.info(
                        "skipped %s — doesn't match category filter (%s)",
                        studio["name"], extraction.category_reasoning or "(no reason)",
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
                    studio_name=studio["name"],
                    mindbody_url=studio["mindbody_url"],
                    resolved=resolved,
                    city=city_name,
                    niche=niche,
                )
                if row is None:
                    drops["no_domain_after"] += 1
                    logger.info(
                        "skipped %s — no usable domain after extraction",
                        studio["name"],
                    )
                    time.sleep(CLAUDE_GAP_SECONDS)
                    continue

                missing = validate_row(row)
                if missing:
                    drops["missing_fields"] += 1
                    logger.info(
                        "skipped %s — missing required fields: %s",
                        studio["name"], missing,
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

_CITY_META_BY_SLUG: dict[str, dict[str, str]] = {
    "cape-town-wc-za":   {"name": "Cape Town",    "country": "South Africa"},
    "johannesburg-gp-za":{"name": "Johannesburg", "country": "South Africa"},
    "durban-kzn-za":     {"name": "Durban",       "country": "South Africa"},
    "stellenbosch-wc-za":{"name": "Stellenbosch", "country": "South Africa"},
    "pretoria-gp-za":    {"name": "Pretoria",     "country": "South Africa"},
    "austin-tx-us":      {"name": "Austin",       "country": "United States"},
    "los-angeles-ca-us": {"name": "Los Angeles",  "country": "United States"},
    "new-york-ny-us":    {"name": "New York",     "country": "United States"},
}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape Mindbody fitness-studio directory + resolve "
            "decision-makers via Claude web_search."
        ),
    )
    parser.add_argument("--city-slug", default="cape-town-wc-za")
    parser.add_argument("--city-name", default=None)
    parser.add_argument("--niche", default="fitness_wellness")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--output",
        default="data/test_contacts_fitness_wellness_mvp.csv",
    )
    parser.add_argument("--min-studios", type=int, default=5)
    parser.add_argument(
        "--country",
        default=None,
        help="Country name used in Claude prompt (overrides slug default).",
    )
    parser.add_argument(
        "--category-filter",
        default="any fitness or wellness studio",
        help=(
            "Plain-language description of which studios to keep. "
            'e.g. "pilates or yoga studio" — studios that do not match '
            "are skipped."
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

    meta = _CITY_META_BY_SLUG.get(args.city_slug, {})
    city_name = args.city_name or meta.get("name") or (
        args.city_slug.replace("-", " ").title()
    )
    country = args.country or meta.get("country") or "Unknown"

    output = Path(args.output)
    if not output.is_absolute():
        output = _REPO_ROOT / output

    exit_code, rows = asyncio.run(run(
        city_slug=args.city_slug,
        city_name=city_name,
        niche=args.niche,
        limit=args.limit,
        country=country,
        category_filter=args.category_filter,
        output=output,
        min_studios=args.min_studios,
    ))

    print(
        f"scrape complete: {len(rows)} rows written to {output} "
        f"(exit={exit_code})"
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
