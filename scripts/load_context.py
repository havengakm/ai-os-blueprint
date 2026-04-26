"""Load context/{client}/**/*.md into business_context with [[backlink]] resolution.

Two-pass algorithm (per Task 12.5 + Amendment 2 from Max webinar 2026-04-21 pt2):

  Pass 1 — Walk markdown, parse frontmatter + body, strip [[...]] brackets from
           the body (entity name preserved as plain text), compute embedding,
           insert/upsert each row into business_context. Record raw
           [[entity-name]] tokens per source file for Pass 2.

  Pass 2 — For each file's backlink tokens: look up target in business_context
           (by title, same client_id) OR client_facts (by key, same client_id).
           Append resolved UUIDs to the row's related_context_ids /
           related_fact_ids arrays. Unresolved backlinks -> written to
           data/reports/load_context_unresolved_links-{timestamp}.log (one entry
           per unresolved link). Does NOT create stub entries.

Usage:
    uv run python scripts/load_context.py --client-id=<id>
                                          [--root=context/<client>]
                                          [--dry-run]
"""
from __future__ import annotations

# Auto-load .env so the script works from a fresh shell without `source .env`
# or direnv. Plan 1.5 Task 1.5.2 (follow-ups-plan1.md item 2).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import argparse
import asyncio
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aios.foundation.embedder import VoyageEmbedder  # noqa: E402
from scripts._lib.markdown_loader import MarkdownDoc, parse_markdown, walk_markdown  # noqa: E402

logger = logging.getLogger(__name__)


# Match [[Entity Name]] and [[Entity Name|display text]] (Obsidian alias syntax).
# Group 1 = the target; we ignore the alias.
_BACKLINK_RE = re.compile(r"\[\[([^\]\[|]+?)(?:\|[^\]\[]*)?\]\]")


@dataclass
class _LoadedRow:
    """Pass-1 output: a row we inserted/upserted, keyed by title, with the
    [[tokens]] we observed so Pass 2 can resolve them."""
    title: str
    source_path: Path
    backlink_tokens: list[str] = field(default_factory=list)
    # Populated after Pass 1 returns from the DB with the row's UUID.
    row_id: str | None = None


@dataclass
class _UnresolvedLink:
    source_file: Path
    token: str
    reason: str


def _extract_backlinks(text: str) -> list[str]:
    """Return deduped-in-order list of [[target]] strings from text."""
    seen: set[str] = set()
    ordered: list[str] = []
    for m in _BACKLINK_RE.finditer(text):
        target = m.group(1).strip()
        if target and target not in seen:
            seen.add(target)
            ordered.append(target)
    return ordered


def _strip_brackets(text: str) -> str:
    """Remove [[...]] brackets, keeping the target name as plain text.
    `[[Nick Saraev]]` -> `Nick Saraev`
    `[[Nick Saraev|Nick]]` -> `Nick` (alias takes precedence per Obsidian)."""
    def _replace(m: re.Match[str]) -> str:
        raw = m.group(0)[2:-2]  # strip [[ and ]]
        if "|" in raw:
            _, alias = raw.split("|", 1)
            return alias.strip()
        return raw.strip()
    return _BACKLINK_RE.sub(_replace, text)


def _validate_context_frontmatter(doc: MarkdownDoc) -> tuple[bool, str]:
    """Required: title. section_metadata is optional (defaults to {})."""
    if not doc.frontmatter.get("title"):
        return False, "missing required frontmatter field: title"
    if not doc.body:
        return False, "body is empty"
    sm = doc.frontmatter.get("section_metadata", {})
    if sm is not None and not isinstance(sm, dict):
        return False, "section_metadata must be a mapping"
    return True, ""


