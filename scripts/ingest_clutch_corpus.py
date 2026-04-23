"""One-off ingest: scraped Clutch corpus CSV → contacts (status='enriched').

The sibling project ``clutch.co-scraper/`` already captured homepage /
about / services / testimonials text plus Clutch firmographics (rating,
review count, hourly rate, services mix) and decision-maker email where
discoverable. This script maps that rich schema onto the AIOS ``contacts``
table and stamps rows with ``status='enriched'`` so the daemon can skip
the enrich stage and proceed directly to score_v1 → screen → identity →
score_v2 → compose.

Scraper column → AIOS column mapping
    company_name   → company
    domain         → company_domain, source_id (dedup key)
    best_email     → email (NULL if empty)
    linkedin       → linkedin_url
    timezone       → timezone
    employee_count → employees (band midpoint; see _parse_employee_band)

Scraper column → research_data.website_content
    homepage_text, about_text, services_text, testimonials_text,
    portfolio_text

Scraper column → research_data.clutch_metadata
    rating, review_count, hourly_rate, min_budget, services, location,
    website

Scraper column → raw_data
    clutch_url, designrush_url, sources, meta_title, meta_description

Usage:
    uv run python scripts/ingest_clutch_corpus.py \\
        --csv-path=<path> --client-id=<id> \\
        [--limit=N] [--sample-random] [--niche=...] \\
        [--offer-label=...] [--dry-run]

Exit codes:
    0  success
    1  at least one row upsert errored
    2  env missing or CSV unreadable
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_NICHE = "cro_growth_ugc_agency"
DEFAULT_OFFER_LABEL = "pipeline_audit"
DEFAULT_ICP_SCORE = 65
DEFAULT_ICP_TIER = "B"
SOURCE_NAME = "clutch_scraper"

_EMPLOYEE_RANGE_RE = re.compile(r"^\s*([\d,]+)\s*-\s*([\d,]+)\s*$")
_EMPLOYEE_PLUS_RE = re.compile(r"^\s*([\d,]+)\s*\+\s*$")


# ── Pure helpers (unit-tested) ────────────────────────────────────────────────

def _parse_employee_band(raw: str | None) -> int | None:
    """Parse Clutch employee band strings to a midpoint int.

    Examples:
        "2 - 9"          → 5   (floor((2+9)/2) = 5)
        "10 - 49"        → 29
        "50 - 249"       → 149
        "250 - 999"      → 624
        "1,000 - 9,999"  → 5499
        "10,000+"        → 10000
        ""/None/garbage  → None
    """
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None

    m = _EMPLOYEE_RANGE_RE.match(s)
    if m:
        try:
            lo = int(m.group(1).replace(",", ""))
            hi = int(m.group(2).replace(",", ""))
        except ValueError:
            return None
        return (lo + hi) // 2

    m = _EMPLOYEE_PLUS_RE.match(s)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            return None

    return None


def _nullable_str(raw: str | None) -> str | None:
    """Return None for empty/whitespace strings; else stripped value."""
    if raw is None:
        return None
    s = raw.strip()
    return s or None


def _row_to_contact(
    row: dict[str, str],
    *,
    client_id: str,
    niche: str,
    offer_label: str,
) -> dict[str, Any] | None:
    """Map one scraper CSV row to a contacts-table upsert payload.

    Returns None if the row is missing the dedup key (domain) or the
    minimum compose input (company_name). Skip reason is logged by the
    caller.
    """
    domain = _nullable_str(row.get("domain"))
    company = _nullable_str(row.get("company_name"))
    if not domain:
        return None
    if not company:
        return None

    website_content = {
        "homepage_text": row.get("homepage_text", "") or "",
        "about_text": row.get("about_text", "") or "",
        "services_text": row.get("services_text", "") or "",
        "testimonials_text": row.get("testimonials_text", "") or "",
        "portfolio_text": row.get("portfolio_text", "") or "",
    }

    clutch_metadata = {
        "rating": row.get("rating", "") or "",
        "review_count": row.get("review_count", "") or "",
        "hourly_rate": row.get("hourly_rate", "") or "",
        "min_budget": row.get("min_budget", "") or "",
        "services": row.get("services", "") or "",
        "location": row.get("location", "") or "",
        "website": row.get("website", "") or "",
    }

    research_data = {
        "website_content": website_content,
        "clutch_metadata": clutch_metadata,
        "offer_label": offer_label,
        "key_pain_point": None,
        "citable_details": [],
    }

    raw_data = {
        "clutch_url": row.get("clutch_url", "") or "",
        "designrush_url": row.get("designrush_url", "") or "",
        "sources": row.get("sources", "") or "",
        "meta_title": row.get("meta_title", "") or "",
        "meta_description": row.get("meta_description", "") or "",
    }

    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "client_id": client_id,
        "source": SOURCE_NAME,
        "source_id": domain,
        "niche": niche,
        "company": company,
        "company_domain": domain,
        "email": _nullable_str(row.get("best_email")),
        "linkedin_url": _nullable_str(row.get("linkedin")),
        "employees": _parse_employee_band(row.get("employee_count")),
        "timezone": _nullable_str(row.get("timezone")),
        "icp_score": DEFAULT_ICP_SCORE,
        "icp_tier": DEFAULT_ICP_TIER,
        "status": "enriched",
        "enriched_at": now_iso,
        "raw_data": raw_data,
        "research_data": research_data,
    }


# ── I/O glue ──────────────────────────────────────────────────────────────────

def _build_client(url: str, key: str) -> Any:
    """Construct a Supabase client. Factored out for test monkeypatching."""
    from supabase import create_client
    return create_client(url, key)


def _load_rows(
    csv_path: Path,
    *,
    limit: int | None,
    sample_random: bool,
) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    if limit is None or limit >= len(rows):
        return rows
    if sample_random:
        return random.sample(rows, limit)
    return rows[:limit]


def ingest_corpus(
    supabase: Any,
    rows: list[dict[str, str]],
    *,
    client_id: str,
    niche: str,
    offer_label: str,
    dry_run: bool = False,
) -> dict[str, int]:
    summary = {"loaded": 0, "skipped": 0, "errors": 0}

    for idx, row in enumerate(rows, start=1):
        payload = _row_to_contact(
            row,
            client_id=client_id,
            niche=niche,
            offer_label=offer_label,
        )
        if payload is None:
            reason = (
                "missing domain"
                if not _nullable_str(row.get("domain"))
                else "missing company_name"
            )
            logger.info("SKIP row %d: %s", idx, reason)
            summary["skipped"] += 1
            continue

        label = f"row {idx} / {payload['company']} ({payload['source_id']})"

        if dry_run:
            logger.info(
                "DRY-RUN would upsert %s status=enriched email=%s employees=%s",
                label, payload["email"], payload["employees"],
            )
            summary["loaded"] += 1
            continue

        try:
            supabase.table("contacts").upsert(
                payload, on_conflict="client_id,source,source_id"
            ).execute()
            logger.info("UPSERT %s", label)
            summary["loaded"] += 1
        except Exception as e:
            logger.error("FAILED %s: %s", label, e)
            summary["errors"] += 1

    return summary


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest scraped Clutch corpus CSV into contacts "
                    "(status='enriched').",
    )
    parser.add_argument("--csv-path", required=True, help="Path to scraper CSV.")
    parser.add_argument("--client-id", required=True, help="AIOS client_id.")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap number of rows ingested. Default: all.",
    )
    parser.add_argument(
        "--sample-random", action="store_true",
        help="With --limit, random-sample instead of taking first N.",
    )
    parser.add_argument(
        "--niche", default=DEFAULT_NICHE,
        help=f"contacts.niche value (default: {DEFAULT_NICHE}).",
    )
    parser.add_argument(
        "--offer-label", default=DEFAULT_OFFER_LABEL,
        help=f"research_data.offer_label (default: {DEFAULT_OFFER_LABEL}).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview rows without writing to Supabase.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv or sys.argv[1:])

    csv_path = Path(args.csv_path).expanduser().resolve()
    if not csv_path.is_file():
        print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
        return 2

    try:
        rows = _load_rows(
            csv_path, limit=args.limit, sample_random=args.sample_random,
        )
    except OSError as e:
        print(f"ERROR: cannot read CSV {csv_path}: {e}", file=sys.stderr)
        return 2

    logger.info("loaded %d rows from %s", len(rows), csv_path)

    supabase: Any
    if args.dry_run:
        supabase = None  # type: ignore[assignment]
    else:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            print(
                "ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set "
                "in the environment (or loaded from .env before running).",
                file=sys.stderr,
            )
            return 2
        supabase = _build_client(url, key)

    summary = ingest_corpus(
        supabase,
        rows,
        client_id=args.client_id,
        niche=args.niche,
        offer_label=args.offer_label,
        dry_run=args.dry_run,
    )

    prefix = "DRY-RUN " if args.dry_run else ""
    print(
        f"{prefix}ingest complete: "
        f"{summary['loaded']} loaded, "
        f"{summary['skipped']} skipped, "
        f"{summary['errors']} errors"
    )
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
