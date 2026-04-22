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

Task 16.5 refactor
------------------
Endpoints now dispatch through ``ScoutSystem`` (via
``api.deps.get_scout_system``) rather than constructing stages per
request. ``ScoutSystem.run_<stage>`` wraps each inner orchestrator with
the mandatory foundation loop (load_foundation → check_autonomy →
find_similar_decisions → retrieve_knowledge[render only]) before
dispatching. Stage construction lives in ``ScoutSystem.from_registry``.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_scout_system
from api.middleware.verify_signatures import require_cron_secret
from systems.scout.skill import ScoutSystem

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
    """Render-stage body. Adds ``contacts`` — the composer is per-contact and
    has no batch fetcher yet. Caller supplies enriched contact dicts."""
    contacts: list[dict[str, Any]] = []


class TriggerRequest(BaseModel):
    """Legacy Task 8 stub body — kept for backward compatibility."""
    stage: Literal["pull", "score", "screen", "enrich", "research", "render", "full"]
    dry_run: bool = False
    limit: int | None = None


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
    scout: ScoutSystem = Depends(get_scout_system),
):
    """Dispatch the pull stage through ScoutSystem's foundation loop."""
    result = await scout.run_pull(body.client_id, dry_run=body.dry_run, limit=body.limit)
    return _to_json(result)


@router.post("/score")
async def run_score(
    body: PipelineInvocation,
    scout: ScoutSystem = Depends(get_scout_system),
):
    """Dispatch the score stage (phase defaults to v1 — pre-screen pass)."""
    result = await scout.run_score(body.client_id, dry_run=body.dry_run, limit=body.limit)
    return _to_json(result)


@router.post("/screen")
async def run_screen(
    body: PipelineInvocation,
    scout: ScoutSystem = Depends(get_scout_system),
):
    """Dispatch the screen stage."""
    result = await scout.run_screen(body.client_id, dry_run=body.dry_run, limit=body.limit)
    return _to_json(result)


@router.post("/identity")
async def run_identity(
    body: PipelineInvocation,
    scout: ScoutSystem = Depends(get_scout_system),
):
    """Dispatch the identity stage."""
    result = await scout.run_identity(body.client_id, dry_run=body.dry_run, limit=body.limit)
    return _to_json(result)


@router.post("/enrich")
async def run_enrich(
    body: PipelineInvocation,
    scout: ScoutSystem = Depends(get_scout_system),
):
    """Dispatch the enrich stage."""
    result = await scout.run_enrich(body.client_id, dry_run=body.dry_run, limit=body.limit)
    return _to_json(result)


@router.post("/render")
async def run_render(
    body: RenderInvocation,
    scout: ScoutSystem = Depends(get_scout_system),
):
    """Dispatch the render stage — compose drafts for the supplied contacts.

    Batching belongs to the caller: the Composer operates per-contact.
    Pass at most ``limit`` contacts (if supplied) through to compose.
    """
    contacts = body.contacts[: body.limit] if body.limit else body.contacts
    return await scout.run_compose(body.client_id, contacts, dry_run=body.dry_run)


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
