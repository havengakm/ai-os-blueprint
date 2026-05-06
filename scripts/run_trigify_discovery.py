"""Run a Trigify discovery pass for an AIOS client (Task 1.5.9c CLI).

Wraps ``TrigifyDiscoverySource.pull()``. Invokes the pull, optionally
pipes the returned list through ``PullOrchestrator`` for persistence, and
always generates a markdown summary report under ``data/reports/``.

Usage:
    uv run python scripts/run_trigify_discovery.py --client-id=<id>
        [--search-subset=intent|competitor|thought_leader|brand]
        [--max-companies=100]
        [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aios.scout.pipeline.pull import PullOrchestrator, PullResult  # noqa: E402
from aios.scout.sources.base import CompanySourceAdapter, RawCompanyContact  # noqa: E402
from aios.scout.sources.trigify_discovery import (  # noqa: E402
    DiscoverySummary,
    TrigifyDiscoverySource,
)
from aios.scout.supabase_backends.pull import SupabasePullBackend  # noqa: E402
from aios.scout.supabase_backends.trigify import (  # noqa: E402
    SupabaseDiscoveryStorage,
)

logger = logging.getLogger(__name__)

VALID_SEARCH_SUBSETS: tuple[str, ...] = (
    "intent", "competitor", "thought_leader", "brand",
)
DEFAULT_MAX_COMPANIES = 100
_SAMPLE_CONTACTS_SHOWN = 5


def _build_supabase(url: str, key: str) -> Any:
    """Construct a supabase.Client. Factored out for test monkeypatching."""
    from supabase import create_client
    return create_client(url, key)


def _reports_dir() -> Path:
    return _REPO_ROOT / "data" / "reports"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _render_report(
    *,
    client_id: str,
    dry_run: bool,
    search_subset: str | None,
    max_companies: int,
    contacts: list[RawCompanyContact],
    summary: DiscoverySummary | None,
    pull_result: PullResult | None,
) -> str:
    """Render the markdown report. Called on BOTH dry-run and live paths."""
    parts: list[str] = [
        f"# Trigify discovery report — client {client_id}\n",
        f"- generated: {datetime.now(timezone.utc).isoformat()}",
        f"- dry_run: {dry_run}",
        f"- search_subset: {search_subset or '(all enabled)'}",
        f"- max_companies: {max_companies}\n",
    ]

    if summary is not None:
        by_type = (
            "\n".join(
                f"- {m}: {n}" for m, n in sorted(summary.by_monitor_type.items())
            )
            if summary.by_monitor_type else "- (no leads by monitor type)"
        )
        parts.append(
            "## Summary\n\n"
            f"- searches_queried: {summary.searches_queried}\n"
            f"- posts_scanned: {summary.posts_scanned}\n"
            f"- posts_below_threshold: {summary.posts_below_threshold}\n"
            f"- posts_qualified: {summary.posts_qualified}\n"
            f"- engagers_extracted: {summary.engagers_extracted}\n"
            f"- engagers_skipped_no_employer: {summary.engagers_skipped_no_employer}\n"
            f"- leads_returned: {summary.leads_returned}\n"
            f"- errors: {summary.errors}\n\n"
            f"### By monitor type\n\n{by_type}\n"
        )

    sample_lines: list[str] = []
    for c in contacts[:_SAMPLE_CONTACTS_SHOWN]:
        rd = c.raw_data or {}
        sample_lines.append(
            f"- **{c.company}** ({c.company_domain or 'no-domain'}) — "
            f"engager: {rd.get('engager_name', '?')} "
            f"[{rd.get('engager_title', '?')}] via "
            f"{rd.get('monitor_type', '?')} — "
            f"post engagement: {rd.get('post_engagement_total', '?')}"
        )
    if len(contacts) > _SAMPLE_CONTACTS_SHOWN:
        sample_lines.append(f"- ... +{len(contacts) - _SAMPLE_CONTACTS_SHOWN} more")
    sample_body = "\n".join(sample_lines) if sample_lines else "(no leads returned)"
    parts.append(f"## Sample leads\n\n{sample_body}\n")

    if pull_result is not None:
        per_source = "\n".join(
            f"  - {s.adapter_name}: pulled={s.pulled} "
            f"inserted={s.inserted} skipped={s.skipped_duplicate}"
            + (f" error={s.error}" if s.error else "")
            for s in pull_result.per_source
        )
        parts.append(
            "## PullOrchestrator result\n\n"
            f"- total_pulled: {pull_result.total_pulled}\n"
            f"- total_inserted: {pull_result.total_inserted}\n"
            f"- total_skipped_duplicate: {pull_result.total_skipped_duplicate}\n"
            + (per_source + "\n" if per_source else "")
        )

    return "\n".join(parts) + "\n"


def _write_report(content: str) -> Path:
    reports = _reports_dir()
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / f"trigify-discovery-{_timestamp()}.md"
    path.write_text(content)
    return path


class _CachedAdapter:
    """Wraps a pre-pulled list into a ``CompanySourceAdapter``.

    We pull once (to capture contacts + summary for the report), then hand
    the same list to ``PullOrchestrator`` via this wrapper so the
    orchestrator's dedup + persistence logic runs without a second HTTP
    round-trip. Name mirrors the underlying source so
    ``active_directories`` matching + decision_log source names stay
    correct.
    """

    def __init__(self, name: str, rows: list[RawCompanyContact]) -> None:
        self.name = name
        self._rows = rows

    async def pull(
        self,
        client_id: str,  # noqa: ARG002 — part of Protocol signature
        max_companies: int,  # noqa: ARG002
        dry_run: bool = False,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> list[RawCompanyContact]:
        return list(self._rows)


async def _run(
    *,
    client_id: str,
    max_companies: int,
    dry_run: bool,
    search_subset: str | None,
    source: TrigifyDiscoverySource,
    orchestrator_factory: Any,
) -> int:
    """Core async flow. Returns exit code (0 success, 1 failure).

    ``orchestrator_factory`` is a callable taking one ``CompanySourceAdapter``
    and returning a ``PullOrchestrator`` with that adapter registered.
    Injected so tests can supply a fake orchestrator without patching
    module state.
    """
    # Forward search_subset only when set — avoids passing None which would
    # be treated as a filter key by the source.
    pull_kwargs: dict[str, Any] = {}
    if search_subset is not None:
        pull_kwargs["search_subset"] = search_subset

    contacts = await source.pull(
        client_id=client_id,
        max_companies=max_companies,
        dry_run=dry_run,
        **pull_kwargs,
    )
    summary = source.last_summary

    pull_result: PullResult | None = None
    if not dry_run:
        # Pipe through PullOrchestrator for dedup + persistence. Wrap the
        # already-pulled list so we don't hit Trigify twice.
        cached = _CachedAdapter(source.name, contacts)
        orchestrator: PullOrchestrator = orchestrator_factory(cached)
        pull_result = await orchestrator.run(
            client_id=client_id,
            max_companies_per_source=max_companies,
            dry_run=False,
            source_filter=[source.name],
        )

    report = _render_report(
        client_id=client_id,
        dry_run=dry_run,
        search_subset=search_subset,
        max_companies=max_companies,
        contacts=contacts,
        summary=summary,
        pull_result=pull_result,
    )
    report_path = _write_report(report)

    prefix = "DRY-RUN " if dry_run else ""
    leads = summary.leads_returned if summary else len(contacts)
    print(
        f"{prefix}trigify discovery complete for client_id={client_id}: "
        f"{leads} leads returned"
    )
    print(f"Report: {report_path}")
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a Trigify discovery pass. Pulls engagers from configured "
            "monitors, writes a markdown report, optionally pipes results "
            "through PullOrchestrator to persist into contacts."
        ),
    )
    parser.add_argument(
        "--client-id", required=True,
        help="Client ID to run discovery for.",
    )
    parser.add_argument(
        "--search-subset", default=None, choices=VALID_SEARCH_SUBSETS,
        help="Restrict pull to one monitor type. Default: all enabled.",
    )
    parser.add_argument(
        "--max-companies", type=int, default=DEFAULT_MAX_COMPANIES,
        help=f"Cap on leads returned. Default: {DEFAULT_MAX_COMPANIES}.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Read-only preview — no PullOrchestrator / contacts-table writes.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv or sys.argv[1:])

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print(
            "ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set "
            "in the environment (or loaded from .env before running).",
            file=sys.stderr,
        )
        return 1

    if not os.environ.get("TRIGIFY_API_KEY"):
        print(
            "ERROR: TRIGIFY_API_KEY must be set. Add it to .env before "
            "running discovery.",
            file=sys.stderr,
        )
        return 1

    try:
        supabase = _build_supabase(url, key)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: failed to construct Supabase client: {e}", file=sys.stderr)
        return 1

    discovery_storage = SupabaseDiscoveryStorage(supabase)
    source = TrigifyDiscoverySource(storage=discovery_storage)

    def orchestrator_factory(adapter: CompanySourceAdapter) -> PullOrchestrator:
        pull_storage = SupabasePullBackend(supabase)
        # Single-adapter route: use the adapter's self-reported name as the
        # routing key — keeps run_trigify_discovery's stand-alone path intact
        # without touching client_config.
        return PullOrchestrator(
            adapters={adapter.name: adapter}, storage=pull_storage,
        )

    try:
        return asyncio.run(_run(
            client_id=args.client_id,
            max_companies=args.max_companies,
            dry_run=args.dry_run,
            search_subset=args.search_subset,
            source=source,
            orchestrator_factory=orchestrator_factory,
        ))
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except EnvironmentError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
