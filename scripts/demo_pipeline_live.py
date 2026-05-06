"""Live Supabase demo — runs Plan 1 scoring + screening against real contacts.

READ-ONLY. No writes to the database. Outputs what Plan 1 would do if dispatched.

Maps base-camp-agents' older contacts schema into Plan 1's ContactToScore shape
as best-effort. Industry/title/geography/employees come from contact.raw_data
(Apollo payload) when present; missing fields score 0 for that category.

Usage:
    PYTHONPATH=. uv run python scripts/demo_pipeline_live.py [LIMIT]

LIMIT defaults to 10.
"""
from __future__ import annotations

import os
import sys
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

from aios.scout.pipeline.score import (
    DEFAULT_TIER_THRESHOLDS,
    DEFAULT_WEIGHTS,
    assign_tier,
    score_v1,
)
from aios.scout.pipeline.screen import screen_contact


# ---------------------------------------------------------------------------
# Load credentials from base-camp-agents (current Supabase project)
# ---------------------------------------------------------------------------

ENV_PATH = "/home/kirsten/01_PERSONAL/10_PERSONAL_PROJECTS/base-camp-agents/.env"
load_dotenv(ENV_PATH)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print(f"ERROR: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not found in {ENV_PATH}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Field extraction helpers (defensive lookup against inconsistent raw_data)
# ---------------------------------------------------------------------------

def _first_nonblank(d: dict[str, Any], keys: list[str]) -> Any:
    """Return first truthy value found in d for any of keys."""
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return None


def _extract_industry(raw: dict[str, Any]) -> str | None:
    org = raw.get("organization") or {}
    return _first_nonblank(raw, ["industry", "organization_industry"]) or _first_nonblank(org, ["industry"])


def _extract_title(raw: dict[str, Any]) -> str | None:
    return _first_nonblank(raw, ["title", "headline", "job_title"])


def _extract_employees(raw: dict[str, Any]) -> int | None:
    org = raw.get("organization") or {}
    v = _first_nonblank(raw, ["employees", "estimated_num_employees", "employee_count"]) \
        or _first_nonblank(org, ["estimated_num_employees", "employees", "employee_count"])
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _extract_geography(raw: dict[str, Any]) -> str | None:
    org = raw.get("organization") or {}
    # Build a geography string from available components
    country = _first_nonblank(raw, ["country", "country_name"]) or _first_nonblank(org, ["country"])
    state = _first_nonblank(raw, ["state", "region"]) or _first_nonblank(org, ["state"])
    city = _first_nonblank(raw, ["city"]) or _first_nonblank(org, ["city"])
    parts = [p for p in (city, state, country) if p]
    return ", ".join(parts) if parts else None


def _extract_name_parts(name: str | None) -> tuple[str | None, str | None]:
    """Split 'John Smith' → ('John', 'Smith'). Defensive."""
    if not name:
        return None, None
    parts = name.strip().split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------

def run_demo(limit: int = 10) -> None:
    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 1. Fetch ICP definition (assume one client)
    icp_resp = client.table("icp_definitions").select("*").limit(1).execute()
    if not icp_resp.data:
        print("ERROR: no icp_definitions row found. Set one up first.")
        sys.exit(1)
    icp_row = icp_resp.data[0]
    client_id = icp_row["client_id"]

    # 2. Fetch negative ICP (blacklist)
    neg_resp = client.table("negative_icp").select("*").eq("client_id", client_id).execute()
    blacklist_companies = [
        r["value"] for r in (neg_resp.data or []) if r.get("field") == "company"
    ]
    blacklist_domains = [
        r["value"] for r in (neg_resp.data or []) if r.get("field") == "domain"
    ]

    # 3. Build Plan 1-shaped client_config from the base-camp-agents ICP schema
    plan1_config: dict[str, Any] = {
        "weights": DEFAULT_WEIGHTS,
        "tier_thresholds": DEFAULT_TIER_THRESHOLDS,
        "icp": {
            "industries": icp_row.get("industries") or [],
            "titles": icp_row.get("titles") or [],
            "employee_min": icp_row.get("min_employees"),
            "employee_max": icp_row.get("max_employees"),
            "geographies": icp_row.get("geographies") or [],
            "blacklist_companies": blacklist_companies,
            "blacklist_domains": blacklist_domains,
        },
    }

    # 4. Fetch contacts (include top-level firmographic columns added post-001_initial_schema)
    contacts_resp = (
        client.table("contacts")
        .select(
            "id, name, company, company_domain, email, email_verified, linkedin_url, "
            "phone, title, industry, employees, revenue_usd, geography, website, "
            "icp_score, status, raw_data"
        )
        .eq("client_id", client_id)
        .limit(limit)
        .execute()
    )
    rows = contacts_resp.data or []

    # 5. Print header
    print("=" * 110)
    print(f"Plan 1 Live Demo — Supabase project for client_id='{client_id}'")
    print("=" * 110)
    print(f"\nICP fetched: {len(plan1_config['icp']['industries'])} industries, "
          f"{len(plan1_config['icp']['titles'])} titles, "
          f"{len(plan1_config['icp']['geographies'])} geographies, "
          f"{len(blacklist_companies)} blacklisted companies, "
          f"{len(blacklist_domains)} blacklisted domains")
    print(f"Weights: {plan1_config['weights']}")
    print(f"Tier thresholds: A>={plan1_config['tier_thresholds']['A']}  "
          f"B>={plan1_config['tier_thresholds']['B']}  "
          f"C>={plan1_config['tier_thresholds']['C']}  "
          f"D>={plan1_config['tier_thresholds']['D']}  "
          f"archive_floor={plan1_config['tier_thresholds']['archive_floor']}")
    print(f"\nScoring {len(rows)} contacts...\n")

    print(f"{'Name':<25} {'Company':<25} {'Industry':<20} {'Title':<25} {'Score':>5} {'Tier':>6} {'Screen':>20}")
    print("-" * 130)

    # 6. For each contact, map + score + screen
    tier_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "archive": 0}
    screen_counts = {"pass": 0, "missing_name": 0, "missing_company": 0,
                     "blacklisted_company": 0, "blacklisted_domain": 0, "skipped_archived": 0}

    for row in rows:
        raw = row.get("raw_data") or {}
        first, last = _extract_name_parts(row.get("name"))
        # Prefer top-level columns (post-001 schema); fall back to raw_data for missing fields
        contact = {
            "first_name": first,
            "last_name": last,
            "company": row.get("company"),
            "company_domain": row.get("company_domain") or raw.get("domain"),
            "industry": row.get("industry") or _extract_industry(raw),
            "title": row.get("title") or _extract_title(raw),
            "employees": row.get("employees") if row.get("employees") is not None else _extract_employees(raw),
            "geography": row.get("geography") or _extract_geography(raw),
            "email": row.get("email"),
            "email_verified": bool(row.get("email_verified")),
            "linkedin_url": row.get("linkedin_url"),
            "phone": row.get("phone") or raw.get("phone"),
            "raw_data": raw,
            "research_data": {},
        }

        score = score_v1(contact, plan1_config)
        tier = assign_tier(score, plan1_config)
        tier_counts[tier] += 1

        if tier == "archive":
            screen_label = "(skipped: archived)"
            screen_counts["skipped_archived"] += 1
        else:
            passed, reason = screen_contact(contact, plan1_config)
            if passed:
                screen_label = "PASS"
                screen_counts["pass"] += 1
            else:
                bucket = reason.split(":", 1)[0]
                screen_label = f"REJECT: {bucket}"
                screen_counts[bucket] = screen_counts.get(bucket, 0) + 1

        name_display = (row.get("name") or "(no name)")[:24]
        company_display = (row.get("company") or "(no company)")[:24]
        industry_display = (contact["industry"] or "(none)")[:19]
        title_display = (contact["title"] or "(none)")[:24]
        print(f"{name_display:<25} {company_display:<25} {industry_display:<20} {title_display:<25} {score:>5} {tier:>6} {screen_label:>20}")

    # 7. Summary
    print()
    print(f"Tier distribution: {tier_counts}")
    print(f"Screen outcomes:   {screen_counts}")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    run_demo(limit=limit)
