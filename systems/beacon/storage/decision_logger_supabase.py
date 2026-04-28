"""SupabaseDecisionLogger — Beacon's decision_log writer.

Implements two protocols simultaneously:

- ``systems.beacon.pipeline.send_stage.DecisionLogger`` via
  ``log_decision(client_id, *, decision_type, decision, reasoning,
  context, source, confidence) -> str``. SendStage emits these.

- ``systems.beacon.pipeline.webhook_handler.DecisionLogger`` via
  ``emit(*, client_id, decision_type, contact_id, payload) -> None``.
  WebhookHandler emits these.

Both write rows to the same ``decision_log`` table. The ``emit`` method
injects ``contact_id`` into the JSONB ``context`` so the per-contact
cost rollup query in
``SupabaseSendBackend.get_contact_total_cost_cents`` can find webhook
events by the same key as send attempts.
"""
from __future__ import annotations

from uuid import uuid4

from systems.scout.supabase_backends._base import SupabaseLike


class SupabaseDecisionLogger:
    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    # -- SendStage shape ---------------------------------------------------- #

    async def log_decision(
        self,
        client_id: str,
        *,
        decision_type: str,
        decision: str,
        reasoning: str,
        context: dict,
        source: str,
        confidence: float | None = None,
    ) -> str:
        new_id = str(uuid4())
        (
            self._client.table("decision_log")
            .insert(
                {
                    "id": new_id,
                    "client_id": client_id,
                    "decision_type": decision_type,
                    "decision": decision,
                    "reasoning": reasoning,
                    "context": context,
                    "source": source,
                    "confidence": confidence,
                }
            )
            .execute()
        )
        return new_id

    # -- WebhookHandler shape ----------------------------------------------- #

    async def emit(
        self,
        *,
        client_id: str,
        decision_type: str,
        contact_id: str,
        payload: dict,
    ) -> None:
        # Inject contact_id into context so cost-rollup queries that
        # filter on context.contact_id find webhook events too.
        context = {"contact_id": contact_id, **payload}
        decision = payload.get("event") or decision_type
        (
            self._client.table("decision_log")
            .insert(
                {
                    "id": str(uuid4()),
                    "client_id": client_id,
                    "decision_type": decision_type,
                    "decision": decision,
                    "context": context,
                    "source": "beacon.webhook_handler",
                }
            )
            .execute()
        )
