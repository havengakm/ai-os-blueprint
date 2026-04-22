"""Load data/knowledge/**/*.md into the knowledge_base table with embeddings.

Expected file shape:
    ---
    source: "saraev"
    category: "framework"
    title: "AIDA for cold email"
    tags: ["cold_email", "saraev"]
    ---

    # AIDA
    Body content...

Behaviour:
    - Walks the --root directory (default: data/knowledge/)
    - Parses YAML frontmatter + body
    - Embeds the body via VoyageEmbedder
    - Upserts into knowledge_base, keyed by (client_id, source, title)

Usage:
    uv run python scripts/load_knowledge.py [--client-id=global]
                                             [--root=data/knowledge]
                                             [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Path-based import of the embedder: the project's `os/` package shadows
# Python's stdlib `os` when imported by name, so we load by file path.
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_embedder_cls() -> type:
    path = _REPO_ROOT / "os" / "foundation" / "embedder.py"
    spec = importlib.util.spec_from_file_location("aios_foundation_embedder", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.VoyageEmbedder


# Ensure scripts._lib imports resolve when the script is invoked from anywhere.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts._lib.markdown_loader import MarkdownDoc, parse_markdown, walk_markdown  # noqa: E402

logger = logging.getLogger(__name__)


VALID_CATEGORIES = {
    "framework", "template", "principle", "tactic",
    "case_study", "swipe_file", "research",
}


def _validate_knowledge_frontmatter(doc: MarkdownDoc) -> tuple[bool, str]:
    """Return (ok, error_msg). Required fields: source, category, title."""
    fm = doc.frontmatter
    for field in ("source", "category", "title"):
        if not fm.get(field):
            return False, f"missing required frontmatter field: {field}"
    if fm["category"] not in VALID_CATEGORIES:
        return False, (
            f"category '{fm['category']}' not in allowed set "
            f"({sorted(VALID_CATEGORIES)})"
        )
    if not doc.body:
        return False, "body is empty"
    return True, ""


async def load_knowledge(
    supabase: Any,
    embedder: Any,
    *,
    root: Path,
    client_id: str = "global",
    dry_run: bool = False,
) -> dict[str, int]:
    """Walk root, embed each doc, upsert into knowledge_base.

    Returns {'loaded': N, 'errors': E, 'skipped': S}.
    `skipped` covers files with missing required frontmatter OR empty body.
    """
    summary = {"loaded": 0, "errors": 0, "skipped": 0}

    paths = walk_markdown(root)
    if not paths:
        logger.info("no markdown files found under %s, nothing to load", root)
        return summary

    logger.info("found %d markdown files under %s", len(paths), root)

    for path in paths:
        try:
            doc = parse_markdown(path)
        except ValueError as e:
            logger.error("skip %s: %s", path, e)
            summary["errors"] += 1
            continue

        if doc is None:
            summary["errors"] += 1
            continue

        ok, err = _validate_knowledge_frontmatter(doc)
        if not ok:
            logger.warning("skip %s: %s", path, err)
            summary["skipped"] += 1
            continue

        fm = doc.frontmatter
        record = {
            "client_id": client_id,
            "source": fm["source"],
            "category": fm["category"],
            "title": fm["title"],
            "content": doc.body,
            "tags": fm.get("tags") or [],
            "active": True,
        }

        if dry_run:
            logger.info(
                "DRY-RUN would upsert knowledge_base: source=%s category=%s title=%s (%d chars)",
                record["source"], record["category"], record["title"], len(doc.body),
            )
            summary["loaded"] += 1
            continue

        try:
            embed_text = f"{fm['title']}: {doc.body[:2000]}"
            record["embedding"] = await embedder(embed_text)
        except Exception as e:
            logger.warning("embed failed for %s: %s", path, e)
            # Continue without an embedding — the row is still useful for
            # keyword fallback search.

        try:
            supabase.table("knowledge_base").upsert(
                record,
                on_conflict="client_id,source,title",
            ).execute()
            summary["loaded"] += 1
            logger.info(
                "UPSERTED knowledge_base: source=%s title=%s",
                fm["source"], fm["title"],
            )
        except Exception as e:
            logger.error("upsert failed for %s: %s", path, e)
            summary["errors"] += 1

    return summary


def _build_supabase(url: str, key: str) -> Any:
    from supabase import create_client
    return create_client(url, key)


def _build_embedder(api_key: str) -> Any:
    cls = _load_embedder_cls()
    return cls(api_key=api_key)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load data/knowledge/**/*.md into knowledge_base with embeddings."
    )
    parser.add_argument(
        "--client-id", default="global",
        help="Client ID to load under (default: 'global').",
    )
    parser.add_argument(
        "--root", default="data/knowledge",
        help="Directory to walk for markdown files (default: data/knowledge).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse + validate files but don't embed or write to the DB.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv or sys.argv[1:])
    root = Path(args.root)

    if args.dry_run:
        summary = asyncio.run(
            load_knowledge(
                supabase=None, embedder=None,
                root=root, client_id=args.client_id, dry_run=True,
            )
        )
    else:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        voyage_key = os.environ.get("VOYAGE_API_KEY")
        if not url or not key:
            print(
                "ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.",
                file=sys.stderr,
            )
            return 1
        if not voyage_key:
            print(
                "ERROR: VOYAGE_API_KEY must be set for embedding (or use --dry-run).",
                file=sys.stderr,
            )
            return 1

        supabase = _build_supabase(url, key)
        embedder = _build_embedder(voyage_key)
        summary = asyncio.run(
            load_knowledge(
                supabase=supabase, embedder=embedder,
                root=root, client_id=args.client_id, dry_run=False,
            )
        )

    prefix = "DRY-RUN " if args.dry_run else ""
    print(
        f"{prefix}knowledge load complete: {summary['loaded']} loaded, "
        f"{summary['skipped']} skipped, {summary['errors']} errors"
    )
    return 0 if summary["errors"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
