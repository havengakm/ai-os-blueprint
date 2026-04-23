"""Apollo Organization Enrichment adapter — company-level data fill.

Calls Apollo's GET /v1/organizations/enrich endpoint to fill company-level
gaps (revenue, employees, industry, founded_year, etc.) for contacts that
were NOT sourced from Apollo in the first place. Tier A/B only — the
orchestrator is responsible for tier gating; this adapter just executes
the call and returns an EnrichResult.

Cost model:
  - 1 Apollo credit per call. Mapped to cost_cents_per_call=1 so the
    orchestrator's tier-budget math can compare against ZeroBounce (also 1).
    The budget engine treats cost_cents as a relative weight, not USD.

Skip paths (no network call, cost_cents=0):
  - dry_run=True                             → reason='dry_run_skipped'
  - APOLLO_API_KEY unset                     → reason='no_api_key'
  - contact.company_domain blank/missing     → reason='no_company_domain'
  - contact already has all 4 core fields    → reason='already_complete'
    (revenue_usd + employees + industry + founded_year all truthy)

Infrastructure errors propagate — no retries (per base.py docstring).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from config.settings import get_settings
from systems.scout.enrich.base import EnrichResult
from systems.scout.sources.utils import normalize_domain


logger = logging.getLogger(__name__)

APOLLO_ORG_ENRICH_URL = "https://api.apollo.io/v1/organizations/enrich"


class ApolloEnrichAdapter:
    """Apollo Organization Enrichment adapter. name='apollo_enrich'."""

    name: str = "apollo_enrich"
    cost_cents_per_call: int = 1    # 1 credit, mapped to 1 cent for tier-budget math

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        """http_client lets tests inject a mocked client; production passes None."""
        self._http_client = http_client

    async def enrich(
        self,
        contact: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> EnrichResult:
        """Fill company-level gaps for a contact via Apollo Organization Enrichment.

        See module docstring for skip paths. On a completed call, cost_cents=1
        regardless of whether Apollo returned a match (the credit was spent).
        """
        contact_id = contact.get("contact_id", "<unknown>")

        # --- dry run ---
        if dry_run:
            logger.debug("apollo_enrich dry_run contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=True,
                data={},
                cost_cents=0,
                reason="dry_run_skipped",
            )

        # --- key guard ---
        settings = get_settings()
        api_key = settings.apollo_api_key
        if not api_key:
            logger.warning("apollo_enrich no_api_key contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=False,
                data={},
                cost_cents=0,
                reason="no_api_key",
            )

        # --- domain guard ---
        raw_domain = (contact.get("company_domain") or "").strip()
        if not raw_domain:
            logger.debug("apollo_enrich no_company_domain contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=False,
                data={},
                cost_cents=0,
                reason="no_company_domain",
            )

        # --- already-complete guard (don't burn credits when all 4 fields are set) ---
        if (
            contact.get("revenue_usd")
            and contact.get("employees")
            and contact.get("industry")
            and contact.get("founded_year")
        ):
            logger.debug("apollo_enrich already_complete contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=True,
                data={},
                cost_cents=0,
                reason="already_complete",
            )

        # --- normalise domain before sending ---
        domain = normalize_domain(raw_domain) or raw_domain

        # --- API call ---
        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "x-api-key": api_key,
        }
        client_provided = self._http_client is not None
        client = self._http_client or httpx.AsyncClient(timeout=30.0)
        try:
            response = await client.get(
                APOLLO_ORG_ENRICH_URL,
                params={"domain": domain},
                headers=headers,
            )
            response.raise_for_status()  # propagates on 4xx/5xx — no retry
            body: dict[str, Any] = response.json()
        finally:
            if not client_provided:
                await client.aclose()

        # --- parse response ---
        org = body.get("organization")
        if not org:
            logger.info(
                "apollo_enrich contact_id=%s domain=%s reason=no_match cost_cents=%d",
                contact_id, domain, self.cost_cents_per_call,
            )
            return EnrichResult(
                adapter_name=self.name,
                ok=True,
                data={},
                cost_cents=self.cost_cents_per_call,
                reason="no_match",
                raw_response=body,
            )

        # Map Apollo org fields into company-level fill fields. Only include
        # fields where Apollo returned a value — let the orchestrator decide
        # whether to overwrite existing contact fields.
        data: dict[str, Any] = {}
        revenue = org.get("annual_revenue")
        if isinstance(revenue, (int, float)):
            data["company_revenue_usd"] = int(revenue)

        employees = org.get("estimated_num_employees")
        if isinstance(employees, int):
            data["company_employees"] = employees

        if org.get("industry"):
            data["company_industry"] = org["industry"]

        founded_year = org.get("founded_year")
        if isinstance(founded_year, int):
            data["company_founded_year"] = founded_year

        if org.get("short_description"):
            data["company_short_description"] = org["short_description"]

        if org.get("linkedin_url"):
            data["company_linkedin_url"] = org["linkedin_url"]

        technologies = org.get("technologies")
        if isinstance(technologies, list) and technologies:
            data["company_technologies"] = technologies

        keywords = org.get("keywords")
        if isinstance(keywords, list) and keywords:
            data["company_keywords"] = keywords

        logger.info(
            "apollo_enrich contact_id=%s domain=%s reason=enriched cost_cents=%d",
            contact_id, domain, self.cost_cents_per_call,
        )

        return EnrichResult(
            adapter_name=self.name,
            ok=True,
            data=data,
            cost_cents=self.cost_cents_per_call,
            reason="enriched",
            raw_response=body,
        )
