"""Snapshot a client's intake artefacts to ``archives/intake-{client_id}-{timestamp}/``.

Adapted from nateherkai/AIS-OS ``aios-intake.md`` pattern (audited 2026-05-04):
edit-source-and-re-run flows should snapshot prior outputs before regenerating
so re-onboarding never clobbers existing context.

Today this is an operator-callable tool: run it manually before any flow that
will rewrite per-client context or knowledge. When future regenerate-from-intake
scripts ship, they should call ``archive_client_intake()`` first.

Usage:

    uv run python scripts/archive_client_intake.py --client-id=clymb
    uv run python scripts/archive_client_intake.py --client-id=clymb --dry-run

Snapshots:

  - ``context/<client_id>/``
  - ``data/knowledge/personal/<client_id>/``
  - ``data/knowledge/company/<client_id>/``

Into:

  - ``archives/intake-<client_id>-<UTC ISO timestamp>/``

Folders that don't exist are skipped silently. The archive directory is created
even when nothing exists yet, so the run is observable.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


_REPO_ROOT = Path(__file__).parent.parent


@dataclass
class ArchiveResult:
    client_id: str
    archive_dir: Path
    archived_paths: list[Path] = field(default_factory=list)
    skipped_paths: list[Path] = field(default_factory=list)
    dry_run: bool = False


def _intake_sources(repo_root: Path, client_id: str) -> list[Path]:
    return [
        repo_root / "context" / client_id,
        repo_root / "data" / "knowledge" / "personal" / client_id,
        repo_root / "data" / "knowledge" / "company" / client_id,
    ]


def archive_client_intake(
    client_id: str,
    *,
    repo_root: Path | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
) -> ArchiveResult:
    """Snapshot a client's intake folders to ``archives/intake-{id}-{ts}/``.

    Tests inject ``repo_root`` + ``now``; production reads cwd + utcnow.
    Returns an ``ArchiveResult`` for the caller (or CLI) to report.
    """
    root = repo_root or _REPO_ROOT
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H-%M-%SZ")
    archive_dir = root / "archives" / f"intake-{client_id}-{stamp}"

    result = ArchiveResult(client_id=client_id, archive_dir=archive_dir, dry_run=dry_run)

    if not dry_run:
        archive_dir.mkdir(parents=True, exist_ok=False)

    for source in _intake_sources(root, client_id):
        if not source.exists():
            result.skipped_paths.append(source)
            continue
        rel = source.relative_to(root)
        target = archive_dir / rel
        if dry_run:
            result.archived_paths.append(source)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        result.archived_paths.append(source)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Snapshot a client's intake artefacts before regeneration",
    )
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = archive_client_intake(args.client_id, dry_run=args.dry_run)

    prefix = "DRY RUN. Would archive" if args.dry_run else "archived"
    if result.archived_paths:
        rels = [str(p.relative_to(_REPO_ROOT)) for p in result.archived_paths]
        print(f"{prefix} {len(rels)} folder(s) -> {result.archive_dir.relative_to(_REPO_ROOT)}")
        for r in rels:
            print(f"  - {r}")
    else:
        print(f"no intake folders found for client {args.client_id!r}; nothing archived")

    if result.skipped_paths:
        rels = [str(p.relative_to(_REPO_ROOT)) for p in result.skipped_paths]
        print(f"skipped (not present):")
        for r in rels:
            print(f"  - {r}")


if __name__ == "__main__":
    sys.exit(main())
