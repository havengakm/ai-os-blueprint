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

Phase 1 of structural rewrite (2026-04-29) — accepts an optional
embedder so similarity search via PatternMatcher.find_similar() covers
webhook + send_stage decisions, not just foundation-logged decisions.
Embedder failure is non-fatal — the row is still inserted without an
embedding.
"""
from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable
from uuid import uuid4

from systems.scout.supabase_backends._base import SupabaseLike


logger = logging.getLogger(__name__)


class SupabaseDecisionLogger:
    def __init__(
        self,
        client: SupabaseLike,
        embedder: Callable[[str], Awaitable[list[float]]] | None = None,
    ) -> None:
        self._client = client
        self._embedder = embedder

    async def _maybe_embed(
        self, decision_type: str, decision: str, context: dict
    ) -> list[float] | None:
        """Best-effort embedding of the decision context. None on failure."""
        if self._embedder is None:
            return None
        try:
            embed_text = (
                f"{decision_type}: {decision}. "
                f"Context: {json.dumps(context)[:500]}"
            )
            return await self._embedder(embed_text)
        except Exception:
            logger.exception(
                "SupabaseDecisionLogger: embedder failed (non-fatal)",
            )
            return None

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
        record: dict = {
            "id": new_id,
            "client_id": client_id,
            "decision_type": decision_type,
            "decision": decision,
            "reasoning": reasoning,
            "context": context,
            "source": source,
            "confidence": confidence,
        }
        embedding = await self._maybe_embed(decision_type, decision, context)
        if embedding is not None:
            record["embedding"] = embedding
        (
            self._client.table("decision_log")
            .insert(record)
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
        record: dict = {
            "id": str(uuid4()),
            "client_id": client_id,
            "decision_type": decision_type,
            "decision": decision,
            "context": context,
            "source": "beacon.webhook_handler",
        }
        embedding = await self._maybe_embed(decision_type, decision, context)
        if embedding is not None:
            record["embedding"] = embedding
        (
            self._client.table("decision_log")
            .insert(record)
            .execute()
        )
