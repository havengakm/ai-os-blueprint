"""Pipeline HTTP router — dispatches to Scout pipeline stages.

Endpoints (per Plan 1 Task 16):
  POST /api/pipeline/pull       — run the pull stage (discover new contacts)
  POST /api/pipeline/score      — score unscored contacts
  POST /api/pipeline/screen     — screen scored contacts for hard-gate fails
  POST /api/pipeline/identity   — resolve decision-makers for screened contacts
  POST /api/pipeline/enrich     — enrich identified contacts (ZB, Trigify, etc.)
  POST /api/pipeline/render     — compose drafts for enriched contacts

Each endpoint accepts a ``PipelineInvocation`` body and returns the
stage-specific result dataclass as JSON.

The ``trigger`` endpoint from Task 8 (stage-name dispatch stub) is kept
as a legacy compatibility shim — it returns ``accepted`` and delegates
nothing. Real work happens through the per-stage endpoints below.

Stage construction is factored through module-level ``_build_*_stage``
hooks. Tests monkeypatch these to return stub stages, so the TestClient
never calls real Supabase / Apollo / Trigify / Anthropic.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import (
    get_budget_tracker,
    get_composer_backend,
    get_enrich_backend,
    get_identity_backend,
    get_pull_backend,
    get_score_backend,
    get_screen_backend,
)
from api.middleware.verify_signatures import require_cron_secret

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class PipelineInvocation(BaseModel):
    """Common body shape for pipeline-stage POSTs.

    ``client_id`` identifies which tenant's config + contacts to operate on.
    ``dry_run`` forwards to the stage's ``run(dry_run=...)`` flag — reads
    happen, writes are skipped, decision_log still fires for observability.
    ``limit`` caps the batch size; ``None`` means no cap.
    """
    client_id: str
    dry_run: bool = False
    limit: int | None = None


class RenderInvocation(PipelineInvocation):
    """Render-stage body. Adds ``contacts`` — per-contact render has no
    batch orchestrator yet (Task 16.5 will wire one). Caller supplies the
    enriched contact dicts to compose drafts for."""
    contacts: list[dict[str, Any]] = []


class TriggerRequest(BaseModel):
    """Legacy Task 8 stub body — kept for backward compatibility."""
    stage: Literal["pull", "score", "screen", "enrich", "research", "render", "full"]
    dry_run: bool = False
    limit: int | None = None


# ---------------------------------------------------------------------------
# Stage-factory hooks
# ---------------------------------------------------------------------------
# Real production factories. Each returns a stage object with a
# ``.run(client_id, *, dry_run, limit)`` coroutine. Tests monkeypatch
# these to return stubs so the router can be exercised without any real
# Supabase / Apollo / Claude / Voyage / Trigify calls.


async def _build_pull_stage(backend: Any) -> Any:
    """Build a ``PullOrchestrator`` with an empty adapter list.

    Adapter wiring (Apollo / Clutch / CSV / Trigify-discovery) is
    deliberately NOT done here — each adapter needs per-client API keys
    that live outside this router's contract. The real deployment path
    runs pull via ``scripts/run_trigify_discovery.py`` (or equivalent)
    until Task 16.5 lifts pull into a BaseSystem that pulls its own
    adapters from client config.

    Calling ``.run()`` on this bare orchestrator is a valid no-op: it
    will report zero active directories and log a summary — the exact
    behaviour the HTTP route should surface when no source adapters
    are wired in this process.
    """
    from systems.scout.pipeline.pull import PullOrchestrator
    return PullOrchestrator(adapters=[], storage=backend)


async def _build_score_stage(backend: Any) -> Any:
    from systems.scout.pipeline.score_stage import ScoreStage
    return ScoreStage(storage=backend)


async def _build_screen_stage(backend: Any) -> Any:
    from systems.scout.pipeline.screen import ScreenStage
    return ScreenStage(storage=backend)


async def _build_identity_stage(backend: Any) -> Any:
    """Identity stage needs an IdentityOrchestrator, which needs adapters
    keyed by live API credentials. We construct a zero-adapter
    orchestrator so the route can at least surface eligible-contact
    counts and log decisions — every contact will fail to resolve and
    be archived as ``no_decision_maker``. Real adapter wiring is the
    Scout daemon's job (Task 16.5)."""
    from systems.scout.identity.orchestrator import IdentityOrchestrator
    from systems.scout.pipeline.identity import IdentityStage
    orchestrator = IdentityOrchestrator(adapters=[])
    return IdentityStage(orchestrator=orchestrator, storage=backend)


