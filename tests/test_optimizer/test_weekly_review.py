"""Plan 2 Phase 5 Task 2.5.1: WeeklyReview tests.

The weekly review job pulls operator-facing summaries:

  1. Cost analysis (reuses cost_dashboard.fetch_cost_report).
  2. Pending recommendations + count.
  3. Open escalations count.
  4. Cool-off queue size + ready-to-re-enter count.
  5. Reply rate (replies / sends in window).

v2 adds variant / adapter / send-time analysis once bandit + adapter
attribution data is queryable.

Renders to markdown for ``data/captures/optimizer/<date>.md`` archival
+ a Slack summary.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from systems.optimizer.weekly_review import (
    WeeklyReview,
    WeeklyReviewReport,
    render_markdown,
)
from tests.test_supabase_backends.fakes import FakeSupabaseClient


def _now() -> datetime:
    return datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)


def _seed(now: datetime) -> FakeSupabaseClient:
    """Seed a client with: 3 contacts (2 tier A + 1 tier B), 4
    decision_log entries totalling 6c, 2 sends, 1 reply, 2 open
    escalations, 1 cooling-off contact, 2 pending recommendations."""
    recent = (now - timedelta(days=2)).isoformat()
    return FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "client_id": "c1", "icp_tier": "A",
                 "status": "sent"},
                {"id": "u2", "client_id": "c1", "icp_tier": "A",
                 "status": "cooling_off",
                 "cool_off_until": (now - timedelta(days=1)).isoformat()},
                {"id": "u3", "client_id": "c1", "icp_tier": "B",
                 "status": "ready"},
            ],
            "decision_log": [
                {
                    "client_id": "c1",
                    "context": {"contact_id": "u1", "cost_cents": 3},
                    "source": "scout.icebreaker",
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
                    "context": {"contact_id": "u3", "cost_cents": 2},
                    "source": "scout.icebreaker",
                    "created_at": recent,
                },
            ],
            "outreach_send_log": [
                {"id": "s1", "client_id": "c1", "contact_id": "u1",
                 "status": "sent", "sent_at": recent},
                {"id": "s2", "client_id": "c1", "contact_id": "u3",
                 "status": "sent", "sent_at": recent},
            ],
            "outreach_reply": [
                {"id": "r1", "client_id": "c1", "contact_id": "u1",
                 "received_at": recent},
            ],
            "escalations": [
                {"id": "e1", "client_id": "c1", "status": "open",
                 "summary": "low confidence reply",
                 "created_at": recent},
                {"id": "e2", "client_id": "c1", "status": "open",
                 "summary": "auto_respond failed",
                 "created_at": recent},
                {"id": "e3", "client_id": "c1", "status": "resolved",
                 "summary": "old", "created_at": recent},
            ],
            "optimizer_recommendation": [
                {"id": "rec1", "client_id": "c1", "status": "pending",
                 "category": "autonomy_promotion",
                 "payload": {}, "reasoning": "x", "confidence": 0.8,
                 "created_at": recent},
                {"id": "rec2", "client_id": "c1", "status": "pending",
                 "category": "variant_retirement",
                 "payload": {}, "reasoning": "y", "confidence": 0.7,
                 "created_at": recent},
                {"id": "rec3", "client_id": "c1", "status": "approved",
                 "category": "autonomy_promotion",
                 "payload": {}, "reasoning": "z", "confidence": 0.9,
                 "created_at": recent},
            ],
            "client_config": [
                {"client_id": "c1",
                 "tier_spent_cents": {"A": 50}, "tier_budget_cents": {"A": 1000}}
            ],
        }
    )


# --------------------------------------------------------------------------- #
# WeeklyReview.run() — full report                                            #
# --------------------------------------------------------------------------- #


async def test_run_produces_full_report():
    now = _now()
    fake = _seed(now)
    review = WeeklyReview(client=fake)

    report = await review.run("c1", days=7, now=now)

    assert isinstance(report, WeeklyReviewReport)
    assert report.client_id == "c1"
    assert report.window_days == 7

    # Cost section: 6c total spend, 2 active contacts
    assert report.cost["total_cost_cents"] == 6
    assert report.cost["total_contacts_with_activity"] == 2

    # Reply rate section: 1 reply / 2 sends = 50%
    assert report.reply_rate["sends"] == 2
    assert report.reply_rate["replies"] == 1
    assert report.reply_rate["rate"] == 0.5

    # Pending recommendations: 2
    assert report.pending_recommendations == 2

    # Open escalations: 2
    assert report.open_escalations == 2

    # Cool-off: 1 cooling, 1 ready-to-re-enter (cool_off_until in past)
    assert report.cooling_off_count == 1
    assert report.ready_to_re_enter_count == 1


# --------------------------------------------------------------------------- #
# Reply rate edge cases                                                       #
# --------------------------------------------------------------------------- #


async def test_reply_rate_zero_when_no_sends():
    fake = FakeSupabaseClient(
        tables={
            "contacts": [], "decision_log": [],
            "outreach_send_log": [], "outreach_reply": [],
            "escalations": [], "optimizer_recommendation": [],
            "client_config": [],
        }
    )
    review = WeeklyReview(client=fake)
    report = await review.run("c1", days=7, now=_now())
    assert report.reply_rate["sends"] == 0
    assert report.reply_rate["replies"] == 0
    assert report.reply_rate["rate"] == 0.0


async def test_reply_rate_only_counts_window():
    """Sends + replies outside the window are excluded."""
    now = _now()
    recent = (now - timedelta(days=2)).isoformat()
    old = (now - timedelta(days=30)).isoformat()
    fake = FakeSupabaseClient(
        tables={
            "contacts": [],
            "decision_log": [],
            "outreach_send_log": [
                {"client_id": "c1", "contact_id": "u1",
                 "status": "sent", "sent_at": recent},
                {"client_id": "c1", "contact_id": "u2",
                 "status": "sent", "sent_at": old},
            ],
            "outreach_reply": [
                {"client_id": "c1", "contact_id": "u2",
                 "received_at": old},
            ],
            "escalations": [], "optimizer_recommendation": [],
            "client_config": [],
        }
    )
    review = WeeklyReview(client=fake)
    report = await review.run("c1", days=7, now=now)
    assert report.reply_rate["sends"] == 1  # only recent
    assert report.reply_rate["replies"] == 0  # old reply excluded


# --------------------------------------------------------------------------- #
# Cool-off counts                                                             #
# --------------------------------------------------------------------------- #


async def test_cool_off_distinguishes_cooling_vs_ready_to_re_enter():
    """cooling_off_count = total in cooling_off status.
    ready_to_re_enter_count = subset whose cool_off_until <= now."""
    now = _now()
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "client_id": "c1", "status": "cooling_off",
                 "cool_off_until": (now - timedelta(days=2)).isoformat()},
                {"id": "u2", "client_id": "c1", "status": "cooling_off",
                 "cool_off_until": (now + timedelta(days=10)).isoformat()},
                {"id": "u3", "client_id": "c1", "status": "cooling_off",
                 "cool_off_until": (now - timedelta(days=1)).isoformat()},
                {"id": "u4", "client_id": "c1", "status": "ready",
                 "cool_off_until": None},
            ],
            "decision_log": [], "outreach_send_log": [],
            "outreach_reply": [], "escalations": [],
            "optimizer_recommendation": [], "client_config": [],
        }
    )
    review = WeeklyReview(client=fake)
    report = await review.run("c1", days=7, now=now)
    assert report.cooling_off_count == 3
    assert report.ready_to_re_enter_count == 2  # u1 + u3


# --------------------------------------------------------------------------- #
# render_markdown                                                             #
# --------------------------------------------------------------------------- #


def test_render_markdown_includes_all_sections():
    report = WeeklyReviewReport(
        client_id="c1",
        window_days=7,
        generated_at=_now(),
        cost={
            "total_cost_cents": 6,
            "total_contacts_with_activity": 2,
            "cost_per_active_contact_cents": 3.0,
            "per_tier_cost_cents": {"A": 4, "B": 2},
            "per_adapter_cost_cents": {"scout.icebreaker": 5},
            "top_contacts": [("u1", 4)],
            "tier_spent": {}, "tier_budget": {},
        },
        reply_rate={"sends": 2, "replies": 1, "rate": 0.5},
        pending_recommendations=2,
        open_escalations=2,
        cooling_off_count=1,
        ready_to_re_enter_count=1,
    )
    md = render_markdown(report)

    assert "# Optimizer Weekly Review" in md
    assert "client=c1" in md or "c1" in md
    assert "## Cost" in md
    assert "## Reply Rate" in md
    assert "## Pending Recommendations" in md
    assert "## Open Escalations" in md
    assert "## Cool-off Queue" in md
    # Numbers should appear in output
    assert "6c" in md or "6 cents" in md or "6 " in md
    assert "50.0%" in md or "0.5" in md


def test_render_markdown_with_zero_data():
    """When everything is empty, render still produces a clean report."""
    report = WeeklyReviewReport(
        client_id="c-empty",
        window_days=7,
        generated_at=_now(),
        cost={
            "total_cost_cents": 0,
            "total_contacts_with_activity": 0,
            "cost_per_active_contact_cents": 0.0,
            "per_tier_cost_cents": {},
            "per_adapter_cost_cents": {},
            "top_contacts": [],
            "tier_spent": {}, "tier_budget": {},
        },
        reply_rate={"sends": 0, "replies": 0, "rate": 0.0},
        pending_recommendations=0,
        open_escalations=0,
        cooling_off_count=0,
        ready_to_re_enter_count=0,
    )
    md = render_markdown(report)
    assert "c-empty" in md
    assert "## Cost" in md
