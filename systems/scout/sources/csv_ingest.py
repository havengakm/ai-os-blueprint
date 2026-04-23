"""CSV ingest adapter — operators upload a CSV of companies, we ingest.

The simplest source: no external APIs, no HTML scraping. Useful for:
- Seeding a new client's deployment with a hand-built list
- Ingesting the operator-facing research CSV shape (14 columns per Task 3.8)
- Fast end-to-end dry-run validation in Plan 1

Accepted CSV shape (header row required, column order flexible):
  Required columns: Company Name OR company
  Optional columns: Website, company_website, company_domain, Industry,
  industry, Employees, employees, Revenue, revenue_usd, Location, city, state,
  geography, source_id
  Any extra columns are preserved in raw_data JSON.

Dedup key: normalized company_domain if present, else lower(Company Name).
"""
from __future__ import annotations

import csv
import hashlib
from io import StringIO
from pathlib import Path
from typing import Any

from systems.scout.sources.base import CompanySourceAdapter, RawCompanyContact
from systems.scout.sources.utils import normalize_domain, parse_int_safe


COMPANY_NAME_COLS = ("Company Name", "company_name", "company", "Company")
WEBSITE_COLS = ("Website", "website", "company_website")
DOMAIN_COLS = ("company_domain", "Domain", "domain")
INDUSTRY_COLS = ("Industry", "industry")
EMPLOYEES_COLS = ("Employees", "employees")
REVENUE_COLS = ("Revenue", "revenue_usd", "revenue")
CITY_COLS = ("city", "City")
STATE_COLS = ("state", "State")
GEOGRAPHY_COLS = ("geography", "Location", "Geography", "location")
SOURCE_ID_COLS = ("source_id", "id", "Source ID")


def _pick(row: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for col in candidates:
        if col in row and row[col] and str(row[col]).strip():
            return str(row[col]).strip()
    return None



class CSVIngestAdapter:
    """CSV file adapter. name='csv_ingest'."""

    name: str = "csv_ingest"

    def __init__(self, upload_id: str | None = None) -> None:
        """upload_id tags source as 'csv:{upload_id}' for audit; auto-generated if not given."""
        self.upload_id = upload_id

    async def pull(
        self,
        client_id: str,
        max_companies: int,
        dry_run: bool = False,
        *,
        csv_path: str | Path | None = None,
        csv_content: str | None = None,
    ) -> list[RawCompanyContact]:
        """Read a CSV from csv_path OR csv_content; return up to max_companies.

        Exactly one of csv_path / csv_content must be provided.
        dry_run has no effect for CSV (no external calls).
        """
        if (csv_path is None) == (csv_content is None):
            raise ValueError("Provide exactly one of csv_path or csv_content")

        if csv_path is not None:
            text = Path(csv_path).read_text(encoding="utf-8-sig")
        else:
            text = (csv_content or "").lstrip("\ufeff")

        reader = csv.DictReader(StringIO(text))
        upload_id = self.upload_id or hashlib.sha256(text.encode()).hexdigest()[:12]
        source_key = f"csv:{upload_id}"

        results: list[RawCompanyContact] = []
        seen_keys: set[str] = set()

        for idx, row in enumerate(reader):
            if len(results) >= max_companies:
                break

            company = _pick(row, COMPANY_NAME_COLS)
            if not company:
                continue  # skip rows without a company

            website = _pick(row, WEBSITE_COLS)
            explicit_domain = _pick(row, DOMAIN_COLS)
            domain = normalize_domain(explicit_domain) or normalize_domain(website)

            dedup_key = (domain or company.lower()).strip()
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            source_id = _pick(row, SOURCE_ID_COLS) or f"{upload_id}-row{idx}"

            results.append(
                RawCompanyContact(
                    company=company,
                    company_domain=domain,
                    company_website=website,
                    industry=_pick(row, INDUSTRY_COLS),
                    employees=parse_int_safe(_pick(row, EMPLOYEES_COLS)),
                    revenue_usd=parse_int_safe(_pick(row, REVENUE_COLS)),
                    city=_pick(row, CITY_COLS),
                    state=_pick(row, STATE_COLS),
                    geography=_pick(row, GEOGRAPHY_COLS),
                    source=source_key,
                    source_id=source_id,
                    raw_data={k: v for k, v in row.items() if v},
                )
            )

        return results
