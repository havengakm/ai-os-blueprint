"""Load component variant YAMLs into component_variants table (Task 16b Step 3).

Wraps ``systems/scout/outreach/component_store.py::ComponentStore.sync(client_id)``
with the Supabase-backed ``ComponentStoreBackend`` from Task 16b Step 1. Dry-run
preview + operator confirm flow; exits non-zero on any validation error so
automation catches malformed YAMLs.

Preserves the item-62 invariant at the backend layer: learned ``win_rate`` +
``sample_size`` are never clobbered by this loader. Only ``variant_content`` /
``status`` / ``metadata`` / ``ab_epsilon`` can change during sync.

Usage:
    uv run python scripts/load_components.py --client-id=<id>
        [--root=<path>] [--dry-run] [--no-confirm]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from systems.scout.outreach.component_store import (  # noqa: E402
    ComponentStore,
    ComponentVariant,
    SyncSummary,
    VariantKeyTuple,
)
from systems.scout.supabase_backends.component_store import (  # noqa: E402
    SupabaseComponentStoreBackend,
)

logger = logging.getLogger(__name__)

_DEFAULT_ROOT = _REPO_ROOT / "data" / "reference" / "sequences"


# --------------------------------------------------------------------------- #
# Supabase client shim — factored out for test monkeypatching.                 #
# --------------------------------------------------------------------------- #

def _build_supabase(url: str, key: str) -> Any:
    """Construct a supabase.Client. Matches the sibling-script pattern
    (seed_autonomy_rules, configure_trigify_monitors) so tests can
    ``monkeypatch.setattr(mod, "_build_supabase", ...)``."""
    from supabase import create_client
    return create_client(url, key)


# --------------------------------------------------------------------------- #
# DryRunComponentStoreBackend                                                  #
# --------------------------------------------------------------------------- #

class DryRunComponentStoreBackend:
    """Implements ``ComponentStoreBackend`` Protocol but records operations
    without writing.

    Used when ``--dry-run`` is set. Forwards ``fetch_existing`` to the real
    backend (read-only) but captures ``insert_variants`` / ``update_variants``
    calls locally so the planned writes can be reported to the operator
    without touching the DB.
    """

    def __init__(self, real_backend: Any) -> None:
        self._real = real_backend
        self.planned_inserts: list[tuple[str, list[ComponentVariant]]] = []
        self.planned_updates: list[
            tuple[str, list[tuple[str, ComponentVariant]]]
        ] = []

    async def fetch_existing(
        self,
        client_id: str,
        keys: list[VariantKeyTuple],
    ) -> dict[VariantKeyTuple, dict[str, Any]]:
        return await self._real.fetch_existing(client_id, keys)

    async def insert_variants(
        self,
        client_id: str,
        variants: list[ComponentVariant],
    ) -> None:
        self.planned_inserts.append((client_id, list(variants)))

    async def update_variants(
        self,
        client_id: str,
        updates: list[tuple[str, ComponentVariant]],
    ) -> None:
        self.planned_updates.append((client_id, list(updates)))


# --------------------------------------------------------------------------- #
# Output formatting                                                            #
# --------------------------------------------------------------------------- #

def _print_summary(summary: SyncSummary, *, dry_run: bool, client_id: str) -> None:
    """Operator-facing summary of a sync run."""
    prefix = "DRY-RUN " if dry_run else ""
    print(
        f"\n{prefix}component sync for client_id={client_id}: "
        f"{summary.loaded} loaded, "
        f"{summary.inserted} inserted, "
        f"{summary.updated} updated, "
        f"{summary.unchanged} unchanged, "
        f"{summary.skipped} skipped"
    )
    if summary.errors:
        print(f"\n{len(summary.errors)} error(s):", file=sys.stderr)
        for err in summary.errors:
            print(f"  - {err}", file=sys.stderr)


def _confirm(inserts: int, updates: int, client_id: str) -> bool:
    """Interactive confirm prompt. Returns True iff operator typed 'y'."""
    try:
        answer = input(
            f"\nProceed? {inserts} inserts + {updates} updates for "
            f"client_id={client_id}? [y/N]: "
        )
    except EOFError:
        return False
    return answer.strip().lower() == "y"


# --------------------------------------------------------------------------- #
# Core flow                                                                    #
# --------------------------------------------------------------------------- #

async def _run(
    *,
    client_id: str,
    root: Path,
    dry_run: bool,
    no_confirm: bool,
    real_backend: Any,
) -> int:
    """Run the sync flow. Returns exit code (0 success, 1 on errors)."""
    if not root.exists():
        # Not an error — an operator may legitimately run setup before
        # authoring any sequences. Match ComponentStore.sync's own
        # tolerance for a missing root.
        print(
            f"WARNING: sequences root not found: {root}. Nothing to load.",
            file=sys.stderr,
        )
        return 0

    # Dry-run pass first — either as the final output (--dry-run) or as
    # the preview shown to the operator before confirming a live run.
    dry_backend = DryRunComponentStoreBackend(real_backend)
    dry_store = ComponentStore(backend=dry_backend, sequences_root=root)
    dry_summary = await dry_store.sync(client_id)
    _print_summary(dry_summary, dry_run=True, client_id=client_id)

    if dry_summary.errors:
        # Validation errors block BOTH dry-run and live paths: fail fast so
        # operators can't inadvertently push a partial sync over a malformed
        # YAML batch.
        return 1

    if dry_run:
        return 0

    planned_writes = dry_summary.inserted + dry_summary.updated
    if planned_writes == 0:
        print("\nNothing to write (all variants unchanged). Exiting.")
        return 0

    if not no_confirm and not _confirm(
        dry_summary.inserted, dry_summary.updated, client_id,
    ):
        print("\nAborted by operator.")
        return 0

    live_store = ComponentStore(backend=real_backend, sequences_root=root)
    live_summary = await live_store.sync(client_id)
    _print_summary(live_summary, dry_run=False, client_id=client_id)

    return 0 if not live_summary.errors else 1


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Load component variant YAMLs from data/reference/sequences/ into "
            "the component_variants table. Dry-run preview + confirm flow. "
            "Preserves learned win_rate/sample_size (item-62 gate)."
        ),
    )
    parser.add_argument(
        "--client-id", required=True,
        help="Client ID to sync variants under.",
    )
    parser.add_argument(
        "--root", default=None,
        help="Sequences directory root. Default: data/reference/sequences/",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview only — no DB writes.",
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

    root = Path(args.root) if args.root else _DEFAULT_ROOT

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print(
            "ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set "
            "in the environment (or loaded from .env before running).",
            file=sys.stderr,
        )
        return 1

    try:
        supabase = _build_supabase(url, key)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: failed to construct Supabase client: {e}", file=sys.stderr)
        return 1

    real_backend = SupabaseComponentStoreBackend(supabase)

    try:
        return asyncio.run(_run(
            client_id=args.client_id,
            root=root,
            dry_run=args.dry_run,
            no_confirm=args.no_confirm,
            real_backend=real_backend,
        ))
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
