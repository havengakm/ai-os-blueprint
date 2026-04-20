"""Hunter Domain Search adapter — identity resolution via Hunter.io.

Queries all known emails for a domain and picks the highest-seniority
decision-maker using title keyword scoring. Returns None when no entry
scores above 0 (i.e. no recognised decision-maker title found).
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from config.settings import get_settings
from systems.scout.identity.base import IdentityResult, is_generic_email


HUNTER_DOMAIN_SEARCH_URL = "https://api.hunter.io/v2/domain-search"

# (score, compiled pattern) — evaluated in order, first match wins
_SENIORITY_RULES: list[tuple[int, re.Pattern[str]]] = [
    (100, re.compile(r"\bco[-\s]?founder\b|\bfounder\b", re.I)),
    (90,  re.compile(r"\bceo\b|\bchief executive\b|\bpresident\b(?!.*\bvice\b)", re.I)),
    (80,  re.compile(r"\bcfo\b|\bcoo\b|\bcto\b|\bchief\b.+\bofficer\b|\bchief operating\b|\bchief financial\b|\bchief technology\b", re.I)),
    (75,  re.compile(r"\bowner\b|\bmanaging director\b|\bmanaging partner\b", re.I)),
    (60,  re.compile(r"\bvp\b|\bvice president\b", re.I)),
    (40,  re.compile(r"\bhead of\b|\bdirector\b", re.I)),
]

# Vice president should NOT match the president rule — guard applied in scoring
_VICE_PRESIDENT_RE = re.compile(r"\bvice president\b", re.I)


def _title_score(position: str | None) -> int:
    """Return seniority score (0–100) for a job title string."""
    if not position:
        return 0
    for score, pattern in _SENIORITY_RULES:
        if pattern.search(position):
            # CEO/President rule: skip if "vice president" present
            if score == 90 and _VICE_PRESIDENT_RE.search(position):
                continue
            return score
    return 0


def _pick_best_entry(emails: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the highest-seniority non-generic entry with a valid name.

    Tie-break: higher Hunter confidence, then presence of linkedin URL.
    Returns None if no entry scores above 0.
    """
    best: dict[str, Any] | None = None
    best_score = 0
    best_confidence = -1
    best_has_linkedin = False

    for entry in emails:
        email = entry.get("value")
        if is_generic_email(email):
            continue

        first = (entry.get("first_name") or "").strip()
        last = (entry.get("last_name") or "").strip()
        if not first or not last:
            continue
        if first.lower() in {"unknown", "n/a"} or last.lower() in {"unknown", "n/a"}:
            continue

        score = _title_score(entry.get("position"))
        if score == 0:
            continue

        confidence = entry.get("confidence", 0)
        has_linkedin = bool(entry.get("linkedin"))

        if (
            score > best_score
            or (score == best_score and confidence > best_confidence)
            or (score == best_score and confidence == best_confidence and has_linkedin and not best_has_linkedin)
        ):
            best = entry
            best_score = score
            best_confidence = confidence
            best_has_linkedin = has_linkedin

    return best


class HunterDomainAdapter:
    """Hunter Domain Search adapter. name='hunter_domain'."""

    name: str = "hunter_domain"

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        """http_client lets tests inject a mock; production passes None."""
        self._http_client = http_client

    async def resolve(
        self,
        company: str,
        company_domain: str | None = None,
        **kwargs: Any,
    ) -> IdentityResult | None:
        """Query Hunter Domain Search for the highest-seniority decision-maker.

        Returns None if:
        - No api_key configured
        - No company_domain provided (Hunter requires domain)
        - No entry scores above 0 (no recognised decision-maker title)
        - Only generic emails found
        """
        settings = get_settings()
        api_key = settings.hunter_api_key
        if not api_key:
            return None

        if not company_domain:
            return None

        params = {
            "domain": company_domain,
            "api_key": api_key,
        }

        client_provided = self._http_client is not None
        client = self._http_client or httpx.AsyncClient(timeout=30.0)
        try:
            sources_attempted = [HUNTER_DOMAIN_SEARCH_URL]
            response = await client.get(HUNTER_DOMAIN_SEARCH_URL, params=params)
            response.raise_for_status()
            body = response.json()
            emails = (body.get("data") or {}).get("emails") or []

            best = _pick_best_entry(emails)
            if not best:
                return None

            return IdentityResult(
                first_name=best["first_name"].strip(),
                last_name=best["last_name"].strip(),
                title=best.get("position") or None,
                email=best["value"],
                linkedin_url=best.get("linkedin") or None,
                source=self.name,
                confidence=float(best.get("confidence", 0)) / 100.0,
                sources_attempted=sources_attempted,
            )
        finally:
            if not client_provided:
                await client.aclose()
