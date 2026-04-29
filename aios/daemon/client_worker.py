"""Per-client nightly cycle runner (Task 16.6).

Runs the pipeline stages in sequence for ONE client:

    pull → score(phase="v1") → screen → identity → enrich
         → score(phase="v2") → compose

Every stage is wrapped in its own try/except — one failing stage does NOT
abort the cycle. Failures accumulate in ``result.errors`` for the operator
to review. This is "degraded mode": every client still gets every other
stage a chance to run, and the daemon continues to the next client.

Autonomy checks are ALREADY done inside each ``ScoutSystem.run_<stage>``
via ``_prime_foundation``. The daemon does not pre-gate.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from systems.scout.outreach.composer import ComposerStorageBackend
    from systems.scout.skill import ScoutSystem

logger = logging.getLogger(__name__)


# Pipeline stage order. score runs twice: v1 before screen, v2 after enrich.
# cheap_resolve runs between pull and score_v1 — fills company-level fields
# (domain, industry) so score_v1 can evaluate fit AND identity stage has a
# domain to query (Apollo + Hunter both REQUIRE a domain). Pattern C per
# docs/superpowers/decisions/2026-04-29-scout-pipeline-order.md.
STAGE_ORDER: tuple[str, ...] = (
    "pull",
    "cheap_resolve",
    "score_v1",
    "screen",
    "identity",
    "enrich",
    "score_v2",
    "compose",
)


@dataclass
class StageRun:
    """Result of one stage within a client cycle."""

    stage: str
    ok: bool
    started_at: str
    completed_at: str
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class ClientCycleResult:
    """Aggregate result of one nightly pass for one client."""

    client_id: str
    started_at: str
    completed_at: str
    stages_run: list[StageRun] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True iff every stage succeeded."""
        return not self.errors


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run_one_stage(
    scout: "ScoutSystem",
    stage: str,
    client_id: str,
    *,
    dry_run: bool,
    composer_backend: "ComposerStorageBackend | None",
    max_companies_per_source: int | None = None,
) -> StageRun:
    """Run one stage, capture outcome + timing. Never raises.

    ``max_companies_per_source`` (when set) is forwarded only to the
    pull stage; other stages ignore it.
    """
    started = _now_iso()
    try:
        if stage == "pull":
            pull_kwargs: dict[str, Any] = {"dry_run": dry_run}
            if max_companies_per_source is not None:
                pull_kwargs["max_companies_per_source"] = max_companies_per_source
            await scout.run_pull(client_id, **pull_kwargs)
        elif stage == "cheap_resolve":
            await scout.run_cheap_resolve(client_id, dry_run=dry_run)
        elif stage == "score_v1":
            await scout.run_score(client_id, dry_run=dry_run, phase="v1")
        elif stage == "screen":
            await scout.run_screen(client_id, dry_run=dry_run)
        elif stage == "identity":
            await scout.run_identity(client_id, dry_run=dry_run)
        elif stage == "enrich":
            await scout.run_enrich(client_id, dry_run=dry_run)
        elif stage == "score_v2":
            await scout.run_score(client_id, dry_run=dry_run, phase="v2")
        elif stage == "compose":
            if composer_backend is None:
                raise RuntimeError(
                    "compose stage requires composer_backend; "
                    "pass it to run_client_cycle"
                )
            contacts = await composer_backend.fetch_eligible_contacts(client_id)
            if not contacts:
                logger.info(
                    "compose stage: no eligible contacts client=%s", client_id,
                )
            else:
                await scout.run_compose(client_id, contacts, dry_run=dry_run)
        else:
            raise ValueError(f"unknown stage: {stage}")
    except Exception as exc:
        logger.exception(
            "client cycle stage failed client=%s stage=%s", client_id, stage,
        )
        return StageRun(
            stage=stage,
            ok=False,
            started_at=started,
            completed_at=_now_iso(),
            error_type=type(exc).__name__,
            error_message=str(exc)[:500],
        )
    return StageRun(
        stage=stage,
        ok=True,
        started_at=started,
        completed_at=_now_iso(),
    )


async def run_client_cycle(
    scout: "ScoutSystem",
    client_id: str,
    *,
    dry_run: bool = False,
    stages: tuple[str, ...] | None = None,
    composer_backend: "ComposerStorageBackend | None" = None,
    max_companies_per_source: int | None = None,
) -> ClientCycleResult:
    """Run the nightly pipeline for one client.

    Degraded-mode semantics: every stage gets its turn even if predecessors
    failed. This lets an operator see ALL the problems in one cycle rather
    than one-at-a-time across nights. A completely unreachable backend will
    still surface cleanly (every stage errors the same way).

    ``stages`` lets callers restrict to a subset — used by
    ``scripts/run_daemon_once.py`` for targeted debugging.

    ``composer_backend`` is required iff the ``compose`` stage is selected.
    Threaded through explicitly (rather than fished out of the ScoutSystem)
    so stage handlers stay independent of Scout's construction details.

    ``max_companies_per_source`` (when set) caps the per-adapter pull
    batch size. None = orchestrator's own default applies. Useful for
    debug runs and cost-bounded smoke tests.
    """
    selected = stages if stages is not None else STAGE_ORDER
    # Validate up-front so a typo surfaces before any work happens.
    unknown = [s for s in selected if s not in STAGE_ORDER]
    if unknown:
        raise ValueError(f"unknown stage(s): {unknown} (valid: {list(STAGE_ORDER)})")

    started = _now_iso()
    logger.info(
        "client cycle start client=%s dry_run=%s stages=%s max_per_source=%s",
        client_id, dry_run, list(selected), max_companies_per_source,
    )

    result = ClientCycleResult(
        client_id=client_id,
        started_at=started,
        completed_at=started,  # overwritten at end
    )
    for stage in selected:
        run = await _run_one_stage(
            scout, stage, client_id,
            dry_run=dry_run, composer_backend=composer_backend,
            max_companies_per_source=max_companies_per_source,
        )
        result.stages_run.append(run)
        if not run.ok:
            result.errors.append({
                "stage": run.stage,
                "error_type": run.error_type,
                "error_message": run.error_message,
            })

    result.completed_at = _now_iso()
    logger.info(
        "client cycle end client=%s ok=%s errors=%d stages=%d",
        client_id, result.ok, len(result.errors), len(result.stages_run),
    )
    return result
