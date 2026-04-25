"""Shared pure-function helpers used by both scrape_mindbody and
scrape_google_maps. Split out to avoid circular imports with
_owner_extraction.py.

Everything here is pure string manipulation / regex — no IO, no network,
no Playwright. Fully unit-testable in isolation.
"""
from __future__ import annotations

import re
from typing import Any


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
