"""Run the nightly pipeline for ONE client, synchronously, then exit.

Local-testing counterpart to the long-running daemon. Bypasses the
scheduler: builds the registry + adapter factory, fetches the client's
config, then calls ``run_client_cycle`` directly.

Usage:
    uv run python scripts/run_daemon_once.py --client-id=<id> [--dry-run]
        [--stages=pull,score_v1,screen,identity,enrich,score_v2,compose]

Exit codes:
    0  success (every stage ok)
    1  at least one stage errored
    2  client_id has no client_config row (daemon would skip)
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import logging
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aios.daemon.adapter_factory import AdapterFactory  # noqa: E402
from aios.daemon.client_registry import fetch_client_config  # noqa: E402
from aios.daemon.client_worker import (  # noqa: E402
    STAGE_ORDER,
    ClientCycleResult,
    run_client_cycle,
)
from aios.daemon.main import _build_scout_for_client  # noqa: E402

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the AIOS nightly pipeline for one client, synchronously. "
            "Bypasses the scheduler — useful for local debugging."
        ),
    )
    parser.add_argument(
        "--client-id", required=True,
        help="Client ID whose nightly pipeline to run.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Forward dry_run=True to every stage (reads only, no writes).",
    )
    parser.add_argument(
        "--stages", default=None,
        help=(
            "Comma-separated subset of stages to run. Valid: "
            + ",".join(STAGE_ORDER)
            + ". Default: run every stage in order."
        ),
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit the ClientCycleResult as JSON on stdout.",
    )
    return parser.parse_args(argv)


def _parse_stages(raw: str | None) -> tuple[str, ...] | None:
    if raw is None:
        return None
    names = tuple(s.strip() for s in raw.split(",") if s.strip())
    invalid = [s for s in names if s not in STAGE_ORDER]
    if invalid:
        raise SystemExit(
            f"ERROR: unknown stage(s): {invalid}. Valid: {list(STAGE_ORDER)}"
        )
    return names


def _result_to_dict(result: ClientCycleResult) -> dict[str, Any]:
    """ClientCycleResult → plain dict for JSON output."""
    return dataclasses.asdict(result)


def _print_summary(result: ClientCycleResult) -> None:
    print(f"client_id: {result.client_id}")
    print(f"started:   {result.started_at}")
    print(f"completed: {result.completed_at}")
    print(f"stages:    {len(result.stages_run)}")
    for run in result.stages_run:
        marker = "ok" if run.ok else "FAIL"
        extra = ""
        if not run.ok:
            extra = f"  [{run.error_type}: {run.error_message}]"
        print(f"  - {run.stage:10s} {marker}{extra}")
    if result.errors:
        print(f"errors:    {len(result.errors)}")
    else:
        print("errors:    0")


async def _run(
    client_id: str, dry_run: bool, stages: tuple[str, ...] | None,
) -> ClientCycleResult | None:
    from api.deps import get_registry
    from config.settings import get_settings

    settings = get_settings()
    registry = get_registry()

    client_config = await fetch_client_config(registry, client_id)
    if client_config is None:
        return None

    factory = AdapterFactory(settings, registry)
    scout = _build_scout_for_client(registry, factory, client_config)
    return await run_client_cycle(
        scout, client_id,
        dry_run=dry_run, stages=stages,
        composer_backend=registry.composer_backend,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    stages = _parse_stages(args.stages)

    try:
        result = asyncio.run(_run(args.client_id, args.dry_run, stages))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 1

    if result is None:
        print(
            f"ERROR: no client_config row for client_id={args.client_id!r}",
            file=sys.stderr,
        )
        return 2

    if args.json:
        print(json.dumps(_result_to_dict(result), indent=2, default=str))
    else:
        _print_summary(result)

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
