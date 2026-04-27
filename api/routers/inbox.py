"""Operator inbox router — escalation queue triage endpoints.

Plan 2 Phase 3 Task 2.3.3. Endpoints:

  GET  /api/inbox/escalations?client_id=...   list open escalations
  POST /api/inbox/escalations/{id}/resolve    mark resolved
  POST /api/inbox/escalations/{id}/dismiss    mark dismissed (no action)

All endpoints are gated by ``cron_secret_dep`` for v1 — the operator
uses the same shared secret as the cron triggers. The Next.js web app
side will swap to per-user auth in a later plan.

DI: ``get_escalation_runtime`` is the production wiring target. Tests
override it with a fake-backed runtime via
``app.dependency_overrides``. The default ``RuntimeError`` keeps
unwired deployments fail-loud.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.middleware.verify_signatures import cron_secret_dep
from systems.beacon.reply.escalation import EscalationRuntime


router = APIRouter(prefix="/api/inbox", tags=["inbox"])


def get_escalation_runtime() -> EscalationRuntime:
    raise RuntimeError(
        "EscalationRuntime not configured. Wire api.deps.get_escalation_runtime "
        "via app.dependency_overrides[get_escalation_runtime] before serving "
        "traffic."
    )


# --------------------------------------------------------------------------- #
# Request / response models                                                   #
# --------------------------------------------------------------------------- #


class ResolveRequest(BaseModel):
    resolved_by: str


class DismissRequest(BaseModel):
    dismissed_by: str


# --------------------------------------------------------------------------- #
# Endpoints                                                                   #
# --------------------------------------------------------------------------- #


@router.get("/escalations", dependencies=[cron_secret_dep()])
async def list_open(
    client_id: str,
    runtime: EscalationRuntime = Depends(get_escalation_runtime),
):
    rows = await runtime.list_open(client_id)
    return {"count": len(rows), "escalations": rows}


@router.post(
    "/escalations/{escalation_id}/resolve",
    dependencies=[cron_secret_dep()],
)
async def resolve(
    escalation_id: str,
    body: ResolveRequest,
    runtime: EscalationRuntime = Depends(get_escalation_runtime),
):
    await runtime.resolve(escalation_id, resolved_by=body.resolved_by)
    return {"escalation_id": escalation_id, "status": "resolved"}


@router.post(
    "/escalations/{escalation_id}/dismiss",
    dependencies=[cron_secret_dep()],
)
async def dismiss(
    escalation_id: str,
    body: DismissRequest,
    runtime: EscalationRuntime = Depends(get_escalation_runtime),
):
    await runtime.dismiss(escalation_id, dismissed_by=body.dismissed_by)
    return {"escalation_id": escalation_id, "status": "dismissed"}
