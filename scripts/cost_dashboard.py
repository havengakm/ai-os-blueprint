"""Operator cost + coverage dashboard CLI.

Plan 2 Phase 4 Tasks 2.4.4 (cost report) + 2.4.6 (coverage extension).

  uv run python scripts/cost_dashboard.py --client-id=<id> [--days=N]
  uv run python scripts/cost_dashboard.py --client-id=<id> --coverage

Cost report (default):
  - cost-per-active-contact this period vs $0.002 target
  - per-tier cost breakdown
  - top N most-expensive contacts
  - per-adapter spend rollup (which adapter is the cost driver?)
  - tier budget remaining (from client_config.tier_spent_cents)

Coverage report (--coverage flag):
  - per-tier per-field enrichment presence vs 90% target
  - flags tiers/fields under target
  - phone is gated to Tier A only (per feedback_enrichment_tiers)

Numbers reconcile against ``decision_log`` rollups +
``client_config.tier_spent_cents`` (cost) and the ``v_enrichment_coverage``
view (coverage).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Constants                                                                   #
# ---------------------------------------------------------------------------


# Per-contact cost target in cents. $0.002 = 0.2c.
COST_TARGET_CENTS_PER_CONTACT = 0.2

# Coverage target percentage per field per tier.
COVERAGE_TARGET_PCT = 90.0

# Phone is gated to Tier A only per feedback_enrichment_tiers + the
# 2026-04-27 scope expansion. Tiers B/C are NOT expected to reach 90%
# phone coverage and are rendered as "n/a" instead of "UNDER".
TIERS_REQUIRING_PHONE_COVERAGE: frozenset[str] = frozenset({"A"})


# ---------------------------------------------------------------------------
# Data fetchers                                                               #
# ---------------------------------------------------------------------------


async def fetch_cost_report(
    client: Any,
    client_id: str,
    days: int,
    *,
    now: datetime | None = None,
    top_n: int = 10,
) -> dict:
    """Aggregate cost data for one client over the past ``days``.

    Filters ``decision_log`` rows by ``client_id`` + ``created_at``
    window. Aggregates ``context.cost_cents`` totals + groups by
    ``decision_log.source`` (adapter) + joins to ``contacts.icp_tier``
    for the per-tier rollup.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).isoformat()

    # 1. Decision-log entries inside the window.
    log_resp = (
        client.table("decision_log")
        .select("decision_type, context, source, created_at")
        .eq("client_id", client_id)
        .gte("created_at", cutoff)
        .execute()
    )
    log_rows = log_resp.data or []

    # 2. Contacts (for tier mapping). Pull only what we need.
    contacts_resp = (
        client.table("contacts")
        .select("id, icp_tier")
        .eq("client_id", client_id)
        .execute()
    )
    contact_tier = {
        c["id"]: c.get("icp_tier") or "?"
        for c in (contacts_resp.data or [])
    }

    # 3. Aggregate.
    total_cost = 0
    per_adapter: dict[str, int] = {}
    per_contact: dict[str, int] = {}

    for row in log_rows:
        ctx = row.get("context") or {}
        # decision_log.context is JSONB. Most rows store an object here,
        # but a handful of legacy rows have a plain JSON string. Skip
        # those — they have no cost_cents to aggregate.
        if not isinstance(ctx, dict):
            continue
        cost = ctx.get("cost_cents")
        if not isinstance(cost, (int, float)):
            continue
        cost = int(cost)
        total_cost += cost

        adapter = row.get("source") or "unknown"
        per_adapter[adapter] = per_adapter.get(adapter, 0) + cost

        cid = ctx.get("contact_id")
        if cid:
            per_contact[cid] = per_contact.get(cid, 0) + cost

    # 4. Per-tier rollup (via the contact→tier map).
    per_tier: dict[str, int] = {}
    for cid, cost in per_contact.items():
        tier = contact_tier.get(cid, "?")
        per_tier[tier] = per_tier.get(tier, 0) + cost

    # 5. Top N expensive contacts.
    top_contacts = sorted(
        per_contact.items(), key=lambda kv: -kv[1]
    )[:top_n]

    # 6. Tier budget (from client_config).
    cfg_resp = (
        client.table("client_config")
        .select("tier_spent_cents, tier_budget_cents")
        .eq("client_id", client_id)
        .limit(1)
        .execute()
    )
    cfg_rows = cfg_resp.data or []
    cfg = cfg_rows[0] if cfg_rows else {}

    active_count = len(per_contact)
    cpac = (total_cost / active_count) if active_count else 0.0

    return {
        "total_cost_cents": total_cost,
        "total_contacts_with_activity": active_count,
        "cost_per_active_contact_cents": cpac,
        "per_tier_cost_cents": per_tier,
        "per_adapter_cost_cents": per_adapter,
        "top_contacts": top_contacts,
        "tier_spent": cfg.get("tier_spent_cents") or {},
        "tier_budget": cfg.get("tier_budget_cents") or {},
    }


async def fetch_coverage_report(client: Any, client_id: str) -> list[dict]:
    """Pull the enrichment coverage rollup via the
    ``get_enrichment_coverage`` RPC (migration 021)."""
    from systems.scout.supabase_backends.coverage import EnrichmentCoverageBackend

    backend = EnrichmentCoverageBackend(client)
    return await backend.get_enrichment_coverage(client_id)


