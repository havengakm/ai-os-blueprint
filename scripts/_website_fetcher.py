"""Playwright helper — fetch a business's About/Team pages as plain text.

Used by scrape_mindbody.py and scrape_google_maps.py to collect the raw
studio-site content that's then passed to Haiku for owner extraction.

Design choices:
  - Try a short list of path candidates in order. Concatenate body text
    from pages that loaded. First-match-wins is too brittle (a thin
    About page + richer Team page = more signal than either alone).
  - Cap total chars at 6000. Owner/team copy is always in the first
    few kB of body text; more is just tokens burnt.
  - Strip obvious boilerplate (copyright, email-signup CTAs, nav menus)
    so the signal-to-token ratio stays high.
  - Polite delay between page visits. Hammering a small-business Wix
    site would be impolite.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


DEFAULT_PATHS: tuple[str, ...] = (
    "",             # home page first — often carries "meet our founder" teasers
    "about",
    "about-us",
    "team",
    "our-team",
    "meet-the-team",
    "our-story",
    "story",
    "contact",
)

# Heuristic noise-stripping. Not meant to catch every template, just to
# cut the most common boilerplate so the Haiku prompt stays focused.
_NOISE_PATTERNS = [
    re.compile(r"©\s*20\d{2}[^\n]{0,120}", re.IGNORECASE),
    re.compile(r"\bsubscribe\s+to\s+(?:our\s+)?newsletter[^\n]{0,120}", re.IGNORECASE),
    re.compile(r"\benter\s+your\s+email[^\n]{0,80}", re.IGNORECASE),
    re.compile(r"\bcookie(?:s|\s+policy)\b[^\n]{0,160}", re.IGNORECASE),
    re.compile(r"\ball\s+rights\s+reserved[^\n]{0,80}", re.IGNORECASE),
]
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def strip_noise(text: str) -> str:
    """Remove common boilerplate + collapse whitespace. Pure function."""
    out = text
    for rx in _NOISE_PATTERNS:
        out = rx.sub("", out)
    out = _MULTI_NEWLINE_RE.sub("\n\n", out)
    out = _MULTI_SPACE_RE.sub(" ", out)
    return out.strip()


def _build_url(domain: str, path: str) -> str:
    d = domain.rstrip("/")
    if not d.startswith(("http://", "https://")):
        d = "https://" + d
    if not path:
        return d
    return f"{d}/{path.lstrip('/')}"


async def _fetch_one_path_text(
    *, context: Any, url: str, timeout_ms: int,
) -> str:
    """Navigate a new page to `url`, return body innerText, close page."""
    page = await context.new_page()
    try:
        resp = await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        if not resp or resp.status >= 400:
            return ""
        try:
            await page.wait_for_selector("body", timeout=5_000)
        except Exception:
            pass
        text = await page.evaluate(
            "() => (document.body && document.body.innerText) || ''"
        )
        return text or ""
    finally:
        await page.close()


async def fetch_website_about_text(
    *,
    browser: Any,
    domain: str,
    candidate_paths: tuple[str, ...] = DEFAULT_PATHS,
    max_chars: int = 6_000,
    per_page_timeout_ms: int = 15_000,
    user_agent: str | None = None,
) -> str:
    """Fetch About/Team pages from `domain`. Returns concatenated stripped
    body text, truncated to `max_chars`. Empty string if nothing loaded.

    Accepts an already-open Playwright browser so callers can reuse
    their existing session and avoid cold-starting chromium per contact.
    """
    if not domain:
        return ""
    context_opts: dict[str, Any] = {}
    if user_agent:
        context_opts["user_agent"] = user_agent
    ctx = await browser.new_context(**context_opts)
    combined: list[str] = []
    try:
        for path in candidate_paths:
            url = _build_url(domain, path)
            try:
                text = await _fetch_one_path_text(
                    context=ctx, url=url, timeout_ms=per_page_timeout_ms,
                )
            except Exception as e:
                logger.debug("fetch failed %s: %s", url, e)
                continue
            cleaned = strip_noise(text)
            if cleaned:
                combined.append(f"---[{path or 'home'}]---\n{cleaned}")
            if sum(len(p) for p in combined) >= max_chars:
                break
    finally:
        await ctx.close()

    merged = "\n\n".join(combined)
    if len(merged) > max_chars:
        merged = merged[:max_chars].rstrip() + "\n[...truncated]"
    return merged
