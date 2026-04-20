"""Apollo Organization Search adapter — company-level discovery.

Calls Apollo's /v1/organizations/search endpoint. Returns RawCompanyContact
rows with company-level data only — no decision-maker / people fields.
Identity lookup is Task 9.5's responsibility.
"""
from __future__ import annotations

from typing import Any

import httpx

from config.settings import get_settings
from systems.scout.sources.base import CompanySourceAdapter, RawCompanyContact
from systems.scout.sources.utils import normalize_domain


APOLLO_ORG_SEARCH_URL = "https://api.apollo.io/v1/organizations/search"
DEFAULT_PER_PAGE = 25


def _org_to_contact(org: dict[str, Any]) -> RawCompanyContact | None:
    """Map an Apollo Organization to our RawCompanyContact. Returns None if
    the org lacks a usable name (rare but possible)."""
    name = org.get("name") or org.get("organization_name")
    if not name:
        return None

    website = org.get("website_url")
    domain = normalize_domain(org.get("primary_domain")) or normalize_domain(website)

    # Revenue — Apollo gives either an int (annual_revenue) or printed string
    revenue_usd: int | None = None
    if isinstance(org.get("annual_revenue"), (int, float)):
        revenue_usd = int(org["annual_revenue"])

    return RawCompanyContact(
        company=str(name).strip(),
        company_domain=domain,
        company_website=website,
        industry=org.get("industry"),
        employees=org.get("estimated_num_employees"),
        revenue_usd=revenue_usd,
        city=org.get("city"),
        state=org.get("state"),
        geography=org.get("country"),
        source="apollo_company",
        source_id=str(org.get("id") or org.get("organization_id") or ""),
        raw_data=org,
    )


class ApolloCompanyAdapter:
    """Apollo Organization Search adapter. name='apollo_company'."""

    name: str = "apollo_company"

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        """http_client lets tests inject a mocked client. Production wiring
        passes None and a new client is created per-call."""
        self._http_client = http_client

    async def pull(
        self,
        client_id: str,
        max_companies: int,
        dry_run: bool = False,
        *,
        keywords: list[str] | None = None,
        employee_ranges: list[str] | None = None,
        locations: list[str] | None = None,
    ) -> list[RawCompanyContact]:
        """Query Apollo's Organization Search.

        In dry_run mode: builds the request payload but does NOT call the API
        (returns []). Useful for wiring tests without burning credits.
        """
        settings = get_settings()
        api_key = settings.apollo_api_key
        if not api_key and not dry_run:
            # Don't raise — return empty and let orchestrator log a decision
            return []

        if dry_run:
            return []

        payload: dict[str, Any] = {"page": 1, "per_page": min(DEFAULT_PER_PAGE, max_companies)}
        if keywords:
            payload["q_organization_keyword_tags"] = keywords
        if employee_ranges:
            payload["organization_num_employees_ranges"] = employee_ranges
        if locations:
            payload["organization_locations"] = locations

        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "x-api-key": api_key,
        }

        results: list[RawCompanyContact] = []
        page = 1

        client_provided = self._http_client is not None
        client = self._http_client or httpx.AsyncClient(timeout=30.0)
        try:
            while len(results) < max_companies:
                payload["page"] = page
                payload["per_page"] = min(DEFAULT_PER_PAGE, max_companies - len(results))
                response = await client.post(APOLLO_ORG_SEARCH_URL, json=payload, headers=headers)
                response.raise_for_status()
                body = response.json()
                orgs = body.get("organizations", [])
                if not orgs:
                    break
                for org in orgs:
                    contact = _org_to_contact(org)
                    if contact:
                        results.append(contact)
                    if len(results) >= max_companies:
                        break
                pagination = body.get("pagination", {})
                total_pages = pagination.get("total_pages", 1)
                if page >= total_pages:
                    break
                page += 1
        finally:
            if not client_provided:
                await client.aclose()

        return results
