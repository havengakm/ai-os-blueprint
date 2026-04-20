"""Source adapter contract for company-level lead discovery (Task 9).

Per Amendment 2 of the 2026-04-20 lead-sourcing decision: sources produce
company-level data only. Person-level identity (first_name, last_name, email,
phone, linkedin_url, title) is resolved by Task 9.5's identity-lookup stage,
not here.
"""
from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class RawCompanyContact(BaseModel):
    """A company-level contact produced by a source adapter.

    Person-level fields are intentionally absent — Task 9.5 fills those via
    Apollo People Search / Hunter Domain Search / Claude scraper waterfall.
    """

    company: str
    company_domain: str | None = None
    company_website: str | None = None
    industry: str | None = None
    employees: int | None = None
    revenue_usd: int | None = None
    city: str | None = None
    state: str | None = None
    geography: str | None = None
    source: str  # adapter key — e.g. "csv:{upload_id}", "apollo_company", "clutch_shopify"
    source_id: str  # unique within source, used for dedup
    raw_data: dict[str, Any] = Field(default_factory=dict)


class CompanySourceAdapter(Protocol):
    """Protocol every source adapter must implement."""

    name: str  # adapter key, e.g. "csv_ingest", "apollo_company", "clutch_shopify"

    async def pull(
        self,
        client_id: str,
        max_companies: int,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> list[RawCompanyContact]:
        """Pull up to `max_companies` RawCompanyContact from this source.

        Adapters may accept extra kwargs specific to their source (e.g. ICP
        title filters for Apollo, CSV path for csv_ingest). The pipeline
        orchestrator (Task 9d) is responsible for passing the right kwargs
        to each adapter.

        If dry_run is True, adapter must perform reads but NOT write or call
        external paid APIs in a credit-consuming way.
        """
        ...
