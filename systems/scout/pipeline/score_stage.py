"""ScoreStage — pipeline stage that wraps the pure scoring functions from score.py.

Fetches eligible contacts, scores them via score_v1 / score_v2, assigns tiers,
persists results, and logs one summary decision_log entry per run.

Standalone stage — NOT a BaseSystem subclass. BaseSystem wiring is Task 17.
Pattern mirrors identity.py and pull.py exactly.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


from systems.scout.pipeline.score import (
    DEFAULT_TIER_THRESHOLDS,
    assign_tier,
    score_v1,
    score_v2,
)


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class ContactToScore:
    """Minimum fields the stage needs from a contact row."""

    contact_id: str
    # Fit signals (pull payload)
    industry: str | None
    title: str | None
    employees: int | None
    geography: str | None
    # Reach signals (pull payload)
    email: str | None
    email_verified: bool
    linkedin_url: str | None
    phone: str | None
    # Recency signals (pull payload, may be empty for most contacts)
    raw_data: dict[str, Any]  # reads: funding_event_last_180d, recent_hiring
    # Intent signals (enrich output — empty for v1, populated for v2)
    research_data: dict[str, Any]  # reads: pain_match, activity_positive


@dataclass
class ScoreStageResult:
    """Aggregate result of a scoring-stage run."""

    client_id: str
    phase: str  # "v1" | "v2"
    dry_run: bool
    total_eligible: int = 0
    total_scored: int = 0
    total_archived: int = 0
    total_errored: int = 0
    tier_counts: dict[str, int] = field(
        default_factory=lambda: {"A": 0, "B": 0, "C": 0, "D": 0, "archive": 0}
    )


# ---------------------------------------------------------------------------
# Storage protocol
# ---------------------------------------------------------------------------


class ScoreStorageBackend(Protocol):
    """Storage contract for the scoring stage.

    Task 17 wraps a real Supabase client; tests use an in-memory fake.
    """

    async def get_client_config(self, client_id: str) -> dict[str, Any]:
        """Return the client's scoring config dict with `weights` and
        `tier_thresholds` keys populated (from client_config table).
        Caller treats missing keys as triggering defaults."""
        ...

    async def get_contacts_for_scoring(
        self,
        client_id: str,
        *,
        phase: str,
        limit: int | None = None,
    ) -> list[ContactToScore]:
        """Return contacts eligible for the given phase.
        v1: icp_score IS NULL (never scored)
        v2: status = 'enriched' AND icp_score IS NOT NULL"""
        ...

    async def update_contact_score(
        self,
        client_id: str,
        contact_id: str,
        *,
        score: int,
        tier: str,
        phase: str,
    ) -> None:
        """Persist score + tier + stage marker. On phase='v1', also
        transitions status 'new' → 'screened'. On phase='v2', status
        stays 'enriched'."""
        ...

    async def archive_contact(
        self,
        client_id: str,
        contact_id: str,
        *,
        reason: str,
    ) -> None:
        """Set status='archived' with reason embedded in raw_data or similar."""
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


class ScoreStage:
    """Fetches eligible contacts, scores them, persists results.

    Standalone orchestrator — no BaseSystem, no foundation loading (Task 17).
    """

    def __init__(self, storage: ScoreStorageBackend) -> None:
        self._storage = storage

    async def run(
        self,
        client_id: str,
        *,
        phase: str = "v1",
        dry_run: bool = False,
        limit: int | None = None,
    ) -> ScoreStageResult:
        """Run the scoring stage.

        1. Validate phase.
        2. Fetch client_config and contacts.
        3. For each contact: score → assign_tier → persist or archive.
        4. Wrap persistence in try/except; log failure, increment errored, continue.
        5. Emit one summary decision_log entry.
        """
        if phase not in ("v1", "v2"):
            raise ValueError("phase must be 'v1' or 'v2'")

        result = ScoreStageResult(client_id=client_id, phase=phase, dry_run=dry_run)

        client_config = await self._storage.get_client_config(client_id)

        contacts = await self._storage.get_contacts_for_scoring(
            client_id, phase=phase, limit=limit
        )
        result.total_eligible = len(contacts)

        score_fn = score_v1 if phase == "v1" else score_v2

        archive_floor: int = (
            client_config.get("tier_thresholds", {}).get(
                "archive_floor", DEFAULT_TIER_THRESHOLDS["archive_floor"]
            )
        )

        for contact in contacts:
            contact_dict = asdict(contact)
            score = score_fn(contact_dict, client_config)
            tier = assign_tier(score, client_config)

            if tier == "archive":
                if not dry_run:
                    try:
                        await self._storage.archive_contact(
                            client_id,
                            contact.contact_id,
                            reason="below_archive_floor",
                        )
                    except Exception as exc:
                        await self._log_persist_failure(client_id, contact.contact_id, exc)
                        result.total_errored += 1
                        continue
                result.total_archived += 1
                result.tier_counts["archive"] += 1
            else:
                if not dry_run:
                    try:
                        await self._storage.update_contact_score(
                            client_id,
                            contact.contact_id,
                            score=score,
                            tier=tier,
                            phase=phase,
                        )
                    except Exception as exc:
                        await self._log_persist_failure(client_id, contact.contact_id, exc)
                        result.total_errored += 1
                        continue
                result.total_scored += 1
                result.tier_counts[tier] += 1

        await self._storage.log_decision(
            client_id,
            decision_type="icp_threshold",
            decision="score_stage_summary",
            reasoning=(
                f"Phase {phase}: scored {result.total_scored}/{result.total_eligible} "
                f"contacts, archived {result.total_archived}, errored {result.total_errored}"
            ),
            context={
                "client_id": client_id,
                "phase": phase,
                "dry_run": dry_run,
                "total_eligible": result.total_eligible,
                "total_scored": result.total_scored,
                "total_archived": result.total_archived,
                "total_errored": result.total_errored,
                "tier_counts": result.tier_counts,
                "archive_floor": archive_floor,
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
                decision=f"score_stage:persist_failed:{contact_id}",
                reasoning=reasoning,
                context={"contact_id": contact_id},
            )
        except Exception:
            pass  # logging must never propagate
