"""Ingest an operator-curated CSV of pre-resolved contacts into contacts.

Use this when the operator has already identified the decision-maker
(first_name, last_name, title, email, linkedin_url) and wants to feed
those rows into the daemon without running the lead-identity stage.

Contract with the daemon:
    - status='screened' (not 'enriched') so the enrich stage picks these up.
    - enriched_at is NEVER stamped; the enrich stage filters on
      enriched_at IS NULL.
    - first_name is already populated, so the identity stage auto-skips
      each row.
    - icp_score=75 and icp_tier='A' because the operator has already
      qualified these contacts. They bypass scoring.
    - research_data.short_company_name is seeded from the CSV because the
      composer reads it from that path.
    - research_data.citable_details=[] because the enrich stage will fill
      it in.

This script is productised: there is zero client-specific logic. Any
deployment with a pre-resolved CSV can use it by passing --client-id and
letting the per-row niche column flow through.

Required CSV columns:
    company, domain, linkedin_url, first_name, last_name, title, email,
    short_company_name, niche, notes

Usage:
    uv run python scripts/ingest_preresolved_contacts.py \\
        --csv-path=<path> --client-id=<id> \\
        [--limit=N] [--dry-run]

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
import sys
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

SOURCE_NAME = "manual_pre_resolved"
PRE_RESOLVED_ICP_SCORE = 75
PRE_RESOLVED_ICP_TIER = "A"
INITIAL_STATUS = "screened"


# ── Pure helpers (unit-tested) ────────────────────────────────────────────────

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
) -> dict[str, Any] | None:
    """Map one operator CSV row to a contacts-table upsert payload.

    Returns None if the row is missing the dedup key (email) or the
    minimum identity field (first_name). Skip reason is logged by the
    caller.
    """
    email = _nullable_str(row.get("email"))
    first_name = _nullable_str(row.get("first_name"))
    if not email:
        return None
    if not first_name:
        return None

    short_company_name = _nullable_str(row.get("short_company_name"))
    operator_notes = _nullable_str(row.get("notes"))

    research_data: dict[str, Any] = {
        "citable_details": [],
    }
    if short_company_name:
        research_data["short_company_name"] = short_company_name

    raw_data: dict[str, Any] = {}
    if operator_notes:
        raw_data["operator_notes"] = operator_notes

    payload: dict[str, Any] = {
        "client_id": client_id,
        "source": SOURCE_NAME,
        "source_id": email,
        "first_name": first_name,
        "last_name": _nullable_str(row.get("last_name")),
        "title": _nullable_str(row.get("title")),
        "email": email,
        "linkedin_url": _nullable_str(row.get("linkedin_url")),
        "company": _nullable_str(row.get("company")),
        "company_domain": _nullable_str(row.get("domain")),
        "niche": _nullable_str(row.get("niche")),
        "icp_score": PRE_RESOLVED_ICP_SCORE,
        "icp_tier": PRE_RESOLVED_ICP_TIER,
        "status": INITIAL_STATUS,
        "raw_data": raw_data,
        "research_data": research_data,
    }
    # NB: enriched_at is intentionally omitted so the enrich stage
    # (filter: enriched_at IS NULL) can pick this row up.
    return payload


# ── I/O glue ──────────────────────────────────────────────────────────────────

def _build_client(url: str, key: str) -> Any:
    """Construct a Supabase client. Factored out for test monkeypatching."""
    from supabase import create_client
    return create_client(url, key)


def _load_rows(csv_path: Path, *, limit: int | None) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    if limit is None or limit >= len(rows):
        return rows
    return rows[:limit]


def ingest_preresolved(
    supabase: Any,
    rows: list[dict[str, str]],
    *,
    client_id: str,
    dry_run: bool = False,
) -> dict[str, int]:
    summary = {"loaded": 0, "skipped": 0, "errors": 0}

    for idx, row in enumerate(rows, start=1):
        payload = _row_to_contact(row, client_id=client_id)
        if payload is None:
            if not _nullable_str(row.get("email")):
                reason = "missing email"
            else:
                reason = "missing first_name"
            logger.info("SKIP row %d: %s", idx, reason)
            summary["skipped"] += 1
            continue

        label = f"row {idx} / {payload['first_name']} <{payload['source_id']}>"

        if dry_run:
            logger.info(
                "DRY-RUN would upsert %s status=%s icp_tier=%s",
                label, payload["status"], payload["icp_tier"],
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
        description="Ingest an operator-curated pre-resolved contacts CSV "
                    "into contacts (status='screened').",
    )
    parser.add_argument("--csv-path", required=True, help="Path to CSV.")
    parser.add_argument("--client-id", required=True, help="AIOS client_id.")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap number of rows ingested. Default: all.",
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
        rows = _load_rows(csv_path, limit=args.limit)
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

    summary = ingest_preresolved(
        supabase,
        rows,
        client_id=args.client_id,
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