# ---------------------------------------------------------------------------
# Formatters                                                                  #
# ---------------------------------------------------------------------------


def format_cost_report(report: dict, *, client_id: str, days: int) -> str:
    lines: list[str] = []
    lines.append(f"Cost Dashboard — client={client_id} window={days}d")
    lines.append("=" * 60)

    # Headline
    cpac = report["cost_per_active_contact_cents"]
    target = COST_TARGET_CENTS_PER_CONTACT
    flag = "OK" if cpac <= target else "OVER"
    lines.append(
        f"Cost-per-active-contact: {cpac:.3f}c [{flag}] "
        f"(target <= {target:.3f}c)"
    )
    lines.append(
        f"Total spend (window): {report['total_cost_cents']}c "
        f"across {report['total_contacts_with_activity']} contacts"
    )
    lines.append("")

    # Per-tier
    lines.append("Per-tier cost:")
    if not report["per_tier_cost_cents"]:
        lines.append("  (no spend in window)")
    else:
        for tier in sorted(report["per_tier_cost_cents"].keys()):
            cost = report["per_tier_cost_cents"][tier]
            lines.append(f"  Tier {tier}: {cost}c")
    lines.append("")

    # Per-adapter
    lines.append("Per-adapter cost (sources):")
    if not report["per_adapter_cost_cents"]:
        lines.append("  (no spend in window)")
    else:
        items = sorted(
            report["per_adapter_cost_cents"].items(),
            key=lambda kv: -kv[1],
        )
        for adapter, cost in items:
            lines.append(f"  {adapter}: {cost}c")
    lines.append("")

    # Top contacts
    lines.append("Top expensive contacts:")
    if not report["top_contacts"]:
        lines.append("  (no spend in window)")
    else:
        for cid, cost in report["top_contacts"]:
            lines.append(f"  {cid}: {cost}c")
    lines.append("")

    # Tier budget
    lines.append("Tier budget (lifetime):")
    spent = report["tier_spent"]
    budget = report["tier_budget"]
    if not spent and not budget:
        lines.append("  (no client_config row)")
    else:
        all_tiers = sorted(set(spent.keys()) | set(budget.keys()))
        for tier in all_tiers:
            s = spent.get(tier, 0)
            b = budget.get(tier, 0)
            pct = (100.0 * s / b) if b else 0.0
            lines.append(
                f"  Tier {tier}: tier_spent={s}c / budget={b}c ({pct:.1f}%)"
            )
    lines.append("")

    return "\n".join(lines)


def format_coverage_report(rows: list[dict], *, client_id: str) -> str:
    lines: list[str] = []
    lines.append(f"Coverage Dashboard — client={client_id}")
    lines.append("=" * 60)

    if not rows:
        lines.append("No coverage data — no contacts in tier A/B/C for this client.")
        return "\n".join(lines)

    target = COVERAGE_TARGET_PCT
    lines.append(f"Target: >= {target:.0f}% per field per tier (phone: Tier A only)")
    lines.append("")

    # Sort by (niche, tier).
    rows = sorted(rows, key=lambda r: (r.get("niche") or "", r.get("icp_tier") or ""))

    for row in rows:
        niche = row.get("niche") or "(unknown)"
        tier = row.get("icp_tier") or "?"
        total = row.get("total_contacts") or 0

        lines.append(f"Niche {niche} | Tier {tier} | total={total}")

        for field, key in (
            ("email_verified", "email_verified_pct"),
            ("linkedin", "linkedin_pct"),
            ("phone", "phone_pct"),
        ):
            pct = row.get(key)
            if pct is None:
                lines.append(f"  {field}: n/a")
                continue

            # Phone-on-non-Tier-A is "n/a" not "UNDER"
            if field == "phone" and tier not in TIERS_REQUIRING_PHONE_COVERAGE:
                lines.append(f"  {field}: {pct:.1f}% (n/a — Tier A only)")
                continue

            flag = "OK" if pct >= target else "UNDER"
            lines.append(f"  {field}: {pct:.1f}% [{flag}]")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI                                                                         #
# ---------------------------------------------------------------------------


def _get_supabase_client() -> Any:
    """Production Supabase client. Tests monkeypatch this to inject a
    FakeSupabaseClient."""
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit(
            "SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY required in env"
        )
    return create_client(url, key)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="AIOS cost + coverage dashboard CLI",
    )
    p.add_argument("--client-id", required=True, help="client to report on")
    p.add_argument(
        "--days", type=int, default=7,
        help="cost report window (default: 7)",
    )
    p.add_argument(
        "--top-n", type=int, default=10,
        help="top-N expensive contacts (default: 10)",
    )
    p.add_argument(
        "--coverage", action="store_true",
        help="show coverage report instead of cost report",
    )
    return p


def main() -> None:
    args = _build_arg_parser().parse_args()
    asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> None:
    client = _get_supabase_client()

    if args.coverage:
        rows = await fetch_coverage_report(client, args.client_id)
        print(format_coverage_report(rows, client_id=args.client_id))
    else:
        report = await fetch_cost_report(
            client, args.client_id, args.days, top_n=args.top_n,
        )
        print(format_cost_report(report, client_id=args.client_id, days=args.days))


if __name__ == "__main__":
    main()
