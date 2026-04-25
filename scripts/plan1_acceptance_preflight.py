"""Plan 1 acceptance preflight - read-only seed-data checks.

Runs BEFORE ``scripts/run_daemon_once.py --dry-run`` to prove the
requested client has enough seed data to exercise the full 7-stage
pipeline and produce a meaningful acceptance report. All checks are
read-only: the script never writes to Supabase.

Checks (in order):

    1. env            - 4 required keys present
    2. schema         - 10 critical tables reachable
    3. client         - clients.status='active' + client_config row
    4. context        - business_context + client_facts each >= 1 row
    5. knowledge      - knowledge_base >= 1 row (global)
    6. autonomy_rules - >= 1 row per pipeline decision_type
    7. components     - component_variants >= 1 approved row per type
                        (subject_line/icebreaker/pain_hook/offer_frame/cta/signature)
                        for at least one (niche, offer_label) pairing
    8. contacts       - >= 10 rows with status IN ('new','screened','ready','enriched')

Usage:
    uv run python scripts/plan1_acceptance_preflight.py --client-id=<id> [--json]

Exit codes:
    0  all checks pass
    1  at least one blocking check failed
    2  env missing (cannot connect to Supabase)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Load .env from the repo root so os.environ reflects what pydantic-settings
# would see. Matches the daemon / run_daemon_once behaviour, so preflight and
# the actual run can never disagree on whether env is configured.
try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────────────

REQUIRED_ENV: tuple[str, ...] = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "VOYAGE_API_KEY",
    "ANTHROPIC_API_KEY",
)

SCHEMA_TABLES: tuple[str, ...] = (
    "clients",
    "client_config",
    "contacts",
    "outreach_drafts",
    "decision_log",
    "business_context",
    "client_facts",
    "knowledge_base",
    "autonomy_rules",
    "component_variants",
)

# 7 pipeline decision_types the acceptance run must exercise.
PIPELINE_DECISION_TYPES: tuple[str, ...] = (
    "source_selection",
    "score_contact",
    "screen_contact",
    "identity_lookup",
    "enrich_contact",
    "render_draft",
    "research_contact",
)

COMPONENT_TYPES: tuple[str, ...] = (
    "subject_line",
    "icebreaker",
    "pain_hook",
    "offer_frame",
    "cta",
    "signature",
)

# Pipeline-eligible contact statuses - matches what exists in the DB per
# systems/scout/supabase_backends/ (pull inserts 'new'; screen flips to
# 'screened' then 'ready'; enrich flips to 'enriched').
PIPELINE_ELIGIBLE_STATUSES: tuple[str, ...] = (
    "new", "screened", "ready", "enriched",
)

MIN_CONTACTS_FOR_MEANINGFUL_RUN = 10


# ── Check result type ────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    """One preflight check outcome."""

    name: str
    passed: bool
    detail: str
    fix: str | None = None


@dataclass
class PreflightReport:
    """Aggregate of every check run."""

    client_id: str
    checks: list[CheckResult] = field(default_factory=list)
    env_missing: list[str] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return not self.env_missing and all(c.passed for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "all_passed": self.all_passed,
            "env_missing": list(self.env_missing),
            "checks": [asdict(c) for c in self.checks],
        }


# ── Supabase builder (factored out so tests monkeypatch) ──────────────────────

def _build_client(url: str, key: str) -> Any:
    from supabase import create_client
    return create_client(url, key)


# ── Individual checks ─────────────────────────────────────────────────────────

def check_env() -> list[str]:
    """Return the list of missing env vars (empty = pass)."""
    return [name for name in REQUIRED_ENV if not os.environ.get(name)]


def check_schema(supabase: Any) -> list[CheckResult]:
    """For each critical table, verify both:

      1. It exists in information_schema.tables (via the
         preflight_existing_tables view from migration 013).
      2. It is reachable via a PostgREST SELECT.

    Cross-checking against information_schema guards against PostgREST
    returning 200 from a permission cache state even when the table is
    actually absent from the schema. See follow-ups-plan1.md item 1.
    """
    # Step 1: pull the authoritative list of public-schema table names.
    try:
        view_resp = (
            supabase.table("preflight_existing_tables")
            .select("table_name")
            .execute()
        )
        existing_tables = {
            r.get("table_name") for r in (view_resp.data or [])
        }
    except Exception:
        # View itself errored (e.g. permission denied). Treat as empty:
        # every required table will be flagged with the migration-013
        # fix message below.
        existing_tables = set()

    results: list[CheckResult] = []
    for table in SCHEMA_TABLES:
        in_information_schema = table in existing_tables

        # Step 2: PostgREST connectivity check.
        select_ok = False
        select_error: str | None = None
        try:
            supabase.table(table).select("*").limit(1).execute()
            select_ok = True
        except Exception as exc:
            select_error = str(exc)

        if in_information_schema and select_ok:
            results.append(CheckResult(
                name=f"schema:{table}",
                passed=True,
                detail=(
                    f"table {table!r} present in information_schema "
                    "and reachable"
                ),
            ))
        elif not in_information_schema:
            results.append(CheckResult(
                name=f"schema:{table}",
                passed=False,
                detail=(
                    f"table {table!r} missing from information_schema.tables "
                    f"(PostgREST cache may report it reachable; not "
                    f"authoritative)"
                ),
                fix=(
                    f"Apply migration 013 (creates preflight_existing_tables "
                    f"view). If 013 is applied and {table} is still missing, "
                    f"apply migrations 001-006 to seed the schema."
                ),
            ))
        else:
            results.append(CheckResult(
                name=f"schema:{table}",
                passed=False,
                detail=(
                    f"table {table!r} present in information_schema but "
                    f"PostgREST query failed: {select_error}"
                ),
                fix=(
                    f"Table exists in the database but PostgREST cannot "
                    f"read it. Check service-role grants and RLS policies "
                    f"on {table}."
                ),
            ))
    return results


def check_client_exists(supabase: Any, client_id: str) -> CheckResult:
    """clients.status='active' AND client_config row present."""
    try:
        clients_resp = (
            supabase.table("clients")
            .select("id,status")
            .eq("id", client_id)
            .execute()
        )
        rows = clients_resp.data or []
        if not rows:
            return CheckResult(
                name="client_exists",
                passed=False,
                detail=f"no clients row for client_id={client_id!r}",
                fix=(
                    "Insert a clients row first. "
                    f"INSERT INTO clients (id, name, status) VALUES "
                    f"('{client_id}', '<display name>', 'active');"
                ),
            )
        if rows[0].get("status") != "active":
            return CheckResult(
                name="client_exists",
                passed=False,
                detail=(
                    f"clients.status={rows[0].get('status')!r} "
                    f"(expected 'active')"
                ),
                fix=f"UPDATE clients SET status='active' WHERE id='{client_id}';",
            )
    except Exception as exc:
        return CheckResult(
            name="client_exists",
            passed=False,
            detail=f"clients query errored: {exc}",
            fix="Verify clients table exists and service-role key has RLS bypass.",
        )

    try:
        cfg_resp = (
            supabase.table("client_config")
            .select("client_id")
            .eq("client_id", client_id)
            .execute()
        )
        cfg_rows = cfg_resp.data or []
        if not cfg_rows:
            return CheckResult(
                name="client_exists",
                passed=False,
                detail=f"no client_config row for client_id={client_id!r}",
                fix=(
                    "Insert a client_config row. See scripts/setup_client.sh "
                    "or INSERT INTO client_config (client_id, ...) VALUES (...)."
                ),
            )
    except Exception as exc:
        return CheckResult(
            name="client_exists",
            passed=False,
            detail=f"client_config query errored: {exc}",
            fix="Verify client_config table exists (migration 002).",
        )

    return CheckResult(
        name="client_exists",
        passed=True,
        detail=f"client {client_id!r} active + client_config row present",
    )


def check_context_seeded(supabase: Any, client_id: str) -> list[CheckResult]:
    """business_context + client_facts each have >= 1 row for client_id."""
    results: list[CheckResult] = []
    for table in ("business_context", "client_facts"):
        try:
            resp = (
                supabase.table(table)
                .select("id")
                .eq("client_id", client_id)
                .limit(1)
                .execute()
            )
            rows = resp.data or []
            if not rows:
                results.append(CheckResult(
                    name=f"context:{table}",
                    passed=False,
                    detail=f"no {table} rows for client_id={client_id!r}",
                    fix=(
                        f"Run `uv run python scripts/load_context.py "
                        f"--client-id={client_id}` to seed {table} "
                        "from context/ markdown files. (If that script does "
                        "not exist in this worktree, seed rows manually.)"
                    ),
                ))
            else:
                results.append(CheckResult(
                    name=f"context:{table}",
                    passed=True,
                    detail=f"{table} has >= 1 row for client_id",
                ))
        except Exception as exc:
            results.append(CheckResult(
                name=f"context:{table}",
                passed=False,
                detail=f"{table} query errored: {exc}",
                fix=f"Check {table} exists (migration 005).",
            ))
    return results


def check_knowledge_seeded(supabase: Any) -> CheckResult:
    """knowledge_base has >= 1 row (global, not per-client)."""
    try:
        resp = (
            supabase.table("knowledge_base")
            .select("id")
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return CheckResult(
                name="knowledge_seeded",
                passed=False,
                detail="knowledge_base has 0 rows",
                fix=(
                    "Run `uv run python scripts/load_knowledge.py` to import "
                    "expert frameworks into knowledge_base. (If that script "
                    "does not exist in this worktree, seed rows manually.)"
                ),
            )
        return CheckResult(
            name="knowledge_seeded",
            passed=True,
            detail="knowledge_base has >= 1 row",
        )
    except Exception as exc:
        return CheckResult(
            name="knowledge_seeded",
            passed=False,
            detail=f"knowledge_base query errored: {exc}",
            fix="Check knowledge_base exists (migration 001).",
        )


def check_autonomy_rules(supabase: Any, client_id: str) -> CheckResult:
    """At least one autonomy_rules row per pipeline decision_type."""
    try:
        resp = (
            supabase.table("autonomy_rules")
            .select("action_type")
            .eq("client_id", client_id)
            .execute()
        )
        rows = resp.data or []
        seeded = {r.get("action_type") for r in rows}
        missing = [t for t in PIPELINE_DECISION_TYPES if t not in seeded]
        if missing:
            return CheckResult(
                name="autonomy_rules",
                passed=False,
                detail=(
                    f"missing autonomy_rules action_types: {sorted(missing)}"
                ),
                fix=(
                    f"Run `uv run python scripts/seed_autonomy_rules.py "
                    f"--client-id={client_id}` to seed all 19 action_types "
                    "at level='suggest'."
                ),
            )
        return CheckResult(
            name="autonomy_rules",
            passed=True,
            detail=(
                f"all {len(PIPELINE_DECISION_TYPES)} pipeline "
                "action_types seeded"
            ),
        )
    except Exception as exc:
        return CheckResult(
            name="autonomy_rules",
            passed=False,
            detail=f"autonomy_rules query errored: {exc}",
            fix="Check autonomy_rules exists (migration 001 + 005).",
        )


def check_component_variants(supabase: Any, client_id: str) -> CheckResult:
    """At least one (niche, offer_label) pairing with all 6 approved component
    types present."""
    try:
        resp = (
            supabase.table("component_variants")
            .select("niche,offer_label,component_type,status")
            .eq("client_id", client_id)
            .eq("status", "approved")
            .execute()
        )
        rows = resp.data or []
    except Exception as exc:
        return CheckResult(
            name="component_variants",
            passed=False,
            detail=f"component_variants query errored: {exc}",
            fix="Check component_variants exists (migration 006).",
        )

    # Group by (niche, offer_label) → set of component_types.
    pairings: dict[tuple[str, str], set[str]] = {}
    for r in rows:
        key = (r.get("niche") or "", r.get("offer_label") or "")
        pairings.setdefault(key, set()).add(r.get("component_type") or "")

    complete_pairings = [
        pair for pair, types in pairings.items()
        if set(COMPONENT_TYPES).issubset(types)
    ]

    if not complete_pairings:
        detail = (
            f"no complete (niche, offer_label) pairing has all 6 approved "
            f"component types. Inspected {len(rows)} approved rows across "
            f"{len(pairings)} pairings."
        )
        return CheckResult(
            name="component_variants",
            passed=False,
            detail=detail,
            fix=(
                f"Run `uv run python scripts/load_components.py "
                f"--client-id={client_id}` to seed component_variants from "
                "YAML. Ensure at least one (niche, offer_label) YAML file "
                "has all 6 component types at status='approved'."
            ),
        )

    return CheckResult(
        name="component_variants",
        passed=True,
        detail=(
            f"{len(complete_pairings)} (niche, offer_label) pairing(s) "
            "have all 6 approved component types"
        ),
    )


def check_contact_count(supabase: Any, client_id: str) -> CheckResult:
    """At least MIN_CONTACTS_FOR_MEANINGFUL_RUN contacts in pipeline-eligible
    statuses. Warn (not fail) if all contacts are already 'sent'."""
    try:
        resp = (
            supabase.table("contacts")
            .select("id,status")
            .eq("client_id", client_id)
            .execute()
        )
        rows = resp.data or []
    except Exception as exc:
        return CheckResult(
            name="contact_count",
            passed=False,
            detail=f"contacts query errored: {exc}",
            fix="Check contacts table exists (migration 002).",
        )

    eligible = [r for r in rows if r.get("status") in PIPELINE_ELIGIBLE_STATUSES]
    total = len(rows)

    if len(eligible) < MIN_CONTACTS_FOR_MEANINGFUL_RUN:
        # Distinguish "no contacts" from "all sent" for a better fix message.
        all_sent = total > 0 and all(
            r.get("status") == "sent" for r in rows
        )
        if all_sent:
            return CheckResult(
                name="contact_count",
                passed=False,
                detail=(
                    f"{total} contacts but all in status='sent' - compose "
                    "stage will have nothing to do"
                ),
                fix=(
                    "Reset a subset of contacts to status='enriched' OR run "
                    "the pull stage to bring in fresh contacts."
                ),
            )
        return CheckResult(
            name="contact_count",
            passed=False,
            detail=(
                f"only {len(eligible)} pipeline-eligible contacts "
                f"(need >= {MIN_CONTACTS_FOR_MEANINGFUL_RUN})"
            ),
            fix=(
                f"Run `uv run python scripts/run_daemon_once.py "
                f"--client-id={client_id}` with stages=pull first to seed "
                "contacts, OR insert fixture contacts directly for testing."
            ),
        )

    return CheckResult(
        name="contact_count",
        passed=True,
        detail=(
            f"{len(eligible)} pipeline-eligible contacts "
            f"(>= {MIN_CONTACTS_FOR_MEANINGFUL_RUN})"
        ),
    )


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_preflight(supabase: Any, client_id: str) -> PreflightReport:
    """Run every check. Env check is handled by the caller (needs to
    happen BEFORE we even try to build a supabase client)."""
    report = PreflightReport(client_id=client_id)
    report.checks.extend(check_schema(supabase))
    report.checks.append(check_client_exists(supabase, client_id))
    report.checks.extend(check_context_seeded(supabase, client_id))
    report.checks.append(check_knowledge_seeded(supabase))
    report.checks.append(check_autonomy_rules(supabase, client_id))
    report.checks.append(check_component_variants(supabase, client_id))
    report.checks.append(check_contact_count(supabase, client_id))
    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight checks for Plan 1 acceptance run. Read-only. "
            "Runs before scripts/run_daemon_once.py --dry-run."
        ),
    )
    parser.add_argument(
        "--client-id", required=True,
        help="Client ID whose seed data to validate.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit PreflightReport as JSON on stdout.",
    )
    return parser.parse_args(argv)


def _print_human(report: PreflightReport) -> None:
    if report.env_missing:
        print(f"client_id: {report.client_id}")
        print("env:")
        for name in REQUIRED_ENV:
            marker = "x" if name in report.env_missing else "ok"
            print(f"  [{marker}] {name}")
        print(
            f"\nBLOCKED: {len(report.env_missing)} required env var(s) missing. "
            "Set them in .env or the process environment and re-run."
        )
        return

    print(f"client_id: {report.client_id}")
    print(f"checks:    {len(report.checks)}")
    print()
    for c in report.checks:
        marker = "ok" if c.passed else "FAIL"
        print(f"  [{marker}] {c.name}: {c.detail}")
        if not c.passed and c.fix:
            print(f"         fix: {c.fix}")
    print()
    passed = sum(1 for c in report.checks if c.passed)
    failed = len(report.checks) - passed
    if report.all_passed:
        print(f"PASS - {passed}/{len(report.checks)} checks green.")
    else:
        print(f"FAIL - {failed}/{len(report.checks)} check(s) blocking.")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    env_missing = check_env()
    if env_missing:
        report = PreflightReport(
            client_id=args.client_id,
            env_missing=env_missing,
        )
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            _print_human(report)
        return 2

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    try:
        supabase = _build_client(url, key)
    except Exception as exc:
        print(f"ERROR: could not build Supabase client: {exc}", file=sys.stderr)
        return 2

    report = run_preflight(supabase, args.client_id)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_human(report)
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