async def _pass_1_upsert(
    supabase: Any,
    embedder: Any,
    *,
    paths: list[Path],
    client_id: str,
    dry_run: bool,
) -> tuple[list[_LoadedRow], int, int]:
    """Pass 1: parse + embed + upsert each row. Strips [[...]] brackets from
    the stored body. Records raw tokens for Pass 2.

    Returns (loaded_rows, skipped_count, error_count).
    """
    loaded: list[_LoadedRow] = []
    skipped = 0
    errors = 0

    for path in paths:
        try:
            doc = parse_markdown(path)
        except ValueError as e:
            logger.error("skip %s: %s", path, e)
            errors += 1
            continue

        if doc is None:
            errors += 1
            continue

        ok, err = _validate_context_frontmatter(doc)
        if not ok:
            logger.warning("skip %s: %s", path, err)
            skipped += 1
            continue

        fm = doc.frontmatter
        tokens = _extract_backlinks(doc.body)
        stripped_body = _strip_brackets(doc.body)

        record: dict[str, Any] = {
            "client_id": client_id,
            "title": fm["title"],
            "body": stripped_body,
            "section_metadata": fm.get("section_metadata") or {},
            "source_path": str(path),
        }

        row = _LoadedRow(title=fm["title"], source_path=path, backlink_tokens=tokens)

        if dry_run:
            logger.info(
                "DRY-RUN pass1 would upsert business_context: title=%s backlinks=%d",
                fm["title"], len(tokens),
            )
            loaded.append(row)
            continue

        try:
            record["embedding"] = await embedder(f"{fm['title']}: {stripped_body[:2000]}")
        except Exception as e:
            logger.warning("embed failed for %s: %s", path, e)

        try:
            resp = supabase.table("business_context").upsert(
                record,
                on_conflict="client_id,title",
            ).execute()
            row_data = (resp.data or [{}])[0]
            row.row_id = row_data.get("id")
            logger.info(
                "UPSERTED business_context: title=%s id=%s backlinks=%d",
                fm["title"], row.row_id, len(tokens),
            )
            loaded.append(row)
        except Exception as e:
            logger.error("upsert failed for %s: %s", path, e)
            errors += 1

    return loaded, skipped, errors


def _build_lookup_context(supabase: Any, client_id: str) -> dict[str, str]:
    """title -> id for every business_context row belonging to client_id."""
    try:
        resp = (
            supabase.table("business_context")
            .select("id, title")
            .eq("client_id", client_id)
            .execute()
        )
        return {r["title"]: r["id"] for r in (resp.data or []) if r.get("id") and r.get("title")}
    except Exception as e:
        logger.warning("failed to build business_context lookup: %s", e)
        return {}


def _build_lookup_facts(supabase: Any, client_id: str) -> dict[str, str]:
    """key -> id for every client_facts row belonging to client_id."""
    try:
        resp = (
            supabase.table("client_facts")
            .select("id, key")
            .eq("client_id", client_id)
            .execute()
        )
        return {r["key"]: r["id"] for r in (resp.data or []) if r.get("id") and r.get("key")}
    except Exception as e:
        logger.warning("failed to build client_facts lookup: %s", e)
        return {}


async def _pass_2_resolve(
    supabase: Any,
    *,
    loaded: list[_LoadedRow],
    client_id: str,
    dry_run: bool,
) -> tuple[int, list[_UnresolvedLink]]:
    """Pass 2: resolve each row's backlink tokens to UUIDs and update the row.
    Returns (resolved_count, unresolved_list)."""
    resolved = 0
    unresolved: list[_UnresolvedLink] = []

    # For dry-run we don't have UUIDs (nothing was written), so the only
    # meaningful check is token-level resolution against the *dry-run* row
    # titles + the (possibly empty) facts table.
    context_lookup: dict[str, str]
    facts_lookup: dict[str, str]
    if dry_run:
        context_lookup = {r.title: f"dry-run-id-for-{r.title}" for r in loaded}
        facts_lookup = {}
    else:
        context_lookup = _build_lookup_context(supabase, client_id)
        facts_lookup = _build_lookup_facts(supabase, client_id)

    for row in loaded:
        if not row.backlink_tokens:
            continue

        related_ctx: list[str] = []
        related_facts: list[str] = []

        for token in row.backlink_tokens:
            ctx_id = context_lookup.get(token)
            fact_id = facts_lookup.get(token)

            if ctx_id:
                related_ctx.append(ctx_id)
                resolved += 1
            elif fact_id:
                related_facts.append(fact_id)
                resolved += 1
            else:
                unresolved.append(_UnresolvedLink(
                    source_file=row.source_path,
                    token=token,
                    reason="no matching business_context.title or client_facts.key",
                ))

        if not related_ctx and not related_facts:
            continue

        if dry_run:
            logger.info(
                "DRY-RUN pass2 would update %s: +%d ctx, +%d facts",
                row.title, len(related_ctx), len(related_facts),
            )
            continue

        if row.row_id is None:
            # Row wasn't written in pass 1 (upsert failed). Skip.
            continue

        try:
            update: dict[str, Any] = {}
            if related_ctx:
                update["related_context_ids"] = related_ctx
            if related_facts:
                update["related_fact_ids"] = related_facts

            supabase.table("business_context").update(update).eq(
                "id", row.row_id
            ).execute()
            logger.info(
                "UPDATED business_context %s: +%d ctx, +%d facts",
                row.row_id, len(related_ctx), len(related_facts),
            )
        except Exception as e:
            logger.error("pass-2 update failed for %s: %s", row.title, e)

    return resolved, unresolved


