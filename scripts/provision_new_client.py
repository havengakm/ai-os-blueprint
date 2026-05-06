"""New-client bootstrap script.

Plan 2 Phase 6 Task 2.6.1. Single command spins up a new per-client
AIOS silo:

  uv run python scripts/provision_new_client.py \\
    --client-id=acme-co-zero \\
    --client-name="Acme Co" \\
    --niche=creative_branding \\
    --offer-label=aios_scout_deployment \\
    --tier-budgets-cents='{"A":200,"B":100,"C":50,"D":25}'

Steps:

  1. Validate args (client_id format, niche existence, JSON-parsing
     tier_budgets_cents).
  2. Build a default client_config from args. Run
     ``assert_valid_client_config`` (Task 2.6.2) — caller fills in
     icp / tier_thresholds later, which the validator re-checks at
     update time.
  3. Insert ``clients`` + ``client_config`` + ``autonomy_rules`` rows
     into Supabase. Idempotent — if the client row already exists,
     the script reports ``already_provisioned=True`` and skips DB
     inserts (still bootstraps folders + prints checklist).
  4. Bootstrap per-client folders under ``context/<id>``,
     ``data/knowledge/personal/<id>``, ``data/knowledge/company/<id>``.
  5. Print human-only checklist.

Migrations are NOT run by this script — that's the operator's
responsibility. The script assumes migrations are already applied
to the target Supabase project.

Per ``feedback_per_company_aios_silo``: foundation
(skills/rules/departments/agents/systems) is shared template;
context/ + data/ content is per-client.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Repo-root path setup so ``from systems.X import Y`` works when this
# script is run directly. Matches scripts/run_optimizer_weekly.py +
# scripts/load_components.py patterns.
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


from aios.scout.pipeline.validate_config import assert_valid_client_config  # noqa: E402


# ---------------------------------------------------------------------------
# Defaults                                                                    #
# ---------------------------------------------------------------------------


DEFAULT_TIER_THRESHOLDS: dict[str, int] = {
    "A": 80,
    "B": 60,
    "C": 40,
    "D": 25,
    "archive_floor": 10,
}

# Allowed client_id pattern: lowercase alnum + dash + underscore. ≤ 64 chars.
_CLIENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# Default location for sequence niches. Tests override.
_DEFAULT_SEQUENCES_ROOT = Path("data/reference/sequences")


# ---------------------------------------------------------------------------
# Result dataclass                                                            #
# ---------------------------------------------------------------------------


@dataclass
class ProvisionResult:
    client_id: str
    already_provisioned: bool = False
    db_rows_inserted: dict[str, int] = field(default_factory=dict)
    created_paths: list[Path] = field(default_factory=list)
    already_present_paths: list[Path] = field(default_factory=list)
    would_create_paths: list[Path] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation                                                                  #
# ---------------------------------------------------------------------------


def validate_client_id(client_id: str) -> None:
    """Reject whitespace, special chars, uppercase, empty, > 64 chars."""
    if not isinstance(client_id, str):
        raise ValueError(f"client_id must be a string; got {type(client_id).__name__}")
    if not _CLIENT_ID_RE.match(client_id):
        raise ValueError(
            f"client_id {client_id!r} invalid — must be lowercase alnum + "
            "'-' + '_', 1-64 chars, starting with alnum"
        )


def validate_niche_exists(
    niche: str,
    *,
    sequences_root: Path | None = None,
) -> None:
    root = sequences_root or _DEFAULT_SEQUENCES_ROOT
    if not (root / niche).is_dir():
        existing = sorted(
            [p.name for p in root.iterdir() if p.is_dir()]
        ) if root.is_dir() else []
        raise ValueError(
            f"niche {niche!r} not found under {root}. "
            f"Existing niches: {existing}"
        )


# ---------------------------------------------------------------------------
# Config + folder bootstrap                                                   #
# ---------------------------------------------------------------------------


def build_default_client_config(
    *,
    client_id: str,
    client_name: str,
    niche: str,
    offer_label: str,
    tier_budgets_cents: dict[str, int],
) -> dict[str, Any]:
    """Build the initial client_config row payload.

    Operator fills in ``icp`` (titles / geographies / industries /
    employee_min/max / positive_examples / negative_examples) post-bootstrap.
    The validator re-runs on each update via the (future)
    client_config update endpoint.
    """
    return {
        "client_id": client_id,
        "client_name": client_name,
        "niche": niche,
        "offer_label": offer_label,
        "tier_budgets_cents": dict(tier_budgets_cents),
        "tier_thresholds": dict(DEFAULT_TIER_THRESHOLDS),
        "tier_spent_cents": {tier: 0 for tier in tier_budgets_cents},
        "icp": {},
    }


def bootstrap_client_folders(
    client_id: str,
    *,
    repo_root: Path | None = None,
    dry_run: bool = False,
) -> ProvisionResult:
    """Create per-client folders under ``context/`` + ``data/knowledge/``.

    Idempotent — existing dirs are reported as ``already_present_paths``.
    With ``dry_run=True``, no dirs are created; ``would_create_paths``
    lists the targets.
    """
    root = repo_root or Path.cwd()
    targets = [
        root / "context" / client_id,
        root / "data" / "knowledge" / "personal" / client_id,
        root / "data" / "knowledge" / "company" / client_id,
    ]

    result = ProvisionResult(client_id=client_id)

    for target in targets:
        if target.exists():
            result.already_present_paths.append(target)
            continue
        if dry_run:
            result.would_create_paths.append(target)
            continue
        target.mkdir(parents=True, exist_ok=False)
        result.created_paths.append(target)

    return result


# ---------------------------------------------------------------------------
# Human checklist                                                             #
# ---------------------------------------------------------------------------


def human_checklist(client_id: str) -> str:
    return f"""
