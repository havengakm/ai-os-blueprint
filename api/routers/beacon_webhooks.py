"""Beacon ESP webhook ingest router.

Plan 2 Phase 2 Task 2.2.4. Accepts signed webhook events from Instantly
v2 (and, in future, other providers — one router per provider keeps the
signature secret + path narrowly scoped).

Endpoints:
  POST /api/beacon/webhooks/instantly

Signature is verified via the ``verify_webhook_signature`` factory from
``api.middleware.verify_signatures`` against
``settings.instantly_webhook_secret``. Bad signature → 401.

Dispatch is delegated to ``WebhookHandler.handle(payload)`` which is
exhaustively unit-tested in ``tests/test_beacon/test_webhook_handler.py``.
The router stays a thin pass-through so this file does not need its own
business-logic tests beyond signature wiring + dispatch smoke.

Dependency injection: the handler instance is provided by
``get_webhook_handler``. Tests override that dep to inject a fake
backend + decision_logger; production wiring lives in
``api.deps.get_beacon_webhook_handler`` (added when the real Supabase
backend implementation lands).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api.middleware.verify_signatures import verify_webhook_signature
from systems.beacon.pipeline.webhook_handler import WebhookHandler


router = APIRouter(prefix="/api/beacon/webhooks", tags=["beacon-webhooks"])


def get_webhook_handler() -> WebhookHandler:
    """Default DI provider — production wiring overrides this with a real
    Supabase-backed handler. Until that lands, calling the unwrapped
    endpoint will fail loudly so the omission can't go unnoticed."""
    raise RuntimeError(
        "WebhookHandler not configured. Wire api.deps.get_beacon_webhook_handler "
        "via app.dependency_overrides[get_webhook_handler] before serving traffic."
    )


@router.post(
    "/instantly",
    dependencies=[verify_webhook_signature("instantly_webhook_secret")],
)
async def receive_instantly_event(
    request: Request,
    handler: WebhookHandler = Depends(get_webhook_handler),
):
    """Receive an Instantly v2 webhook event.

    Signature gate runs first (401 on bad sig). Then the JSON body is
    parsed + dispatched. Returns ``{"result": <verdict>}`` with HTTP 200
    for every well-formed request, including unknown event types — ESPs
    add new event names over time and the receiver must not 500 on
    them, otherwise the ESP retries cause noise."""
    payload = await request.json()
    result = await handler.handle(payload)
    return {"result": result.value}
