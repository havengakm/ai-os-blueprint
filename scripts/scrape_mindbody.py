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
# web_search pulls ~10-15k input tokens per call via tool results. The
# default Anthropic tier-1 limit is 30k input tokens/min, so we must
# space Claude calls or we hit 429. 35s keeps us under the ceiling with
# headroom for the directory-scrape latency.
CLAUDE_GAP_SECONDS = 35.0
SONNET_MODEL = "claude-sonnet-4-5"
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
Country: South Africa
Mindbody profile: {mindbody_url}

Use the web_search tool (at most 3 searches) to locate:
  1. The studio's own official website (domain).
  2. The named decision-maker: owner, founder, GM, or head coach.
  3. Their public LinkedIn URL if visible.
  4. Any fresh buying-signal you notice (hiring, new location, recent press).

Return STRICT JSON exactly matching this shape, no prose, no code fences:

{{
  "domain": "example.co.za" | null,
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
) -> dict[str, Any]:
    """One Claude Sonnet call with web_search → resolved fields.

    Returns a dict with:
      domain, first_name, last_name, title, linkedin_url, notes, confidence,
      raw_text (for debugging)

    On parse failure, everything is None / empty and notes contains the
    raw_text head for a human to inspect.
    """
    client = _ensure_anthropic_client(client)
    user_message = _CLAUDE_USER_TEMPLATE.format(
        studio_name=studio_name,
        city=city,
        mindbody_url=mindbody_url,
    )

    response = client.messages.create(
        model=SONNET_MODEL,
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

    out = {
        "domain": normalise_domain(parsed.get("domain")),
        "first_name": (parsed.get("first_name") or None),
        "last_name": (parsed.get("last_name") or None),
        "title": (parsed.get("title") or None),
        "linkedin_url": (parsed.get("linkedin_url") or None),
        "notes": (parsed.get("notes") or "").strip(),
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
            )
        except Exception as e:  # billed or infra — log + skip
            logger.warning(
                "claude call failed studio=%s err=%s",
                studio["name"], e,
            )
            # On 429 / rate-limit, cool down before the next attempt so we
            # don't waste the remaining studios on the same throttle.
            if "429" in str(e) or "rate_limit" in str(e).lower():
                logger.info("rate limit cooldown %ds", int(CLAUDE_GAP_SECONDS))
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

_CITY_NAME_BY_SLUG = {
    "cape-town-wc-za": "Cape Town",
    "johannesburg-gp-za": "Johannesburg",
    "durban-kzn-za": "Durban",
    "stellenbosch-wc-za": "Stellenbosch",
    "pretoria-gp-za": "Pretoria",
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

    city_name = args.city_name or _CITY_NAME_BY_SLUG.get(
        args.city_slug, args.city_slug.replace("-", " ").title()
    )

    output = Path(args.output)
    if not output.is_absolute():
        output = _REPO_ROOT / output

    exit_code, rows = asyncio.run(run(
        city_slug=args.city_slug,
        city_name=city_name,
        niche=args.niche,
        limit=args.limit,
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
