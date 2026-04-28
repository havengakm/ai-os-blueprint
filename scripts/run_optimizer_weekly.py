"""Optimizer weekly review CLI.

Plan 2 Phase 5 Task 2.5.1.

  uv run python scripts/run_optimizer_weekly.py --client-id=<id> [--days=7]

Writes the markdown report to ``data/captures/optimizer/<date>-<client>.md``
and (if ``SLACK_WEBHOOK_URL`` is set in env) posts a one-liner summary
to Slack via the same notifier the escalation queue uses.

Idempotent — re-running on the same date overwrites the markdown file.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from systems.optimizer.weekly_review import (
    WeeklyReview,
    WeeklyReviewReport,
    render_markdown,
)


REPORTS_DIR = Path("data/captures/optimizer")


def _get_supabase_client() -> Any:
    """Production Supabase client. Tests monkeypatch this to inject a
    fake."""
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit(
            "SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY required in env"
        )
    return create_client(url, key)


def _slack_summary(report: WeeklyReviewReport) -> str:
    cpac = report.cost.get("cost_per_active_contact_cents", 0.0)
    rate = report.reply_rate.get("rate", 0.0) * 100
    return (
        f"Optimizer weekly review — client={report.client_id} "
        f"window={report.window_days}d\n"
        f"cost-per-active-contact: {cpac:.3f}c | reply-rate: {rate:.1f}%\n"
        f"pending_recs={report.pending_recommendations} | "
        f"open_escalations={report.open_escalations} | "
        f"ready_to_re_enter={report.ready_to_re_enter_count}"
    )


def _report_path(report: WeeklyReviewReport) -> Path:
    date = report.generated_at.date().isoformat()
    return REPORTS_DIR / f"{date}-{report.client_id}.md"


async def _post_to_slack(message: str) -> None:
    """Best-effort Slack notify. No-op when SLACK_WEBHOOK_URL unset."""
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return
    try:
        from systems.beacon.reply.slack_notifier import HttpxSlackNotifier

        notifier = HttpxSlackNotifier(webhook_url=url)
        await notifier.notify(message)
    except Exception as exc:
        # Slack failure is observable in stdout but never blocks the job.
        print(f"Slack notify failed: {exc}", file=sys.stderr)


async def _run(args: argparse.Namespace) -> int:
    client = _get_supabase_client()
    review = WeeklyReview(client=client)

    now = datetime.now(timezone.utc)
    report = await review.run(
        args.client_id, days=args.days, now=now,
    )

    markdown = render_markdown(report)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _report_path(report)
    path.write_text(markdown)
    print(f"wrote {path}")

    summary = _slack_summary(report)
    print(summary)
    await _post_to_slack(summary)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AIOS Optimizer weekly review CLI",
    )
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
