"""Pull-stage orchestrator — dispatches source adapters in priority order.

Reads `client_config.active_directories` (via the injected StorageBackend),
runs each active adapter, dedups results across sources using (source, source_id)
AND normalised company_domain, returns a structured summary. Persistence of
new contacts + decision_log entries is delegated to the StorageBackend.

Amendment 2 (2026-04-20): company-level stage only. Person identity is
resolved by Task 9.5. This orchestrator must NOT fabricate person data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from systems.scout.sources.base import CompanySourceAdapter, RawCompanyContact
from systems.scout.sources.utils import normalize_domain


@dataclass
class SourceSummary:
    """Per-source counts for a pull run."""

    adapter_name: str
    pulled: int = 0
    inserted: int = 0
    skipped_duplicate: int = 0
    error: str | None = None


@dataclass
class PullResult:
    """Aggregate result of a pull run."""

    client_id: str
    dry_run: bool
    total_pulled: int = 0
    total_inserted: int = 0
    total_skipped_duplicate: int = 0
    per_source: list[SourceSummary] = field(default_factory=list)


class StorageBackend(Protocol):
    """Contract for whatever persists pull output + logs decisions.

    Kept deliberately small — real implementation (Task 17) wraps a Supabase
    client; tests use an in-memory fake.
    """

    async def get_active_directories(self, client_id: str) -> list[str]:
        """Return list of adapter names this client is configured to pull from.
        Reads client_config.active_directories."""
        ...

    async def contact_exists(
        self,
        client_id: str,
        *,
        source: str | None = None,
        source_id: str | None = None,
        company_domain: str | None = None,
    ) -> bool:
        """Advisory dedup check — True if a contact already exists matching
        EITHER (source, source_id) OR company_domain (normalised).

        Preconditions: at least one of (source_id, company_domain) must be
        provided. Calling with all identifiers None is a programmer error.

        Advisory only: ultimate uniqueness is enforced by
        `UNIQUE (client_id, source, source_id)` in 002_scout.sql. Real
        Task-17 implementations should use `INSERT ... ON CONFLICT DO NOTHING`
        and treat this method as a pre-filter for counters, not a lock.
        Between this check and a subsequent insert_contact call, a parallel
        run for the same client_id can race."""
        ...

    async def insert_contact(
        self,
        client_id: str,
        contact: RawCompanyContact,
    ) -> None:
        """Persist a new contact row. Orchestrator has already deduped."""
        ...

    async def log_decision(
        self,
        client_id: str,
        *,
        decision_type: str,
        decision: str,
        context: dict[str, Any],  # required, matches the NOT NULL DB schema
        reasoning: str | None = None,
        confidence: float | None = None,  # matches real DecisionLogger signature
    ) -> None:
        """Append an entry to decision_log. `context` is required (DB column is
        NOT NULL). `confidence` feeds the learning loop; orchestrator passes a
        ratio-based proxy where applicable."""
        ...


class PullOrchestrator:
    """Dispatches source adapters in priority order, dedups, persists.

    Priority is the order in which adapters are passed to the constructor
    (NOT a priority field on the adapter itself — keeps adapters stateless).
    """

    def __init__(
        self,
        adapters: list[CompanySourceAdapter],
        storage: StorageBackend,
    ) -> None:
        self._adapters_by_name = {a.name: a for a in adapters}
        self._ordered_names = [a.name for a in adapters]
        self._storage = storage

    async def run(
        self,
        client_id: str,
        *,
        max_companies_per_source: int = 50,
        dry_run: bool = False,
        source_filter: list[str] | None = None,
        adapter_kwargs: dict[str, dict[str, Any]] | None = None,
    ) -> PullResult:
        """Run the pull stage.

        - `source_filter`: optional subset of adapter names to run. Defaults
          to everything in `client_config.active_directories`.
        - `adapter_kwargs`: per-adapter keyword args forwarded to `pull()`.
          e.g. `{"csv_ingest": {"csv_content": "..."}}`.

        Priority + tie-break semantics (documented per 2026-04-20 code review):
        - Adapters run in construction order (NOT in `storage.active_directories` order)
        - On a dedup tie (same domain / same company name across sources), the
          FIRST adapter to produce the row wins. Later matches become
          `skipped_duplicate`. This favours whichever adapter you registered first
          in the PullOrchestrator constructor — typically the higher-quality source.
        - If two sources have overlapping coverage and you want the richer source
          to win, register it first. Merge-on-conflict semantics are deliberately
          out of scope for Plan 1.
        """
        result = PullResult(client_id=client_id, dry_run=dry_run)

        active = await self._storage.get_active_directories(client_id)
        if source_filter is not None:
            active = [name for name in active if name in source_filter]

        # Respect orchestrator construction order when the storage list is unordered.
        # Registered adapters run first (in construction order), then any ghost names.
        active_set = set(active)
        ordered_active = [name for name in self._ordered_names if name in active_set]
        ghost_names = [name for name in active if name not in self._adapters_by_name]
        adapter_kwargs = adapter_kwargs or {}

        # Intra-run dedup keys. Priority order:
        #   1. normalised company_domain (if present)
        #   2. (source, source_id) tuple — cross-source but same source_id identifier
        #   3. lower-cased company name — fallback when domain is null and source_id
        #      differs (happens for Clutch rows from two categories featuring the same company)
        seen_domains_in_run: set[str] = set()
        seen_name_fallback: set[str] = set()

        for adapter_name in ordered_active + ghost_names:
            adapter = self._adapters_by_name.get(adapter_name)
            if adapter is None:
                # Configured but not registered — log and skip
                await self._storage.log_decision(
                    client_id,
                    decision_type="system_config",
                    decision="source_adapter_not_registered",
                    reasoning=f"active_directories lists '{adapter_name}' but no adapter is registered with that name",
                    context={"adapter_name": adapter_name},
                )
                continue

            summary = SourceSummary(adapter_name=adapter_name)
            try:
                kwargs = adapter_kwargs.get(adapter_name, {})
                rows = await adapter.pull(
                    client_id=client_id,
                    max_companies=max_companies_per_source,
                    dry_run=dry_run,
                    **kwargs,
                )
            except Exception as exc:
                summary.error = f"{type(exc).__name__}: {exc}"
                await self._storage.log_decision(
                    client_id,
                    decision_type="source_selection",
                    decision="source_adapter_failed",
                    reasoning=summary.error,
                    context={"adapter_name": adapter_name},
                )
                result.per_source.append(summary)
                continue

            summary.pulled = len(rows)

            for row in rows:
                normalised = normalize_domain(row.company_domain)
                name_key = (row.company or "").strip().lower()

                # Intra-run dedup on domain
                if normalised and normalised in seen_domains_in_run:
                    summary.skipped_duplicate += 1
                    continue

                # Intra-run dedup on company name (fallback when domain is null)
                if not normalised and name_key and name_key in seen_name_fallback:
                    summary.skipped_duplicate += 1
                    continue

                # Cross-run dedup against existing contacts
                already_exists = await self._storage.contact_exists(
                    client_id,
                    source=row.source,
                    source_id=row.source_id,
                    company_domain=normalised,
                )
                if already_exists:
                    summary.skipped_duplicate += 1
                    continue

                if not dry_run:
                    await self._storage.insert_contact(client_id, row)

                # Mark seen in intra-run sets
                if normalised:
                    seen_domains_in_run.add(normalised)
                elif name_key:
                    seen_name_fallback.add(name_key)
                summary.inserted += 1

            confidence = summary.inserted / max(summary.pulled, 1)
            await self._storage.log_decision(
                client_id,
                decision_type="source_selection",
                decision="source_adapter_pulled",
                reasoning=f"pulled={summary.pulled} inserted={summary.inserted} skipped={summary.skipped_duplicate}",
                context={
                    "adapter_name": adapter_name,
                    "dry_run": dry_run,
                    "pulled": summary.pulled,
                    "inserted": summary.inserted,
                    "skipped_duplicate": summary.skipped_duplicate,
                },
                confidence=confidence,
            )
            result.per_source.append(summary)

        result.total_pulled = sum(s.pulled for s in result.per_source)
        result.total_inserted = sum(s.inserted for s in result.per_source)
        result.total_skipped_duplicate = sum(s.skipped_duplicate for s in result.per_source)
        return result
