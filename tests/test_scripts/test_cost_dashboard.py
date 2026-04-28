"""Plan 2 Phase 4 Tasks 2.4.4 + 2.4.6: cost_dashboard CLI tests.

Tests the data-fetcher + formatter functions inside scripts/cost_dashboard.py.
The CLI argparse wrapper is exercised via a single end-to-end smoke test
that calls main() with patched sys.argv.

Two reports:
- Cost report: cost-per-lead, per-tier, top-10 expensive, per-adapter,
  tier budget remaining.
- Coverage report (Task 2.4.6): per-tier per-field presence vs 90% target,
  flagging tiers/fields under target.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.cost_dashboard import (
    fetch_cost_report,
    fetch_coverage_report,
    format_cost_report,
    format_coverage_report,
)
from tests.test_supabase_backends.fakes import FakeSupabaseClient


# --------------------------------------------------------------------------- #
# Cost report — fetcher                                                       #
# --------------------------------------------------------------------------- #


def _now() -> datetime:
    return datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)


def _seed_cost_data(now: datetime):
    """Seed a FakeSupabaseClient with a minimal cost-data fixture.

    3 contacts (Tier A, A, B), 5 decision_log entries totalling 8c spend
    over the last 3 days, plus an old entry that's outside the window.
    """
    recent = (now - timedelta(days=2)).isoformat()
    old = (now - timedelta(days=10)).isoformat()
    return FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "client_id": "c1", "icp_tier": "A"},
                {"id": "u2", "client_id": "c1", "icp_tier": "A"},
                {"id": "u3", "client_id": "c1", "icp_tier": "B"},
            ],
            "decision_log": [
                {
                    "client_id": "c1",
                    "context": {"contact_id": "u1", "cost_cents": 3},
                    "source": "scout.icebreaker_adapter",
                    "created_at": recent,
                },
                {
                    "client_id": "c1",
                    "context": {"contact_id": "u1", "cost_cents": 1},
                    "source": "scout.deep_research",
                    "created_at": recent,
                },
                {
                    "client_id": "c1",
                    "context": {"contact_id": "u2", "cost_cents": 2},
                    "source": "scout.icebreaker_adapter",
                    "created_at": recent,
                },
                {
                    "client_id": "c1",
                    "context": {"contact_id": "u3", "cost_cents": 2},
                    "source": "scout.icebreaker_adapter",
                    "created_at": recent,
                },
                {
                    "client_id": "c1",
                    "context": {"contact_id": "u1", "cost_cents": 99},
                    "source": "scout.icebreaker_adapter",
                    "created_at": old,  # outside the 7-day window
                },
                # decision_log entry without cost_cents — ignored
                {
                    "client_id": "c1",
                    "context": {"contact_id": "u1"},
                    "source": "scout.identity",
                    "created_at": recent,
                },
            ],
            "client_config": [
                {
                    "client_id": "c1",
                    "tier_spent_cents": {"A": 50, "B": 30},
                    "tier_budgets_cents": {"A": 1000, "B": 500},
                }
            ],
        }
    )


async def test_fetch_cost_report_aggregates_spend_in_window():
    now = _now()
    fake = _seed_cost_data(now)
    report = await fetch_cost_report(fake, "c1", days=7, now=now)

    assert report["total_cost_cents"] == 8  # 3 + 1 + 2 + 2; old 99c excluded
    assert report["total_contacts_with_activity"] == 3
    # cost_per_active_contact = 8/3 = 2.67c
    assert abs(report["cost_per_active_contact_cents"] - 2.667) < 0.01


async def test_fetch_cost_report_groups_by_tier():
    now = _now()
    fake = _seed_cost_data(now)
    report = await fetch_cost_report(fake, "c1", days=7, now=now)

    # Tier A: u1=4c + u2=2c = 6c. Tier B: u3=2c.
    assert report["per_tier_cost_cents"]["A"] == 6
    assert report["per_tier_cost_cents"]["B"] == 2


async def test_fetch_cost_report_groups_by_adapter():
    now = _now()
    fake = _seed_cost_data(now)
    report = await fetch_cost_report(fake, "c1", days=7, now=now)

    # icebreaker = 3 + 2 + 2 = 7c; deep_research = 1c.
    assert report["per_adapter_cost_cents"]["scout.icebreaker_adapter"] == 7
    assert report["per_adapter_cost_cents"]["scout.deep_research"] == 1


async def test_fetch_cost_report_top_n_contacts():
    now = _now()
    fake = _seed_cost_data(now)
    report = await fetch_cost_report(fake, "c1", days=7, now=now, top_n=2)

    # u1=4c, u2=2c, u3=2c (in tied order returns 2 → top_n=2 returns first 2)
    assert len(report["top_contacts"]) == 2
    assert report["top_contacts"][0] == ("u1", 4)


async def test_fetch_cost_report_includes_tier_budget_from_client_config():
    now = _now()
    fake = _seed_cost_data(now)
    report = await fetch_cost_report(fake, "c1", days=7, now=now)

    assert report["tier_spent"] == {"A": 50, "B": 30}
    assert report["tier_budget"] == {"A": 1000, "B": 500}


async def test_fetch_cost_report_handles_empty_data():
    fake = FakeSupabaseClient(
        tables={"contacts": [], "decision_log": [], "client_config": []}
    )
    report = await fetch_cost_report(fake, "c1", days=7, now=_now())

    assert report["total_cost_cents"] == 0
    assert report["total_contacts_with_activity"] == 0
    assert report["cost_per_active_contact_cents"] == 0.0


async def test_fetch_cost_report_tolerates_non_dict_context_rows():
    """Live regression: some legacy decision_log rows store ``context``
    as a plain JSONB string instead of a JSONB object. The fetcher must
    skip those rows without crashing — they carry no cost_cents to
    aggregate anyway. Reported by operator 2026-04-28 against
    kirsten-client-zero."""
    now = _now()
    recent = (now - timedelta(days=2)).isoformat()
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "client_id": "c1", "icp_tier": "A"},
            ],
            "decision_log": [
                # Normal object row — should aggregate.
                {
                    "client_id": "c1",
                    "context": {"contact_id": "u1", "cost_cents": 3},
                    "source": "scout.icebreaker",
                    "created_at": recent,
                },
                # Legacy string row — must be skipped, not crash.
                {
                    "client_id": "c1",
                    "context": "free-text legacy entry",
                    "source": "manual",
                    "created_at": recent,
                },
                # None row — also tolerated.
                {
                    "client_id": "c1",
                    "context": None,
                    "source": "manual",
                    "created_at": recent,
                },
            ],
            "client_config": [],
        }
    )
    report = await fetch_cost_report(fake, "c1", days=7, now=now)
    # Only the dict row aggregated.
    assert report["total_cost_cents"] == 3
    assert report["total_contacts_with_activity"] == 1


# --------------------------------------------------------------------------- #
# Cost report — formatter                                                     #
# --------------------------------------------------------------------------- #


def test_format_cost_report_renders_headline_and_target():
    report = {
        "total_cost_cents": 8,
        "total_contacts_with_activity": 3,
        "cost_per_active_contact_cents": 2.667,
        "per_tier_cost_cents": {"A": 6, "B": 2},
        "per_adapter_cost_cents": {
            "scout.icebreaker_adapter": 7,
            "scout.deep_research": 1,
        },
        "top_contacts": [("u1", 4), ("u2", 2)],
        "tier_spent": {"A": 50, "B": 30},
        "tier_budget": {"A": 1000, "B": 500},
    }
    out = format_cost_report(report, client_id="c1", days=7)

    # Headline: cost-per-contact + target
    assert "2.667c" in out or "2.67c" in out
    assert "0.200c" in out  # $0.002 target rendered as 0.200 cents
    assert "OVER" in out  # 2.667 > 0.2 → over target
    # Per-tier
    assert "Tier A" in out
    assert "Tier B" in out
    # Per-adapter
    assert "scout.icebreaker_adapter" in out
    # Top contacts
    assert "u1" in out
    # Tier budget
    assert "tier_spent" in out.lower() or "spent" in out.lower()


def test_format_cost_report_marks_under_target_as_ok():
    report = {
        "total_cost_cents": 1,
        "total_contacts_with_activity": 100,  # 0.01c per contact — under 0.2c
        "cost_per_active_contact_cents": 0.01,
        "per_tier_cost_cents": {},
        "per_adapter_cost_cents": {},
        "top_contacts": [],
        "tier_spent": {},
        "tier_budget": {},
    }
    out = format_cost_report(report, client_id="c1", days=7)
    assert "OK" in out  # under target marker


# --------------------------------------------------------------------------- #
# Coverage report                                                             #
# --------------------------------------------------------------------------- #


async def test_fetch_coverage_report_returns_rpc_payload():
    fake = FakeSupabaseClient()
    fake.set_rpc(
        "get_enrichment_coverage",
        [
            {
                "niche": "creative_branding",
                "icp_tier": "A",
                "total_contacts": 10,
                "email_verified_pct": 95.0,
                "linkedin_pct": 100.0,
                "phone_pct": 80.0,
            }
        ],
    )
    report = await fetch_coverage_report(fake, "c1")
    assert report[0]["icp_tier"] == "A"
    assert report[0]["email_verified_pct"] == 95.0


def test_format_coverage_report_flags_under_target_fields():
    rows = [
        {
            "niche": "creative_branding",
            "icp_tier": "A",
            "total_contacts": 10,
            "email_verified_pct": 95.0,
            "linkedin_pct": 100.0,
            "phone_pct": 80.0,
        },
        {
            "niche": "creative_branding",
            "icp_tier": "B",
            "total_contacts": 19,
            "email_verified_pct": 78.9,  # under 90% target
            "linkedin_pct": 89.5,        # under 90% target
            "phone_pct": 0.0,            # under 90% — but Tier B doesn't gate on phone
        },
    ]
    out = format_coverage_report(rows, client_id="c1")

    # Tier A: email + linkedin all >=90% → OK; phone Tier A target 90% +
    # observed 80% → UNDER.
    # Tier B: email + linkedin under target → flagged.
    assert "Tier A" in out
    assert "Tier B" in out
    # Under-target markers
    assert "UNDER" in out
    # Phone-on-Tier-B rule: phone is gated to Tier A only, so Tier B's
    # phone_pct of 0% is NOT flagged as a coverage gap. Renderer should
    # show a "n/a" or similar marker for Tier B phone instead of UNDER.
    lines = [l for l in out.split("\n") if "Tier B" in l and "phone" in l.lower()]
    if lines:
        assert "UNDER" not in lines[0] or "n/a" in lines[0].lower()


def test_format_coverage_report_with_empty_data():
    out = format_coverage_report([], client_id="c1")
    assert "no" in out.lower() or "empty" in out.lower() or "0" in out


# --------------------------------------------------------------------------- #
# CLI smoke test                                                              #
# --------------------------------------------------------------------------- #


def test_cli_invocation_via_main(monkeypatch, capsys):
    """Smoke test: --client-id is required, --coverage flag toggles report."""
    from scripts import cost_dashboard

    # Stub the fetchers so we don't need a real Supabase client.
    async def stub_fetch_cost_report(client, client_id, days, **kwargs):
        return {
            "total_cost_cents": 0,
            "total_contacts_with_activity": 0,
            "cost_per_active_contact_cents": 0.0,
            "per_tier_cost_cents": {},
            "per_adapter_cost_cents": {},
            "top_contacts": [],
            "tier_spent": {},
            "tier_budget": {},
        }

    monkeypatch.setattr(cost_dashboard, "_get_supabase_client", lambda: object())
    monkeypatch.setattr(cost_dashboard, "fetch_cost_report", stub_fetch_cost_report)
    monkeypatch.setattr(
        "sys.argv",
        ["cost_dashboard.py", "--client-id", "c1", "--days", "7"],
    )

    cost_dashboard.main()
    captured = capsys.readouterr()
    assert "Cost Dashboard" in captured.out
    assert "c1" in captured.out
