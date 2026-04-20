"""Identity-lookup pipeline stage — orchestrator-plus-persistence layer.

Fetches contacts eligible for identity lookup, dispatches to IdentityOrchestrator,
persists results, and returns a structured summary for observability.

This is a standalone pipeline stage — NOT a BaseSystem subclass.
BaseSystem wiring is deferred to Task 17.

Pattern mirrors pull.py exactly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from systems.scout.identity.orchestrator import IdentityOrchestrator


@dataclass
class ContactRow:
    """Minimal contact shape needed by the identity stage.

    Mirrors RawCompanyContact's style in pull.py — no full DB row mapping.
    """

    contact_id: str
    company_name: str
    company_domain: str | None
    icp_score: int


@dataclass
class IdentityStageResult:
    """Aggregate result of an identity-lookup stage run."""

    client_id: str
    dry_run: bool
    total_eligible: int = 0
    total_resolved: int = 0
    total_archived: int = 0
    total_errored: int = 0
    by_source: dict[str, int] = field(
        default_factory=lambda: {
            "apollo_people": 0,
            "hunter_domain": 0,
            "claude_scraper": 0,
        }
    )


class IdentityStorageBackend(Protocol):
    """Storage contract for the identity-lookup stage.

    Kept deliberately small — Task 17 wraps a real Supabase client;
    tests use an in-memory fake.
    """

    async def get_eligible_contacts(
        self,
        client_id: str,
        *,
        archive_floor: int,
        limit: int | None = None,
    ) -> list[ContactRow]:
        """Return contacts where icp_score >= archive_floor and first_name IS NULL
        (no identity resolved yet) and status NOT IN ('archived',
        'archived_no_decision_maker', 'killed'). Caller-supplied limit caps
        batch size; None means no cap."""
        ...

    async def update_contact_identity(
        self,
        client_id: str,
        contact_id: str,
        *,
        first_name: str,
        last_name: str,
        title: str | None,
        email: str,
        linkedin_url: str | None,
        identity_source: str,
    ) -> None:
        """Persist resolved identity fields on a contact row."""
        ...

    async def archive_contact_no_decision_maker(
        self,
        client_id: str,
        contact_id: str,
    ) -> None:
        """Set contact.status = 'archived_no_decision_maker'."""
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
        """Append an entry to decision_log. Mirrors pull.py exactly."""
        ...


class IdentityStage:
    """Fetches eligible contacts, resolves identities, persists results.

    Standalone orchestrator — no BaseSystem, no foundation loading (Task 17).
    """

    def __init__(
        self,
        orchestrator: IdentityOrchestrator,
        storage: IdentityStorageBackend,
        *,
        archive_floor: int = 35,
    ) -> None:
        self._orchestrator = orchestrator
        self._storage = storage
        self._archive_floor = archive_floor

    async def run(
        self,
        client_id: str,
        *,
        dry_run: bool = False,
        limit: int | None = None,
    ) -> IdentityStageResult:
        """Run the identity-lookup stage.

        1. Fetch eligible contacts.
        2. For each, call orchestrator.resolve(client_id, company_name, company_domain).
        3. On hit AND not dry_run: update_contact_identity(...).
        4. On miss AND not dry_run: archive_contact_no_decision_maker(...).
        5. On persistence exception: increment total_errored, log a decision,
           continue to next contact (never abort the stage).
        6. Always log a final "identity_stage_summary" decision_log entry
           (even on dry_run) with the full IdentityStageResult counts.
        """
        result = IdentityStageResult(client_id=client_id, dry_run=dry_run)

        contacts = await self._storage.get_eligible_contacts(
            client_id,
            archive_floor=self._archive_floor,
            limit=limit,
        )
        result.total_eligible = len(contacts)

        for contact in contacts:
            orc_result = await self._orchestrator.resolve(
                client_id,
                contact.company_name,
                contact.company_domain,
            )

            if orc_result.identity is not None:
                # Hit
                if not dry_run:
                    try:
                        await self._storage.update_contact_identity(
                            client_id,
                            contact.contact_id,
                            first_name=orc_result.identity.first_name,
                            last_name=orc_result.identity.last_name,
                            title=orc_result.identity.title,
                            email=orc_result.identity.email,
                            linkedin_url=orc_result.identity.linkedin_url,
                            identity_source=orc_result.source or orc_result.identity.source,
                        )
                    except Exception as exc:
                        await self._log_persist_failure(client_id, contact.contact_id, exc)
                        result.total_errored += 1
                        continue

                result.total_resolved += 1
                source_key = orc_result.source or ""
                if source_key in result.by_source:
                    result.by_source[source_key] += 1

            else:
                # Miss
                if not dry_run:
                    try:
                        await self._storage.archive_contact_no_decision_maker(
                            client_id,
                            contact.contact_id,
                        )
                    except Exception as exc:
                        await self._log_persist_failure(client_id, contact.contact_id, exc)
                        result.total_errored += 1
                        continue

                result.total_archived += 1

        await self._storage.log_decision(
            client_id,
            decision_type="enrichment_choice",
            decision="identity_stage_summary",
            reasoning=(
                f"Processed {result.total_eligible} contacts: "
                f"{result.total_resolved} resolved, "
                f"{result.total_archived} archived, "
                f"{result.total_errored} errored"
            ),
            context={
                "client_id": client_id,
                "dry_run": dry_run,
                "total_eligible": result.total_eligible,
                "total_resolved": result.total_resolved,
                "total_archived": result.total_archived,
                "total_errored": result.total_errored,
                "by_source": result.by_source,
            },
            confidence=None,
        )

        return result

    async def _log_persist_failure(
        self,
        client_id: str,
        contact_id: str,
        exc: Exception,
    ) -> None:
        """Log a persistence failure decision. Never raises."""
        reasoning = f"{type(exc).__name__}: {exc}"[:500]
        try:
            await self._storage.log_decision(
                client_id,
                decision_type="enrichment_choice",
                decision=f"identity_stage:persist_failed:{contact_id}",
                reasoning=reasoning,
                context={"contact_id": contact_id},
            )
        except Exception:
            pass  # logging must never propagate
