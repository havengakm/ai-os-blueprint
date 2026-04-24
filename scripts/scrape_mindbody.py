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
# web_search pulls ~10-15k input tokens per call via tool results. Even on
# Haiku 4.5 that's ~$0.010/call — still over the $0.002/contact target.
# Phase 2 of fix/cost-discipline will drop web_search entirely (Playwright-
# fetch the site + Haiku extract). For now, Haiku replacement alone gets
# us from ~$0.05/call Sonnet to ~$0.010/call — 5x savings.
CLAUDE_GAP_SECONDS = 15.0
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


_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)
_WWW_RE = re.compile(r"^www\.", re.IGNORECASE)


def normalise_domain(raw: str | None) -> str | None:
    """Strip scheme, www, path, and trailing dots; return None on empty."""
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    s = _SCHEME_RE.sub("", s)
    s = _WWW_RE.sub("", s)
    s = s.split("/", 1)[0].rstrip(".")
    return s or None


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


# Phrases that indicate Claude is hedging on category match even when it
# returned is_match=true. Post-hoc override: if ANY of these appear in
# category_reasoning / notes, force is_match=false.
_REJECTION_RE = re.compile(
    r"\b(?:"
    r"not\s+(?:a|primarily|really|actually|truly|the)\s+(?:pilates|yoga|fitness|studio|gym|f45|crossfit|barre|ballet)"
    r"|supplementary"
    r"|secondary\s+(?:offering|focus)"
    r"|side\s+offering"
    r"|doesn'?t\s+(?:fit|match|primarily)"
    r"|isn'?t\s+(?:a|primarily)"
    r"|is\s+(?:a|an)\s+(?:iv|body sculpting|lymphatic|ballet\s+company|dance|martial\s+arts|boxing|hair|beauty|spa|salon)"
    r"|primarily\s+(?:iv|body|lymphatic|ballet|dance)"
    r"|hybrid\s+offering"
    r"|mixed\s+offering"
    r")\b",
    re.IGNORECASE,
)


def resolve_is_match(
    raw_is_match: Any,
    category_reasoning: str,
    notes: str,
) -> tuple[bool, str | None]:
    """Final is_match with safety-net override.

    Returns (is_match, override_reason). override_reason is None when the
    raw Claude value is respected; otherwise a short string describing
    which field tripped the override.
    """
    is_match = bool(raw_is_match) if raw_is_match is not None else True
    combined = f"{category_reasoning} || {notes}"
    rejection_hit = _REJECTION_RE.search(combined or "")
    if is_match and rejection_hit:
        return False, f"rejection-phrase:{rejection_hit.group(0)!r}"
    return is_match, None


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
    """Returns (exit_code, rows)."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            studios = await scrape_directory(city_slug, browser=browser)
        finally:
            await browser.close()

    logger.info("directory scrape: %d studios for %s", len(studios), city_slug)

    if len(studios) < min_studios:
        logger.error(
            "too few studios (%d < %d) for city_slug=%s — aborting",
            len(studios), min_studios, city_slug,
        )
        return 2, []

    # Claude web_search runs sequentially with a short gap to stay polite.
    client = _ensure_anthropic_client()
    rows: list[dict[str, str]] = []
    attempted = 0
    consecutive_failures = 0
    max_consecutive_failures = 5
    for studio in studios:
        if len(rows) >= limit:
            break
        attempted += 1
        logger.info(
            "[%d/%d] resolving %s",
            attempted, limit, studio["name"],
        )
        try:
            resolved = resolve_studio_with_claude(
                studio_name=studio["name"],
                mindbody_url=studio["mindbody_url"],
                city=city_name,
                client=client,
                country=country,
                category_filter=category_filter,
            )
            consecutive_failures = 0
        except Exception as e:  # billed or infra — log + skip
            consecutive_failures += 1
            logger.warning(
                "claude call failed (%d consecutive) studio=%s err=%s",
                consecutive_failures, studio["name"], e,
            )
            if consecutive_failures >= max_consecutive_failures:
                logger.error(
                    "bailing after %d consecutive Claude failures",
                    max_consecutive_failures,
                )
                break
            # Cool down on ANY failure so we don't burn the queue during
            # a transient API or network blip.
            time.sleep(CLAUDE_GAP_SECONDS)
            continue

        row = build_row(
            studio_name=studio["name"],
            mindbody_url=studio["mindbody_url"],
            resolved=resolved,
            city=city_name,
            niche=niche,
        )
        if row is None:
            logger.info(
                "skipped %s — Claude returned no usable domain",
                studio["name"],
            )
            # Rate-limit gap even on skip — we still spent tokens.
            if len(rows) < limit:
                time.sleep(CLAUDE_GAP_SECONDS)
            continue

        if resolved.get("is_match") is False:
            logger.info(
                "skipped %s — doesn't match category filter %r",
                studio["name"], category_filter,
            )
            if len(rows) < limit:
                time.sleep(CLAUDE_GAP_SECONDS)
            continue

        missing = validate_row(row)
        if missing:
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
        # Rate-limit gap between Claude calls (tier-1 30k tokens/min).
        if len(rows) < limit:
            time.sleep(CLAUDE_GAP_SECONDS)

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
