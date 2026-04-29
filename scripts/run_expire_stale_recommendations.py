"""Optimizer recommendation expire-stale cron CLI.

Plan 2 Phase 5 Task 2.5.2 runtime wrapper. Per
``scripts/provision_new_client.py`` operator runbook step 7:

  uv run python scripts/run_expire_stale_recommendations.py [--threshold-days=N]

Transitions any ``optimizer_recommendations`` row in status='pending'
older than ``threshold_days`` (default 7, per
``RecommendationEngine.DEFAULT_AUTO_EXPIRE_DAYS``) to status='expired'.

Engine-level operation, not client-scoped — ``list_pending_older_than``
queries by cutoff across all clients. Designed for daily cron.

Stdout is a single structured line per run for cron-log friendliness.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _get_engine() -> Any:
    """Production engine via api.deps factory. Tests monkeypatch this."""
    from api.deps import get_optimizer_recommendation_engine

    return get_optimizer_recommendation_engine()


async def _run(args: argparse.Namespace) -> int:
    engine = _get_engine()
    now = datetime.now(timezone.utc)
    expired_count = await engine.expire_stale(
        now=now, threshold_days=args.threshold_days,
    )

    threshold_label = (
        args.threshold_days
        if args.threshold_days is not None
        else "engine_default"
    )
    print(
        f"optimizer_recommendations expired={expired_count} "
        f"threshold_days={threshold_label}"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AIOS optimizer-recommendation expire-stale CLI",
    )
    parser.add_argument(
        "--threshold-days",
        type=int,
        default=None,
        help="Override the engine's default auto-expire threshold (7d).",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
