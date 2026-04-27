"""Smoke tests for scripts/run_optimizer_weekly.py."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts import run_optimizer_weekly
from systems.optimizer.weekly_review import WeeklyReviewReport


def _report(client_id: str = "c1") -> WeeklyReviewReport:
    return WeeklyReviewReport(
        client_id=client_id,
        window_days=7,
        generated_at=datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc),
        cost={
            "total_cost_cents": 6,
            "total_contacts_with_activity": 2,
            "cost_per_active_contact_cents": 3.0,
            "per_tier_cost_cents": {},
            "per_adapter_cost_cents": {},
            "top_contacts": [],
            "tier_spent": {}, "tier_budget": {},
        },
        reply_rate={"sends": 2, "replies": 1, "rate": 0.5},
        pending_recommendations=2,
        open_escalations=1,
        cooling_off_count=3,
        ready_to_re_enter_count=1,
    )


def test_slack_summary_renders_one_block():
    out = run_optimizer_weekly._slack_summary(_report())
    assert "Optimizer weekly review" in out
    assert "c1" in out
    assert "3.000c" in out
    assert "50.0%" in out
    assert "pending_recs=2" in out
    assert "open_escalations=1" in out


def test_report_path_uses_date_and_client():
    path = run_optimizer_weekly._report_path(_report(client_id="abc"))
    assert path.name == "2026-04-27-abc.md"
    assert "captures/optimizer" in str(path)


async def test_post_to_slack_no_op_when_url_unset(monkeypatch):
    """No SLACK_WEBHOOK_URL in env → silent no-op, no exception."""
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    await run_optimizer_weekly._post_to_slack("test message")  # no raise


async def test_post_to_slack_swallows_failure(monkeypatch):
    """Slack failure is logged to stderr but never propagates."""
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/x")

    # Stub the notifier to raise.
    from systems.beacon.reply import slack_notifier as sn

    class _BoomNotifier:
        def __init__(self, **kw):
            pass

        async def notify(self, msg):
            raise RuntimeError("slack down")

    monkeypatch.setattr(sn, "HttpxSlackNotifier", _BoomNotifier)
    # Should not raise.
    await run_optimizer_weekly._post_to_slack("test")
