"""Pipeline trigger endpoint (stub — real dispatch wires in Tasks 9/10/12/14)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from api.middleware.verify_signatures import require_cron_secret

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


class TriggerRequest(BaseModel):
    stage: Literal["pull", "score", "screen", "enrich", "research", "render", "full"]
    dry_run: bool = False
    limit: int | None = None


@router.post("/trigger", dependencies=[require_cron_secret()])
async def trigger(req: TriggerRequest):
    # Stub — real dispatch wires in with the pipeline stages in Tasks 9/10/12/14
    return {
        "stage": req.stage,
        "dry_run": req.dry_run,
        "limit": req.limit,
        "status": "accepted",
    }
