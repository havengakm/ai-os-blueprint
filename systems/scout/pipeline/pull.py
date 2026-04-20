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
        """True if a contact already exists matching either (source, source_id)
        OR company_domain (normalised). Either pair can be omitted if not
        known — caller passes what it has."""
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
        reasoning: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Append an entry to decision_log."""
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

        # Track domains seen within this run for intra-run dedup
        seen_domains_in_run: set[str] = set()

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
                    decision_type="enrichment_choice",
                    decision="source_adapter_failed",
                    reasoning=summary.error,
                    context={"adapter_name": adapter_name},
                )
                result.per_source.append(summary)
                continue

            summary.pulled = len(rows)

            for row in rows:
                normalised = normalize_domain(row.company_domain)

                # Intra-run dedup on domain
                if normalised and normalised in seen_domains_in_run:
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

                if normalised:
                    seen_domains_in_run.add(normalised)
                summary.inserted += 1

            await self._storage.log_decision(
                client_id,
                decision_type="enrichment_choice",
                decision="source_adapter_pulled",
                reasoning=f"pulled={summary.pulled} inserted={summary.inserted} skipped={summary.skipped_duplicate}",
                context={"adapter_name": adapter_name, "dry_run": dry_run},
            )
            result.per_source.append(summary)

        result.total_pulled = sum(s.pulled for s in result.per_source)
        result.total_inserted = sum(s.inserted for s in result.per_source)
        result.total_skipped_duplicate = sum(s.skipped_duplicate for s in result.per_source)
        return result
