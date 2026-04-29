"""Cool-off + round-based re-entry cron CLI.

Plan 2 Phase 3 Task 2.3.4 runtime wrapper. Per
``scripts/provision_new_client.py`` operator runbook step 7:

  uv run python scripts/run_cool_off_cycle.py --client-id=<id>

Runs one ``CoolOffRuntime.run_cycle`` invocation: re-enters contacts
whose cool_off_until has passed (next round, or marked dead at
max_rounds), then enters cool-off for any newly idle contacts.

Designed for daily cron. Idempotent — running twice in the same minute
is harmless (the second pass finds nothing to do).

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


def _get_runtime() -> Any:
    """Production runtime via api.deps factory. Tests monkeypatch this."""
    from api.deps import get_cool_off_runtime

    return get_cool_off_runtime()


async def _run(args: argparse.Namespace) -> int:
    runtime = _get_runtime()
    now = datetime.now(timezone.utc)
    result = await runtime.run_cycle(args.client_id, now=now)

    print(
        f"cool_off cycle client={args.client_id} "
        f"cooled_off={result.cooled_off_count} "
        f"re_entered={result.re_entered_count} "
        f"marked_dead={result.marked_dead_count}"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AIOS cool-off + re-entry cycle CLI",
    )
    parser.add_argument("--client-id", required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
