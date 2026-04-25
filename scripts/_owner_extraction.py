"""Haiku-based owner extraction from raw website text.

Used by scrape_mindbody.py and scrape_google_maps.py in place of the
previous Sonnet + web_search pattern. Input: the concatenated About /
Team page text already fetched by `_website_fetcher`. Output: owner
fields + category-match verdict.

Cost profile: typical 1500-3000 input tokens + ~200 output tokens on
Haiku 4.5 → ~$0.0024/call vs the old Sonnet+web_search ~$0.04/call.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from scripts._scrape_common import normalise_domain, resolve_is_match

logger = logging.getLogger(__name__)


HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 400

_BAD_DOMAINS = {
    "mindbodyonline.com", "facebook.com", "instagram.com",
    "yelp.com", "linkedin.com", "google.com",
}


_CLAUDE_SYSTEM = (
    "You are a B2B research analyst extracting owner/founder details from "
    "a studio's own website content. You do NOT have web access. You must "
    "use ONLY the content provided in the user message. Never invent "
    "names. Return strict JSON only, no prose, no code fences."
)


_CLAUDE_USER_TEMPLATE = """\
Studio name: {studio_name}
Country: {country}
Category filter: {category_filter}
Known domain: {known_domain}
Known LinkedIn URL (may be blank): {known_linkedin}

You are given the following raw body text scraped from the studio's own
website (About / Team / Contact pages). Use ONLY this text as source.
No external knowledge allowed.

-----BEGIN WEBSITE TEXT-----
{website_text}
-----END WEBSITE TEXT-----

Extract:
  1. The named decision-maker: owner / founder / general manager /
     head coach. Must be a real person named in the text. Null if none.
  2. Their public LinkedIn URL if the text mentions one.
  3. Whether this studio fits the category filter (primary offering).

CATEGORY MATCH RULES (STRICT):
  - is_match=true ONLY if the PRIMARY offering matches the category
    filter. Secondary/supplementary offerings do NOT count.
  - You MUST produce `category_reasoning` before `is_match`.

Return STRICT JSON in this field order, no prose, no code fences:

{{
  "category_reasoning": "1 short sentence about the PRIMARY offering",
  "is_match": true | false,
  "first_name": "Jane" | null,
  "last_name": "Doe" | null,
  "title": "Founder" | "Owner" | "General Manager" | "Head Coach" | null,
  "linkedin_url": "https://..." | null,
  "notes": "1 sentence signal or blank",
  "confidence": 0.0
}}

Rules:
  - first_name + last_name must BOTH be set if you claim a decision-maker.
  - Never fabricate. If the text does not mention an owner, set the
    name fields to null. Null is always acceptable.
  - confidence reflects your certainty the owner is real and current.
"""


@dataclass
class OwnerExtractionResult:
    """All fields may be None when the website text is empty or sparse."""
    domain: str | None
    first_name: str | None
    last_name: str | None
    title: str | None
    linkedin_url: str | None
    is_match: bool
    category_reasoning: str
    notes: str
    confidence: float
    raw_text: str  # for debugging / decision_log


_FENCE_HEAD_RE = re.compile(r"^\s*```(?:json)?\s*", re.IGNORECASE)
_FENCE_TAIL_RE = re.compile(r"\s*```\s*$")


def _parse_claude_json(raw_text: str) -> dict[str, Any] | None:
    text = raw_text.strip()
    text = _FENCE_HEAD_RE.sub("", text)
    text = _FENCE_TAIL_RE.sub("", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_text_blocks(response: Any) -> str:
    parts: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts)


def extract_owner_with_haiku(
    *,
    client: Any,
    studio_name: str,
    website_text: str,
    category_filter: str,
    country: str = "Unknown",
    known_domain: str | None = None,
    known_linkedin: str | None = None,
) -> OwnerExtractionResult:
    """Single Haiku 4.5 call. No tools, no web_search. Empty website_text
    is handled client-side: we skip the call and return an empty result
    so callers don't pay for a hopeless extraction."""
    if not website_text.strip():
        return OwnerExtractionResult(
            domain=normalise_domain(known_domain),
            first_name=None, last_name=None, title=None,
            linkedin_url=known_linkedin or None,
            is_match=False,
            category_reasoning="no website text fetched",
            notes="website_text empty — no extraction attempted",
            confidence=0.0,
            raw_text="",
        )

    user_message = _CLAUDE_USER_TEMPLATE.format(
        studio_name=studio_name,
        country=country,
        category_filter=category_filter,
        known_domain=known_domain or "(unknown)",
        known_linkedin=known_linkedin or "(unknown)",
        website_text=website_text,
    )
    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=MAX_TOKENS,
        system=_CLAUDE_SYSTEM,
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

    domain = normalise_domain(parsed.get("domain") or known_domain)
    if domain in _BAD_DOMAINS:
        domain = None

    return OwnerExtractionResult(
        domain=domain,
        first_name=(parsed.get("first_name") or None),
        last_name=(parsed.get("last_name") or None),
        title=(parsed.get("title") or None),
        linkedin_url=(parsed.get("linkedin_url") or known_linkedin or None),
        is_match=is_match,
        category_reasoning=category_reasoning,
        notes=notes,
        confidence=float(parsed.get("confidence") or 0.0),
        raw_text=raw_text[:500],
    )
