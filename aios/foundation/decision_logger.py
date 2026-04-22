"""
Decision Logger — The core learning engine.

Every significant decision gets logged with its context snapshot.
When outcomes arrive (email opened, reply received, meeting booked),
they get backfilled. Over time, the system learns which decisions
lead to good outcomes.

Usage:
    logger = DecisionLogger(db)

    # Log a decision
    decision_id = await logger.log_decision(
        client_id="kirsten-client-zero",
        decision_type="copy_variant",
        context={"avatar": "agency_founder", "signals": [...], "template": "touch_1"},
        decision="Used AIDA framework with Meow Mix case study icebreaker",
        reasoning="Signal-based: client has active ad campaigns. AIDA fits growth-mode.",
        source="system",
        confidence=0.82,
    )

    # Later, when outcome is known
    await logger.record_outcome(
        decision_id=decision_id,
        outcome="positive",
        outcome_data={"opened": True, "replied": True, "meeting_booked": True},
    )

    # Get success rate for a decision type
    stats = await logger.get_success_rate("kirsten-client-zero", "copy_variant")
    # Returns: {"total": 50, "positive": 35, "negative": 10, "neutral": 5, "rate": 0.70}
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


class DecisionLogger:
    """Logs decisions, records outcomes, and queries success rates."""

    def __init__(self, db, embedder=None):
        """
        Args:
            db: Supabase async client
            embedder: Optional callable(text) -> list[float] for embedding context
        """
        self.db = db
        self.embedder = embedder

    async def log_decision(
        self,
        client_id: str,
        decision_type: str,
        context: dict[str, Any],
        decision: str,
        reasoning: str | None = None,
        source: str = "system",
        confidence: float | None = None,
    ) -> str:
        """Log a decision and return its ID."""
        import json

        record = {
            "client_id": client_id,
            "decision_type": decision_type,
            "context": json.dumps(context) if isinstance(context, dict) else context,
            "decision": decision,
            "reasoning": reasoning,
            "source": source,
            "confidence": confidence,
        }

        # Optionally embed the context for future similarity search
        if self.embedder:
            try:
                embed_text = f"{decision_type}: {decision}. Context: {json.dumps(context)[:500]}"
                embedding = await self.embedder(embed_text)
                record["embedding"] = embedding
            except Exception as e:
                logger.warning("Failed to embed decision: %s", e)

        result = await self.db.table("decision_log").insert(record).execute()

        if result.data:
            decision_id = result.data[0]["id"]
            logger.info(
                "DECISION LOGGED [%s] %s: %s (confidence: %s)",
                decision_type, client_id, decision[:80], confidence,
            )
            return decision_id

        logger.warning("Failed to log decision: %s", result)
        return ""

    async def record_outcome(
        self,
        decision_id: str,
        outcome: str,
        outcome_data: dict[str, Any] | None = None,
    ) -> None:
        """Backfill the outcome for a previously logged decision."""
        update = {
            "outcome": outcome,
            "outcome_data": outcome_data or {},
            "outcome_at": datetime.now(timezone.utc).isoformat(),
        }

        await (
            self.db.table("decision_log")
            .update(update)
            .eq("id", decision_id)
            .execute()
        )

        logger.info("OUTCOME RECORDED [%s] %s", decision_id[:8], outcome)

    async def get_success_rate(
        self,
        client_id: str,
        decision_type: str,
        lookback_days: int = 90,
    ) -> dict[str, Any]:
        """Get success rate for a decision type over a lookback period."""
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()

        result = await (
            self.db.table("decision_log")
            .select("outcome")
            .eq("client_id", client_id)
            .eq("decision_type", decision_type)
            .gte("created_at", cutoff)
            .not_.is_("outcome", "null")
            .execute()
        )

        rows = result.data or []
        total = len(rows)
        positive = sum(1 for r in rows if r["outcome"] == "positive")
        negative = sum(1 for r in rows if r["outcome"] == "negative")
        neutral = sum(1 for r in rows if r["outcome"] == "neutral")

        return {
            "total": total,
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
            "rate": positive / max(total, 1),
        }

    async def get_pending_outcomes(
        self,
        client_id: str,
        max_age_days: int = 30,
    ) -> list[dict]:
        """Get decisions that still need outcome backfill."""
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()

        result = await (
            self.db.table("decision_log")
            .select("id, decision_type, decision, context, created_at")
            .eq("client_id", client_id)
            .is_("outcome", "null")
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .execute()
        )

        return result.data or []