Human-only steps remaining for client {client_id!r}:

  1. Write personal context at context/{client_id}/ (operator profile,
     ICP narrative, brand voice, decision-making history).

  2. Write company facts at data/knowledge/company/{client_id}/
     (products, pricing, case studies, testimonials).

  3. Write personal knowledge at data/knowledge/personal/{client_id}/
     (operator preferences, biographical context, captured conversations).

  4. Fill in client_config.icp via the (future) update endpoint OR
     operator-side SQL: titles (>=4 chars each), geographies (full
     country names, NOT 'US'/'UK'/'AU' codes), industries,
     employee_min/employee_max, positive_examples, negative_examples,
     uncertain_zone (if overriding the 40-60 default).

  5. Approve template variants per niche in component_registry.
     Variants stay status='draft' until operator promotes them to
     'approved'; only approved variants get pulled by the bandit at
     send time.

  6. Configure send_account rows for the client's mailboxes (provider,
     daily_cap, esp_account_id). Beacon picks accounts from this table.

  7. Configure cron entries:
     - Pipeline triggers (pull / score / screen / identity / enrich / render)
     - CoolOffRuntime.run_cycle (daily)
     - RecommendationEngine.expire_stale (daily)
     - WeeklyReview (Monday 6am operator-local)

  8. Run a 1-contact end-to-end smoke test before enabling autonomous
     send (see Phase 7 Task 2.7.1 acceptance harness).
""".strip()


# ---------------------------------------------------------------------------
# Provisioner — orchestrates everything                                       #
# ---------------------------------------------------------------------------


async def provision(
    *,
    client_id: str,
    client_name: str,
    niche: str,
    offer_label: str,
    tier_budgets_cents: dict[str, int],
    supabase_client: Any | None = None,
    repo_root: Path | None = None,
    dry_run: bool = False,
) -> ProvisionResult:
    """End-to-end provisioning flow. Tests inject ``supabase_client`` +
    ``repo_root``; production reads from env."""
    validate_client_id(client_id)
    validate_niche_exists(niche)

    cfg = build_default_client_config(
        client_id=client_id,
        client_name=client_name,
        niche=niche,
        offer_label=offer_label,
        tier_budgets_cents=tier_budgets_cents,
    )
    assert_valid_client_config(cfg)

    # ----- DB inserts (idempotent) ------------------------------------ #
    result = ProvisionResult(client_id=client_id)
    if supabase_client is None:
        supabase_client = _get_supabase_client()

    existing = (
        supabase_client.table("clients")
        .select("id")
        .eq("id", client_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        result.already_provisioned = True
    elif not dry_run:
        # Insert clients row
        supabase_client.table("clients").insert(
            {"id": client_id, "name": client_name}
        ).execute()
        # Insert client_config row
        supabase_client.table("client_config").insert(cfg).execute()
        # Bootstrap autonomy_rules — start everything at 'suggest' per
        # CLAUDE.md "Start at 'suggest' for everything".
        supabase_client.table("autonomy_rules").insert(
            {"client_id": client_id, "action_type": "send_email", "level": "suggest"}
        ).execute()
        result.db_rows_inserted = {
            "clients": 1, "client_config": 1, "autonomy_rules": 1,
        }

    # ----- Folder bootstrap ------------------------------------------ #
    folder_result = bootstrap_client_folders(
        client_id, repo_root=repo_root, dry_run=dry_run,
    )
    result.created_paths = folder_result.created_paths
    result.already_present_paths = folder_result.already_present_paths
    result.would_create_paths = folder_result.would_create_paths

    return result


def _get_supabase_client() -> Any:
    """Production Supabase client. Tests inject directly via the
    ``supabase_client`` arg to ``provision()``."""
    import os
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit(
            "SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY required in env"
        )
    return create_client(url, key)


# ---------------------------------------------------------------------------
# CLI                                                                         #
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision a new client AIOS silo",
    )
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-name", required=True)
    parser.add_argument("--niche", required=True)
    parser.add_argument("--offer-label", required=True)
    parser.add_argument(
        "--tier-budgets-cents",
        required=True,
        help='JSON dict, e.g. \'{"A":200,"B":100,"C":50,"D":25}\'',
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        tier_budgets = json.loads(args.tier_budgets_cents)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--tier-budgets-cents must be valid JSON: {exc}")

    result = asyncio.run(
        provision(
            client_id=args.client_id,
            client_name=args.client_name,
            niche=args.niche,
            offer_label=args.offer_label,
            tier_budgets_cents=tier_budgets,
            dry_run=args.dry_run,
        )
    )

    if result.already_provisioned:
        print(f"client {args.client_id!r} already provisioned in DB; "
              f"skipped DB inserts.")
    else:
        if args.dry_run:
            print(f"DRY RUN — would insert {result.db_rows_inserted} rows + create {result.would_create_paths}")
        else:
            print(f"inserted: {result.db_rows_inserted}")

    if result.created_paths:
        print(f"created folders: {[str(p) for p in result.created_paths]}")
    if result.already_present_paths:
        print(f"already present: {[str(p) for p in result.already_present_paths]}")

    print("")
    print(human_checklist(args.client_id))


if __name__ == "__main__":
    main()
