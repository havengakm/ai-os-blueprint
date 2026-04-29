"""Cheap-resolve pipeline stage — fill company-level data BEFORE score_v1.

Per the 2026-04-29 Pattern C decision doc
(docs/superpowers/decisions/2026-04-29-scout-pipeline-order.md): cheap-tier
resolvers run between pull and score_v1 to populate fields that
score_v1's "fit" calculation needs (company_domain, industry) AND that
the downstream identity stage needs as inputs (Apollo + Hunter both
require a domain).

Stage runs each resolver against each unresolved contact. A resolver's
``applies_to(contact)`` filter decides per-source eligibility (e.g. the
ClutchProfileResolver only handles Clutch-sourced contacts). Multiple
resolvers can fill different fields on the same contact; later resolvers
fill only fields earlier resolvers left blank.

Pattern matches ``identity.py`` — standalone stage with its own
StorageBackend Protocol; no BaseSystem inheritance, no foundation loading.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ContactRow:
    """Minimal contact shape needed by the cheap-resolve stage."""

    contact_id: str
    company: str
    source: str
    company_domain: str | None
    industry: str | None
    raw_data: dict[str, Any]


@dataclass
class CheapResolveStageResult:
    """Aggregate result of a cheap-resolve stage run."""

    client_id: str
    dry_run: bool
    total_eligible: int = 0
    total_updated: int = 0
    total_skipped: int = 0  # resolver had nothing to add
    total_errored: int = 0
    by_resolver: dict[str, int] = field(default_factory=dict)


class CheapResolveStorageBackend(Protocol):
    """Storage contract for the cheap-resolve stage."""

    async def get_unresolved_contacts(
        self, client_id: str, *, limit: int | None = None,
    ) -> list[ContactRow]:
        """Return contacts where company_domain IS NULL AND status='new'.
        These are the freshly-pulled contacts that haven't been scored yet.
        Caller-supplied limit caps batch size."""
        ...

    async def update_contact_company_data(
        self,
        client_id: str,
        contact_id: str,
        *,
        company_domain: str | None = None,
        industry: str | None = None,
    ) -> None:
        """Set company-level fields on a contact row. Only non-None values
        are written (UPDATE is column-by-column to avoid clobbering data
        a different resolver filled)."""
        ...

    async def log_decision(
        self,
        client_id: str,
        *,
        decision_type: str,
        decision: str,
        context: dict[str, Any],
        reasoning: str | None = None,
        confidence: float | None = None,
    ) -> None:
        """Append an entry to decision_log."""
        ...


class CheapResolveAdapter(Protocol):
    """Cheap-tier resolver contract. Each adapter fills whatever fields it
    can; the stage merges results across adapters."""

    name: str

    def applies_to(self, contact: dict[str, Any]) -> bool:
        """Return True if this resolver has anything to contribute for this
        contact. Lets per-source resolvers (e.g. ClutchProfileResolver)
        skip non-source contacts cheaply."""
        ...

    async def resolve(self, contact: dict[str, Any]) -> dict[str, Any]:
        """Return a dict of newly-discovered company fields. Empty dict
        on miss. Stage merges these onto the contact row."""
        ...


class CheapResolveStage:
    """Run each cheap-resolve adapter against each unresolved contact;
    persist newly-filled fields; log a stage summary at the end."""

    def __init__(
        self,
        adapters: list[CheapResolveAdapter],
        storage: CheapResolveStorageBackend,
    ) -> None:
        self._adapters = list(adapters)
        self._storage = storage

    async def run(
        self,
        client_id: str,
        *,
        dry_run: bool = False,
        limit: int | None = None,
    ) -> CheapResolveStageResult:
        result = CheapResolveStageResult(client_id=client_id, dry_run=dry_run)

        contacts = await self._storage.get_unresolved_contacts(
            client_id, limit=limit,
        )
        result.total_eligible = len(contacts)

        for contact_row in contacts:
            contact_dict = {
                "contact_id": contact_row.contact_id,
                "company": contact_row.company,
                "source": contact_row.source,
                "company_domain": contact_row.company_domain,
                "industry": contact_row.industry,
                "raw_data": contact_row.raw_data,
            }
            merged: dict[str, Any] = {}

            for adapter in self._adapters:
                if not adapter.applies_to(contact_dict):
                    continue
                try:
                    delta = await adapter.resolve(contact_dict)
                except Exception as exc:
                    await self._storage.log_decision(
                        client_id,
                        decision_type="source_selection",
                        decision="cheap_resolve_adapter_failed",
                        reasoning=f"{type(exc).__name__}: {exc}",
                        context={
                            "adapter_name": adapter.name,
                            "contact_id": contact_row.contact_id,
                        },
                    )
                    result.total_errored += 1
                    continue

                if delta:
                    # Only apply fields not already filled (first-resolver-wins
                    # per field).
                    for k, v in delta.items():
                        if v is None or merged.get(k) is not None:
                            continue
                        if contact_dict.get(k) is None:
                            merged[k] = v
                    if merged:
                        result.by_resolver[adapter.name] = (
                            result.by_resolver.get(adapter.name, 0) + 1
                        )

            if merged and not dry_run:
                try:
                    await self._storage.update_contact_company_data(
                        client_id,
                        contact_row.contact_id,
                        company_domain=merged.get("company_domain"),
                        industry=merged.get("industry"),
                    )
                    result.total_updated += 1
                except Exception as exc:
                    await self._storage.log_decision(
                        client_id,
                        decision_type="source_selection",
                        decision="cheap_resolve_persist_failed",
                        reasoning=f"{type(exc).__name__}: {exc}",
                        context={"contact_id": contact_row.contact_id},
                    )
                    result.total_errored += 1
            elif merged and dry_run:
                result.total_updated += 1  # would-be update
            else:
                result.total_skipped += 1

        await self._storage.log_decision(
            client_id,
            decision_type="source_selection",
            decision="cheap_resolve_stage_summary",
            reasoning=(
                f"Processed {result.total_eligible} contacts: "
                f"{result.total_updated} updated, "
                f"{result.total_skipped} skipped, "
                f"{result.total_errored} errored. "
                f"By resolver: {result.by_resolver}"
            ),
            context={
                "total_eligible": result.total_eligible,
                "total_updated": result.total_updated,
                "total_skipped": result.total_skipped,
                "total_errored": result.total_errored,
                "by_resolver": result.by_resolver,
                "dry_run": dry_run,
            },
        )
        return result
