"""Configure Trigify monitors for an AIOS client (Task 1.5.9c CLI).

Wraps ``TrigifyMonitorCreator``. Reads the operator-authored YAML at
``context/{client_id}/sourcing/trigify_monitors.yaml``, performs a dry-run
preview, prompts for confirmation, then provisions the monitors via the
Trigify API and persists returned search_ids to
``client_config.trigify_search_ids``.

Usage:
    uv run python scripts/configure_trigify_monitors.py --client-id=<id>
        [--yaml-path=PATH] [--dry-run] [--no-confirm]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aios.scout.sources.trigify_monitors import (  # noqa: E402
    ProvisioningResult,
    TrigifyMonitorCreator,
)
from aios.scout.supabase_backends.trigify import (  # noqa: E402
    SupabaseTrigifyMonitorStorage,
)

logger = logging.getLogger(__name__)

_SAMPLE_NAMES_SHOWN = 5


def _build_supabase(url: str, key: str) -> Any:
    """Construct a supabase.Client. Factored out for test monkeypatching."""
    from supabase import create_client
    return create_client(url, key)


def _default_yaml_path(client_id: str) -> Path:
    return _REPO_ROOT / "context" / client_id / "sourcing" / "trigify_monitors.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load + validate the operator YAML. Raises ValueError with an
    actionable message on any problem; callers print + exit 1."""
    if not path.exists():
        raise ValueError(
            f"YAML not found: {path}. See "
            "data/reference/sops/trigify-monitor-authoring.md for the schema."
        )
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parse error in {path}: {e}") from e
    if raw is None:
        raise ValueError(f"YAML is empty: {path}")
    if not isinstance(raw, dict):
        raise ValueError(
            f"YAML root must be a mapping, got {type(raw).__name__}: {path}"
        )
    return raw


def _print_dry_run_preview(result: ProvisioningResult) -> None:
    """Operator-facing dry-run output. Shows count + sample names by type."""
    planned = result.dry_run_planned
    print(f"\nDry-run: would provision {len(planned)} Trigify monitors "
          f"for client_id={result.client_id}")

    by_type: dict[str, list[str]] = {}
    for spec in planned:
        by_type.setdefault(spec.monitor_type, []).append(spec.name)
    for mtype, names in sorted(by_type.items()):
        print(f"  {mtype}: {len(names)}")
        for name in names[:_SAMPLE_NAMES_SHOWN]:
            print(f"    - {name}")
        if len(names) > _SAMPLE_NAMES_SHOWN:
            print(f"    ... +{len(names) - _SAMPLE_NAMES_SHOWN} more")


def _print_live_summary(result: ProvisioningResult) -> None:
    print(
        f"\nProvisioned monitors for client_id={result.client_id}: "
        f"{len(result.created)} created, "
        f"{len(result.skipped_existing)} skipped (idempotent), "
        f"{len(result.failed)} failed"
    )
    if result.failed:
        print("\nFailures:", file=sys.stderr)
        for name, err in result.failed:
            print(f"  - {name}: {err}", file=sys.stderr)


def _confirm(num_to_create: int, client_id: str) -> bool:
    """Interactive confirm prompt. Returns True iff operator typed 'y'."""
    try:
        answer = input(
            f"\nProceed? Create {num_to_create} monitors for client_id={client_id}? [y/N]: "
        )
    except EOFError:
        return False
    return answer.strip().lower() == "y"


async def _run(
    *,
    client_id: str,
    yaml_path: Path,
    dry_run: bool,
    no_confirm: bool,
    creator: TrigifyMonitorCreator,
) -> int:
    """Core async flow. Returns the exit code (0 success, 1 failure)."""
    yaml_spec = _load_yaml(yaml_path)

    # Always do the dry-run first — either as the final output (--dry-run)
    # or as the preview shown to the operator before confirming a live run.
    preview = await creator.provision_from_yaml(
        client_id, yaml_spec, dry_run=True,
    )
    _print_dry_run_preview(preview)

    if dry_run:
        return 0

    planned_count = len(preview.dry_run_planned)
    if planned_count == 0:
        print("\nNothing to provision (YAML yielded zero monitor specs). Exiting.")
        return 0

    if not no_confirm and not _confirm(planned_count, client_id):
        print("\nAborted by operator.")
        return 0

    result = await creator.provision_from_yaml(
        client_id, yaml_spec, dry_run=False,
    )
    _print_live_summary(result)

    # Non-zero when any monitor failed so automation catches partial failures.
    return 0 if not result.failed else 1


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Provision Trigify social-listening monitors for an AIOS client. "
            "Reads per-client YAML, dry-runs the Trigify API, prompts for "
            "confirmation, then provisions and persists search IDs."
        ),
    )
    parser.add_argument(
        "--client-id", required=True,
        help="Client ID (matches context/{client-id}/ directory name).",
    )
    parser.add_argument(
        "--yaml-path", default=None,
        help="Path to trigify_monitors.yaml. Default: "
             "context/{client-id}/sourcing/trigify_monitors.yaml.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview only — no Trigify calls, no DB writes.",
    )
    parser.add_argument(
        "--no-confirm", action="store_true",
        help="Skip the interactive confirm prompt (use for automation).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv or sys.argv[1:])

    yaml_path = Path(args.yaml_path) if args.yaml_path else _default_yaml_path(
        args.client_id,
    )

    # Load YAML up-front so a bad path fails fast with a clean message,
    # BEFORE we touch Supabase or Trigify.
    try:
        _load_yaml(yaml_path)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Env-var checks: the live path needs Supabase + Trigify; dry-run still
    # needs neither of them strictly speaking, but we require Trigify key
    # only when going live.
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print(
            "ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set "
            "in the environment (or loaded from .env before running).",
            file=sys.stderr,
        )
        return 1

    if not args.dry_run and not os.environ.get("TRIGIFY_API_KEY"):
        print(
            "ERROR: TRIGIFY_API_KEY must be set for a live provisioning run. "
            "Add it to .env or pass --dry-run for a preview.",
            file=sys.stderr,
        )
        return 1

    try:
        supabase = _build_supabase(url, key)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: failed to construct Supabase client: {e}", file=sys.stderr)
        return 1

    storage = SupabaseTrigifyMonitorStorage(supabase)
    creator = TrigifyMonitorCreator(storage=storage)

    try:
        return asyncio.run(_run(
            client_id=args.client_id,
            yaml_path=yaml_path,
            dry_run=args.dry_run,
            no_confirm=args.no_confirm,
            creator=creator,
        ))
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except EnvironmentError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
