"""ScreenStage — pipeline stage that runs hard rule-based rejection AFTER score_v1.

Filters contacts on blacklists and required-field presence before enrichment spend.
Standalone stage — NOT a BaseSystem subclass. BaseSystem wiring is Task 17.
Pattern mirrors score_stage.py exactly.

Decision type: 'icp_threshold' (screen_contact not in CHECK constraint; flagged in task report).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Pure function
# ---------------------------------------------------------------------------


def screen_contact(contact: dict[str, Any], client_config: dict[str, Any]) -> tuple[bool, str]:
    """Return (passed, reason). passed=True → empty reason.

    Rules in order (short-circuit):
    1. Both first_name and last_name blank/None → 'missing_name'
    2. company blank/None → 'missing_company'
    3. company (case-insensitive) in blacklist_companies → 'blacklisted_company:{company}'
    4. company_domain (case-insensitive) in blacklist_domains → 'blacklisted_domain:{domain}'
    5. Else → (True, '')

    A missing icp block in client_config is treated as empty blacklists.
    """
    icp = client_config.get("icp") or {}
    blacklist_companies = {c.lower() for c in icp.get("blacklist_companies") or []}
    blacklist_domains = {d.lower() for d in icp.get("blacklist_domains") or []}

    first_name = contact.get("first_name") or ""
    last_name = contact.get("last_name") or ""
    if not first_name.strip() and not last_name.strip():
        return False, "missing_name"

    company = contact.get("company") or ""
    if not company.strip():
        return False, "missing_company"

    if company.lower() in blacklist_companies:
        return False, f"blacklisted_company:{company}"

    company_domain = contact.get("company_domain") or ""
    if company_domain and company_domain.lower() in blacklist_domains:
        return False, f"blacklisted_domain:{company_domain}"

    return True, ""


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class ContactToScreen:
    """Minimum fields the stage needs from a contact row."""

    contact_id: str
    first_name: str | None
    last_name: str | None
    company: str | None
    company_domain: str | None


@dataclass
class ScreenStageResult:
    """Aggregate result of a screening-stage run."""

    client_id: str
    dry_run: bool
    total_eligible: int = 0
    total_passed: int = 0
    total_rejected: int = 0
    total_errored: int = 0
    rejections_by_reason: dict[str, int] = field(
        default_factory=lambda: {
            "missing_name": 0,
            "missing_company": 0,
            "blacklisted_company": 0,
            "blacklisted_domain": 0,
        }
    )


# ---------------------------------------------------------------------------
# Storage protocol
# ---------------------------------------------------------------------------

_KNOWN_BUCKETS = frozenset(
    {"missing_name", "missing_company", "blacklisted_company", "blacklisted_domain"}
)


class ScreenStorageBackend(Protocol):
    """Storage contract for the screen stage.

    Task 17 wraps a real Supabase client; tests use an in-memory fake.
    """

    async def get_client_config(self, client_id: str) -> dict[str, Any]: ...

    async def get_contacts_for_screening(
        self,
        client_id: str,
        *,
        limit: int | None = None,
    ) -> list[ContactToScreen]:
        """Contacts with status='screened' (scored, tier in ABCD) and not yet past this stage."""
        ...

    async def mark_contact_passed(self, client_id: str, contact_id: str) -> None:
        """Transition status 'screened' → 'ready' (ready for identity + enrichment)."""
        ...

    async def mark_contact_rejected(
        self,
        client_id: str,
        contact_id: str,
        *,
        reason: str,
    ) -> None:
        """Set status='dead', store reason in raw_data or equivalent."""
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
    ) -> None: ...


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------


class ScreenStage:
    """Fetches eligible contacts, screens them via hard rules, persists results.

    Standalone orchestrator — no BaseSystem, no foundation loading (Task 17).
    """

    def __init__(self, storage: ScreenStorageBackend) -> None:
        self._storage = storage

    async def run(
        self,
        client_id: str,
        *,
        dry_run: bool = False,
        limit: int | None = None,
    ) -> ScreenStageResult:
        """Run the screen stage.

        1. Fetch client_config.
        2. Fetch eligible contacts.
        3. For each: call screen_contact → route pass/fail.
        4. Wrap persistence in try/except; log failure, increment errored, continue.
        5. Emit one summary decision_log entry (even on dry_run).
        """
        result = ScreenStageResult(client_id=client_id, dry_run=dry_run)

        client_config = await self._storage.get_client_config(client_id)

        contacts = await self._storage.get_contacts_for_screening(
            client_id, limit=limit
        )
        result.total_eligible = len(contacts)

        for contact in contacts:
            contact_dict = {
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "company": contact.company,
                "company_domain": contact.company_domain,
            }
            passed, reason = screen_contact(contact_dict, client_config)

            if passed:
                if not dry_run:
                    try:
                        await self._storage.mark_contact_passed(client_id, contact.contact_id)
                    except Exception as exc:
                        await self._log_persist_failure(client_id, contact.contact_id, exc)
                        result.total_errored += 1
                        continue
                result.total_passed += 1
            else:
                bucket = reason.split(":")[0]
                if bucket not in _KNOWN_BUCKETS:
                    raise ValueError(
                        f"Unknown rejection bucket {bucket!r} from screen_contact. "
                        "Update rejections_by_reason and _KNOWN_BUCKETS."
                    )
                if not dry_run:
                    try:
                        await self._storage.mark_contact_rejected(
                            client_id, contact.contact_id, reason=reason
                        )
                    except Exception as exc:
                        await self._log_persist_failure(client_id, contact.contact_id, exc)
                        result.total_errored += 1
                        continue
                result.total_rejected += 1
                result.rejections_by_reason[bucket] += 1

        await self._storage.log_decision(
            client_id,
            decision_type="icp_threshold",
            decision="screen_stage_summary",
            reasoning=(
                f"Screened {result.total_eligible} contacts: "
                f"{result.total_passed} passed, {result.total_rejected} rejected "
                f"({result.rejections_by_reason}), {result.total_errored} errored"
            ),
            context={
                "client_id": client_id,
                "dry_run": dry_run,
                "total_eligible": result.total_eligible,
                "total_passed": result.total_passed,
                "total_rejected": result.total_rejected,
                "total_errored": result.total_errored,
                "rejections_by_reason": dict(result.rejections_by_reason),
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
        """Log a per-contact persistence failure. Never raises."""
        reasoning = f"{type(exc).__name__}: {exc}"[:500]
        try:
            await self._storage.log_decision(
                client_id,
                decision_type="icp_threshold",
                decision=f"screen_stage:persist_failed:{contact_id}",
                reasoning=reasoning,
                context={"contact_id": contact_id},
            )
        except Exception:
            pass  # logging must never propagate
