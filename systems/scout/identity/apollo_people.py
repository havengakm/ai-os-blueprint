"""Apollo People Search adapter — identity resolution via Apollo.

Filters by company domain + seniority (founder, CEO, president, c-suite,
vp). Returns the highest-seniority match that has a non-generic email.
"""
from __future__ import annotations

from typing import Any

import httpx

from config.settings import get_settings
from systems.scout.identity.base import IdentityResult, is_generic_email


APOLLO_PEOPLE_SEARCH_URL = "https://api.apollo.io/v1/mixed_people/search"
DEFAULT_PER_PAGE = 10

# Seniority keywords Apollo understands, ordered by decision-maker weight
SENIORITY_ORDER = ("founder", "c_suite", "owner", "partner", "president", "vp", "head", "director")

# Title keywords to filter on when seniority isn't sufficient (B2B SDR common cases)
DEFAULT_TITLE_KEYWORDS = (
    "founder", "co-founder", "ceo", "chief executive", "president",
    "managing director", "managing partner", "owner",
)


class ApolloPeopleAdapter:
    """Apollo People Search adapter. name='apollo_people'."""

    name: str = "apollo_people"

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        """http_client lets tests inject a mock; production passes None."""
        self._http_client = http_client

    async def resolve(
        self,
        company: str,
        company_domain: str | None = None,
        **kwargs: Any,
    ) -> IdentityResult | None:
        """Query Apollo /mixed_people/search filtered by domain + seniority.
        Returns the best non-generic-email candidate, or None."""
        settings = get_settings()
        api_key = settings.apollo_api_key
        if not api_key:
            return None

        if not company_domain:
            # Apollo People Search works best with a domain filter; without
            # one, returns too much noise. Skip — let Hunter or Claude fallback handle it.
            return None

        payload: dict[str, Any] = {
            "q_organization_domains": company_domain,
            "person_seniorities": list(SENIORITY_ORDER),
            "page": 1,
            "per_page": DEFAULT_PER_PAGE,
        }
        # Allow caller to override title keywords via kwargs
        title_keywords = kwargs.get("title_keywords") or DEFAULT_TITLE_KEYWORDS
        payload["q_keywords"] = " OR ".join(title_keywords)

        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "x-api-key": api_key,
        }

        client_provided = self._http_client is not None
        client = self._http_client or httpx.AsyncClient(timeout=30.0)
        try:
            sources_attempted = [APOLLO_PEOPLE_SEARCH_URL]
            response = await client.post(APOLLO_PEOPLE_SEARCH_URL, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
            people = body.get("people") or body.get("contacts") or []

            # Pick highest-seniority candidate with a non-generic email
            best = _pick_best_candidate(people)
            if not best:
                return None

            name_parts = [best.get("first_name", "").strip(), best.get("last_name", "").strip()]
            if not name_parts[0] or not name_parts[1]:
                # Parse `name` field if first/last split is missing
                full = (best.get("name") or "").strip()
                if not full or full.lower() in {"unknown", "n/a", ""}:
                    return None
                split = full.split(maxsplit=1)
                name_parts = [split[0], split[1] if len(split) > 1 else ""]
                if not name_parts[1]:
                    return None

            return IdentityResult(
                first_name=name_parts[0],
                last_name=name_parts[1],
                title=best.get("title") or None,
                email=best["email"],
                linkedin_url=best.get("linkedin_url"),
                source=self.name,
                confidence=float(best.get("_confidence", 0.85)),
                sources_attempted=sources_attempted,
            )
        finally:
            if not client_provided:
                await client.aclose()


def _pick_best_candidate(people: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the first candidate with a non-generic email, ordered by
    Apollo's seniority-weighted result list. Returns None if no match."""
    for person in people:
        email = person.get("email")
        if not email or is_generic_email(email):
            continue
        # Score a rough confidence from Apollo's presence of linkedin + title
        score = 0.85
        if person.get("linkedin_url"):
            score += 0.05
        if person.get("title"):
            score += 0.05
        person["_confidence"] = min(score, 0.99)
        return person
    return None
