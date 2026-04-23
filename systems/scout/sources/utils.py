"""Shared helpers for source adapters — normalisation + parsing.

Extracted from the inlined duplicates in csv_ingest.py + apollo_company.py
during Task 9a/9b hardening (2026-04-20). Both adapters and future adapters
(Task 9c Clutch, Task 9d orchestrator) import from here so validation rules
stay consistent across sources.
"""
from __future__ import annotations

import math
from urllib.parse import urlparse


def normalize_domain(value: str | None) -> str | None:
    """Normalise a website URL or bare domain string to a canonical hostname.

    Returns None for falsy, non-string, or non-hostname-shaped input. A valid
    return value always contains at least one '.' (rules out garbage like
    'plainstring' or '<>bad<>').

    - Strips `http://` / `https://` scheme
    - Strips `www.` prefix
    - Lower-cases the hostname
    - Returns None if the result doesn't contain a dot
    """
    if not value or not isinstance(value, str):
        return None
    w = value.strip().lower()
    if not w:
        return None
    if not w.startswith(("http://", "https://")):
        w = "https://" + w
    try:
        netloc = urlparse(w).netloc
    except Exception:
        return None
    netloc = netloc.removeprefix("www.")
    if not netloc or "." not in netloc:
        return None
    return netloc


def parse_int_safe(value: str | None) -> int | None:
    """Best-effort parse of a numeric value with M/K suffixes and $ prefixes.

    Examples:
        "3000000"       -> 3_000_000
        "$3M"           -> 3_000_000
        "$3M-$5M"       -> 3_000_000  (low-end of a range)
        "5K"            -> 5_000
        "<$5M"          -> None       (non-numeric prefix — conservative)
        "inf"           -> None       (non-finite — safely rejected)
        "nan"           -> None       (non-finite — safely rejected)
        "abc"           -> None       (unparseable)
        None / ""       -> None

    Never raises.
    """
    if not value:
        return None
    cleaned = value.replace(",", "").replace("$", "").strip()
    # Range -> take the low end
    if "-" in cleaned:
        cleaned = cleaned.split("-")[0].strip()
    if not cleaned:
        return None
    multiplier = 1
    if cleaned.endswith("M"):
        multiplier = 1_000_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith("K"):
        multiplier = 1_000
        cleaned = cleaned[:-1]
    try:
        parsed = float(cleaned)
        if not math.isfinite(parsed):
            return None
        return int(parsed * multiplier)
    except (ValueError, TypeError, OverflowError):
        return None
