"""Optimizer recommendation queue router.

Plan 2 Phase 5 Task 2.5.2. Operator-facing endpoints for the recommendation
queue:

  GET  /api/optimizer/recommendations?client_id=<id>
  POST /api/optimizer/recommendations/{id}/approve
  POST /api/optimizer/recommendations/{id}/reject

All gated by ``cron_secret_dep`` for v1 (operator uses the shared cron
secret; per-user auth via the Next.js web app is a later plan).

DI: ``get_recommendation_engine`` is the production wiring target; the
default raises ``RuntimeError`` so unwired deployments fail loud.
Tests override via ``app.dependency_overrides``.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.middleware.verify_signatures import cron_secret_dep
from systems.optimizer.recommendations import RecommendationEngine, RecommendationRow


router = APIRouter(prefix="/api/optimizer", tags=["optimizer"])


def get_recommendation_engine() -> RecommendationEngine:
    raise RuntimeError(
        "RecommendationEngine not configured. Wire "
        "api.deps.get_optimizer_recommendation_engine via "
        "app.dependency_overrides[get_recommendation_engine] before "
        "serving traffic."
    )


# --------------------------------------------------------------------------- #
# Request / response models                                                   #
# --------------------------------------------------------------------------- #


class ReviewRequest(BaseModel):
    reviewed_by: str


def _serialise(row: RecommendationRow) -> dict:
    """asdict() with ISO-8601 timestamp coercion for JSON-friendliness."""
    out = asdict(row)
    for key in ("created_at", "reviewed_at", "applied_at"):
        v = out.get(key)
        if v is not None and hasattr(v, "isoformat"):
            out[key] = v.isoformat()
    return out


# --------------------------------------------------------------------------- #
# Endpoints                                                                   #
# --------------------------------------------------------------------------- #


@router.get("/recommendations", dependencies=[cron_secret_dep()])
async def list_recommendations(
    client_id: str,
    engine: RecommendationEngine = Depends(get_recommendation_engine),
):
    rows = await engine.list_pending(client_id)
    return {
        "count": len(rows),
        "recommendations": [_serialise(r) for r in rows],
    }


@router.post(
    "/recommendations/{rec_id}/approve",
    dependencies=[cron_secret_dep()],
)
async def approve(
    rec_id: str,
    body: ReviewRequest,
    engine: RecommendationEngine = Depends(get_recommendation_engine),
):
    try:
        await engine.approve(rec_id, reviewed_by=body.reviewed_by)
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"recommendation {rec_id!r} not found",
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return {"recommendation_id": rec_id, "status": "approved"}


@router.post(
    "/recommendations/{rec_id}/reject",
    dependencies=[cron_secret_dep()],
)
async def reject(
    rec_id: str,
    body: ReviewRequest,
    engine: RecommendationEngine = Depends(get_recommendation_engine),
):
    try:
        await engine.reject(rec_id, reviewed_by=body.reviewed_by)
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"recommendation {rec_id!r} not found",
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return {"recommendation_id": rec_id, "status": "rejected"}
