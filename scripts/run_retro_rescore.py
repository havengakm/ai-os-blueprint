"""Retro-rescore admin CLI — re-run score_v2 + assign_tier across all
already-scored contacts under the current scoring model.

Slice 27 (2026-04-29) ships an expanded intent signal table (5 + 2
LinkedIn-reserved). Existing contacts stored under the old 2-binary
model need to be brought in line with the new model. This script
walks ``contacts WHERE icp_score IS NOT NULL``, re-scores each with
the live ``score_v2`` + ``assign_tier``, and writes the new score +
tier back when they differ.

Idempotent — running twice in a row produces zero-update on the
second pass. Safe to run from cron, though typically a one-shot
after a scoring change.

Usage:
  uv run python scripts/run_retro_rescore.py --client-id=<id> [--dry-run]
  uv run python scripts/run_retro_rescore.py --all [--dry-run]

Default is --dry-run; pass --apply to actually write changes.

Stdout: one structured line per client summarising changed/unchanged
counts + tier flow (A→B, B→A, etc).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _get_supabase() -> Any:
    """Build a Supabase client from env. Tests monkeypatch this."""
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = (
        os.environ.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )
    if not key:
        raise SystemExit("SUPABASE_SERVICE_KEY (or _ROLE_KEY) must be set")
    return create_client(url, key)


def _build_contact_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Extract the score-relevant fields from a contacts row."""
    return {
        "industry": row.get("industry"),
        "title": row.get("title"),
        "employees": row.get("employees"),
        "geography": row.get("geography"),
        "email": row.get("email"),
        "email_verified": row.get("email_verified"),
        "linkedin_url": row.get("linkedin_url"),
        "phone": row.get("phone"),
        "raw_data": row.get("raw_data") or {},
        "research_data": row.get("research_data") or {},
    }


async def _rescore_one_client(
    supabase: Any, client_id: str, *, apply: bool,
) -> dict[str, Any]:
    """Re-score every contact for ``client_id``. Returns summary dict."""
    from aios.scout.pipeline.score import assign_tier, score_v2

    cfg_resp = (
        supabase.table("client_config")
        .select("weights, tier_thresholds")
        .eq("client_id", client_id)
        .limit(1)
        .execute()
    )
    if not cfg_resp.data:
        return {"client_id": client_id, "error": "no_client_config"}
    cfg = dict(cfg_resp.data[0])

    # icp lives in a separate table; mirror SupabaseScoreBackend.get_client_config.
    icp_resp = (
        supabase.table("icp_definitions")
        .select(
            "industries, titles, employee_min, employee_max, "
            "geographies, blacklist_companies, blacklist_domains"
        )
        .eq("client_id", client_id)
        .limit(1)
        .execute()
    )
    icp = (icp_resp.data or [{}])[0]

    client_config = {
        "weights": cfg.get("weights") or {},
        "tier_thresholds": cfg.get("tier_thresholds") or {},
        "icp": icp,
    }

    contacts_resp = (
        supabase.table("contacts")
        .select(
            "id,icp_score,icp_tier,industry,title,employees,geography,email,"
            "email_verified,linkedin_url,phone,raw_data,research_data"
        )
        .eq("client_id", client_id)
        .not_.is_("icp_score", "null")
        .execute()
    )
    contacts = contacts_resp.data or []

    score_changes: list[dict[str, Any]] = []
    tier_flow: Counter[tuple[str, str]] = Counter()
    unchanged = 0

    for row in contacts:
        contact = _build_contact_dict(row)
        new_score = score_v2(contact, client_config)
        new_tier = assign_tier(new_score, client_config)
        old_score = row.get("icp_score")
        old_tier = row.get("icp_tier")

        if new_score == old_score and new_tier == old_tier:
            unchanged += 1
            continue

        score_changes.append({
            "id": row["id"],
            "old_score": old_score,
            "new_score": new_score,
            "old_tier": old_tier,
            "new_tier": new_tier,
        })
        tier_flow[(old_tier or "?", new_tier or "?")] += 1

        if apply:
            supabase.table("contacts").update({
                "icp_score": new_score,
                "icp_tier": new_tier,
            }).eq("id", row["id"]).execute()

    return {
        "client_id": client_id,
        "total": len(contacts),
        "changed": len(score_changes),
        "unchanged": unchanged,
        "tier_flow": dict(tier_flow),
        "applied": apply,
        "samples": score_changes[:5],
    }


async def _run(args: argparse.Namespace) -> int:
    supabase = _get_supabase()

    if args.all:
        clients_resp = (
            supabase.table("clients").select("id").eq("status", "active").execute()
        )
        client_ids = [r["id"] for r in clients_resp.data or []]
    elif args.client_id:
        client_ids = [args.client_id]
    else:
        print("error: pass --client-id <id> or --all", file=sys.stderr)
        return 1

    apply = bool(args.apply)
    if not apply:
        print("[DRY RUN] no contacts will be updated. Pass --apply to commit.")

    for cid in client_ids:
        summary = await _rescore_one_client(supabase, cid, apply=apply)
        print(summary)
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--client-id", help="Specific client to rescore.")
    p.add_argument("--all", action="store_true", help="Rescore every active client.")
    p.add_argument("--apply", action="store_true", help="Actually write updates (default: dry-run).")
    args = p.parse_args()
    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