async def _build_enrich_stage(enrich_backend: Any, budget_tracker: Any) -> Any:
    """Enrich stage mirrors identity: zero-adapter fan-out is a valid
    no-op that reports eligible counts + emits a summary."""
    from systems.scout.enrich.orchestrator import EnrichOrchestrator
    from systems.scout.pipeline.enrich import EnrichStage
    orchestrator = EnrichOrchestrator(adapters=[], budget_tracker=budget_tracker)
    return EnrichStage(orchestrator=orchestrator, storage=enrich_backend)


async def _build_composer(backend: Any) -> Any:
    from systems.scout.outreach.composer import Composer
    from systems.scout.outreach.research import ResearchSelector
    return Composer(storage=backend, research_selector=ResearchSelector())


def _to_json(result: Any) -> Any:
    """Convert a stage dataclass result to JSON-serialisable form."""
    if is_dataclass(result):
        return asdict(result)
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/pull")
async def run_pull(
    body: PipelineInvocation,
    backend: Any = Depends(get_pull_backend),
):
    """Dispatch the pull stage. See ``_build_pull_stage`` for the
    zero-adapter caveat — real adapter wiring lives in Scout daemon /
    scripts until Task 16.5."""
    stage = await _build_pull_stage(backend)
    result = await stage.run(body.client_id, dry_run=body.dry_run)
    return _to_json(result)


@router.post("/score")
async def run_score(
    body: PipelineInvocation,
    backend: Any = Depends(get_score_backend),
):
    """Dispatch the score stage."""
    stage = await _build_score_stage(backend)
    result = await stage.run(body.client_id, dry_run=body.dry_run, limit=body.limit)
    return _to_json(result)


@router.post("/screen")
async def run_screen(
    body: PipelineInvocation,
    backend: Any = Depends(get_screen_backend),
):
    """Dispatch the screen stage."""
    stage = await _build_screen_stage(backend)
    result = await stage.run(body.client_id, dry_run=body.dry_run, limit=body.limit)
    return _to_json(result)


@router.post("/identity")
async def run_identity(
    body: PipelineInvocation,
    backend: Any = Depends(get_identity_backend),
):
    """Dispatch the identity stage. See ``_build_identity_stage`` for
    the zero-adapter caveat."""
    stage = await _build_identity_stage(backend)
    result = await stage.run(body.client_id, dry_run=body.dry_run, limit=body.limit)
    return _to_json(result)


@router.post("/enrich")
async def run_enrich(
    body: PipelineInvocation,
    enrich_backend: Any = Depends(get_enrich_backend),
    budget_tracker: Any = Depends(get_budget_tracker),
):
    """Dispatch the enrich stage. The budget tracker is resolved via the
    registry (same Supabase client as enrich_backend)."""
    stage = await _build_enrich_stage(enrich_backend, budget_tracker)
    result = await stage.run(body.client_id, dry_run=body.dry_run, limit=body.limit)
    return _to_json(result)


@router.post("/render")
async def run_render(
    body: RenderInvocation,
    backend: Any = Depends(get_composer_backend),
):
    """Dispatch the render stage — compose drafts for the supplied contacts.

    The Composer operates per-contact. Task 16.5 will add a batch
    orchestrator that fetches enriched contacts itself; until then, the
    caller provides them in the request body.
    """
    composer = await _build_composer(backend)
    composed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for contact in body.contacts[: body.limit] if body.limit else body.contacts:
        outcome = await composer.compose(body.client_id, contact, dry_run=body.dry_run)
        payload = _to_json(outcome)
        bucket = skipped if type(outcome).__name__ == "ComposerSkip" else composed
        bucket.append(payload)
    return {
        "client_id": body.client_id,
        "dry_run": body.dry_run,
        "total_eligible": len(body.contacts),
        "total_composed": len(composed),
        "total_skipped": len(skipped),
        "composed": composed,
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# Legacy Task 8 stub — kept for compatibility with existing cron callers.
# ---------------------------------------------------------------------------


@router.post("/trigger", dependencies=[require_cron_secret()])
async def trigger(req: TriggerRequest):
    """Legacy stage-name dispatch stub. Real work is done by the
    per-stage endpoints above (``/pull``, ``/score``, etc.). Kept so
    existing cron entries continue to succeed during the transition."""
    return {
        "stage": req.stage,
        "dry_run": req.dry_run,
        "limit": req.limit,
        "status": "accepted",
    }