def _write_unresolved_log(unresolved: list[_UnresolvedLink], reports_dir: Path) -> Path | None:
    """Write the unresolved-link log. No-op (returns None) if there are none."""
    if not unresolved:
        return None

    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = reports_dir / f"load_context_unresolved_links-{ts}.log"

    lines = [
        "# Unresolved Obsidian-style backlinks",
        f"# generated: {datetime.now(timezone.utc).isoformat()}",
        f"# count: {len(unresolved)}",
        "",
    ]
    for item in unresolved:
        lines.append(
            f"{item.source_file}\t[[{item.token}]]\t{item.reason}"
        )
    log_path.write_text("\n".join(lines) + "\n")
    logger.info("wrote unresolved-link log: %s (%d entries)", log_path, len(unresolved))
    return log_path


async def load_context(
    supabase: Any,
    embedder: Any,
    *,
    root: Path,
    client_id: str,
    dry_run: bool = False,
    reports_dir: Path | None = None,
) -> dict[str, Any]:
    """Two-pass load of markdown context into business_context.

    Returns a summary dict:
        {'loaded': N, 'skipped': S, 'errors': E,
         'resolved_links': R, 'unresolved_links': U,
         'unresolved_log_path': Path|None}
    """
    reports_dir = reports_dir or (_REPO_ROOT / "data" / "reports")

    paths = walk_markdown(root)
    if not paths:
        logger.info("no markdown files found under %s, nothing to load", root)
        return {
            "loaded": 0, "skipped": 0, "errors": 0,
            "resolved_links": 0, "unresolved_links": 0,
            "unresolved_log_path": None,
        }

    logger.info("found %d markdown files under %s", len(paths), root)

    loaded, skipped, errors = await _pass_1_upsert(
        supabase, embedder,
        paths=paths, client_id=client_id, dry_run=dry_run,
    )

    resolved, unresolved = await _pass_2_resolve(
        supabase,
        loaded=loaded, client_id=client_id, dry_run=dry_run,
    )

    # In dry-run mode we still show what would be unresolved, but we don't
    # write a real log file to disk (keeps --dry-run a true no-op on disk).
    log_path: Path | None = None
    if unresolved and not dry_run:
        log_path = _write_unresolved_log(unresolved, reports_dir)
    elif unresolved and dry_run:
        for item in unresolved:
            logger.info(
                "DRY-RUN unresolved: %s [[%s]] — %s",
                item.source_file, item.token, item.reason,
            )

    return {
        "loaded": len(loaded),
        "skipped": skipped,
        "errors": errors,
        "resolved_links": resolved,
        "unresolved_links": len(unresolved),
        "unresolved_log_path": log_path,
    }


def _build_supabase(url: str, key: str) -> Any:
    from supabase import create_client
    return create_client(url, key)


def _build_embedder(api_key: str) -> Any:
    return VoyageEmbedder(api_key=api_key)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load context/{client}/**/*.md into business_context with "
                    "Obsidian-style [[backlink]] resolution."
    )
    parser.add_argument("--client-id", required=True, help="Client ID to load under.")
    parser.add_argument(
        "--root", default=None,
        help="Directory to walk. Default: context/{client-id}/",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse + resolve without writing or embedding.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv or sys.argv[1:])

    root = Path(args.root) if args.root else _REPO_ROOT / "context" / args.client_id

    if args.dry_run:
        summary = asyncio.run(load_context(
            supabase=None, embedder=None,
            root=root, client_id=args.client_id, dry_run=True,
        ))
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
        summary = asyncio.run(load_context(
            supabase=supabase, embedder=embedder,
            root=root, client_id=args.client_id, dry_run=False,
        ))

    prefix = "DRY-RUN " if args.dry_run else ""
    print(
        f"{prefix}context load complete for client_id={args.client_id}: "
        f"{summary['loaded']} loaded, {summary['skipped']} skipped, "
        f"{summary['errors']} errors; {summary['resolved_links']} links resolved, "
        f"{summary['unresolved_links']} unresolved"
    )
    if summary.get("unresolved_log_path"):
        print(f"Unresolved links logged to: {summary['unresolved_log_path']}")
    return 0 if summary["errors"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
