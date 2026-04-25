"""Seed autonomy_rules rows for a client across ALL decision_types.

All new clients start at 'suggest' for every action type, per the
progressive autonomy policy (see feedback_progressive_autonomy). The script
is idempotent: existing rows are skipped (upsert respects the
UNIQUE(client_id, action_type) constraint from migration 001).

ACTION_TYPES is sourced from a constant below, not from a DB query. This
keeps the script deterministic + auditable: the set of decision_types that
require autonomy gating is a product of schema migration history, and
changes to it should be an explicit code edit alongside the migration.

Usage:
    uv run python scripts/seed_autonomy_rules.py --client-id=<id> [--dry-run]
"""
from __future__ import annotations

# Auto-load .env so the script works from a fresh shell without `source .env`
# or direnv. Plan 1.5 Task 1.5.2 (follow-ups-plan1.md item 2).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import argparse
import logging
import os
import sys
from typing import Any

# 19 action_types, sourced from:
#   - migration 001: 12 original decision_types
#   - migration 005: 7 Plan-1 additions
# Order is stable for deterministic dry-run output.
ACTION_TYPES: tuple[str, ...] = (
    # 001_foundation.sql (12)
    "copy_variant",
    "icp_threshold",
    "template_choice",
    "signal_weight",
    "send_timing",
    "channel_selection",
    "meeting_booking",
    "reply_handling",
    "manual_override",
    "system_config",
    "enrichment_choice",
    "framework_selection",
    # 005_foundation_completion.sql (8)
    "research_contact",
    "render_draft",
    "component_selection",
    "score_contact",
    "screen_contact",
    "identity_lookup",
    "source_selection",
    "enrich_contact",
)

logger = logging.getLogger(__name__)


def _build_client(url: str, key: str) -> Any:
    """Construct a Supabase client. Factored out for test monkeypatching."""
    from supabase import create_client
    return create_client(url, key)


def seed_autonomy_rules(
    supabase: Any,
    client_id: str,
    *,
    dry_run: bool = False,
    action_types: tuple[str, ...] = ACTION_TYPES,
) -> dict[str, int]:
    """Upsert autonomy_rules rows for client_id across all action_types.

    Returns:
        {'created': N, 'skipped': M, 'errors': E} summary.

    Behaviour:
        - Existing rows are left alone (upsert uses UNIQUE(client_id,
          action_type) from 001).
        - Dry-run logs plans without writing.
    """
    summary = {"created": 0, "skipped": 0, "errors": 0}

    # Pre-fetch existing rules so we can classify each action_type as
    # 'would create' vs 'would skip' for the dry-run output + summary.
    existing_action_types: set[str] = set()
    try:
        resp = (
            supabase.table("autonomy_rules")
            .select("action_type")
            .eq("client_id", client_id)
            .execute()
        )
        existing_action_types = {r["action_type"] for r in (resp.data or [])}
    except Exception as e:
        logger.warning("Could not pre-fetch existing rules: %s", e)

    for action_type in action_types:
        exists = action_type in existing_action_types
        if exists:
            logger.info("SKIP %s / %s (already exists)", client_id, action_type)
            summary["skipped"] += 1
            continue

        if dry_run:
            logger.info(
                "DRY-RUN would create: client_id=%s action_type=%s level=suggest",
                client_id, action_type,
            )
            summary["created"] += 1
            continue

        try:
            supabase.table("autonomy_rules").upsert(
                {
                    "client_id": client_id,
                    "action_type": action_type,
                    "autonomy_level": "suggest",
                },
                on_conflict="client_id,action_type",
            ).execute()
            logger.info("CREATED %s / %s at level=suggest", client_id, action_type)
            summary["created"] += 1
        except Exception as e:
            logger.error("FAILED %s / %s: %s", client_id, action_type, e)
            summary["errors"] += 1

    return summary


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed autonomy_rules rows for a client at autonomy_level='suggest'."
    )
    parser.add_argument(
        "--client-id",
        required=True,
        help="Client ID to seed autonomy rules for.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be upserted without writing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv or sys.argv[1:])

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print(
            "ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in the "
            "environment (or loaded from .env before running).",
            file=sys.stderr,
        )
        return 1

    supabase = _build_client(url, key)
    summary = seed_autonomy_rules(supabase, args.client_id, dry_run=args.dry_run)

    prefix = "DRY-RUN " if args.dry_run else ""
    print(
        f"{prefix}autonomy_rules seed complete for client_id={args.client_id}: "
        f"{summary['created']} created, {summary['skipped']} skipped, "
        f"{summary['errors']} errors"
    )
    return 0 if summary["errors"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
