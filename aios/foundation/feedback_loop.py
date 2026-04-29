"""Feedback Loop — peer-to-peer learning channel for AI Employees.

Phase 1 of the structural rewrite (per docs/architecture/aios-structural-plan-2026-04-29.md).

Two operations close the loop between employees:

  - ``publish`` — an employee finishes a job and emits a learning_event so
    subscribers (other employees + the COO) can consume it on next run.
    Also writes the same content to the source employee's own memory.

  - ``record_outcome`` — a webhook or cron observes an outcome (reply,
    booking, ad click). Backfills decision_log.outcome AND emits a
    learning_event linking decision → outcome so PatternMatcher can
    serve "what worked last time" queries with real outcome data.

Per-deployment isolation: every operation requires ``client_id`` and
filters writes accordingly.

Dependencies (injected — keeps this testable):

  - ``decision_logger`` (DecisionLogger) — for record_outcome backfill
  - ``employee_memory`` (EmployeeMemory) — for the source-employee write
  - ``db`` (Supabase async client) — for direct learning_events inserts
  - ``embedder`` (optional callable) — for embedding learning_event content

Both ops are async + non-blocking from the writer's perspective. Failure
in any branch is logged but does not raise (we don't want a learning-loop
glitch to take down the writing employee).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from aios.foundation.decision_logger import DecisionLogger
from aios.foundation.employee_memory import EmployeeMemory


logger = logging.getLogger(__name__)


_VALID_LEARNING_KINDS = frozenset({
    "job_completion", "outcome", "synthesis", "observation",
})

_VALID_OUTCOMES = frozenset({"positive", "negative", "neutral"})


class FeedbackLoop:
    """Async event router. Writes learning_events + employee_memory rows
    + decision_log.outcome backfills. Per-deployment isolated."""

    def __init__(
        self,
        *,
        db: Any,
        decision_logger: DecisionLogger,
        employee_memory: EmployeeMemory,
        embedder: Callable[[str], Awaitable[list[float]]] | None = None,
    ) -> None:
        self._db = db
        self._decision_logger = decision_logger
        self._employee_memory = employee_memory
        self._embedder = embedder

    async def publish(
        self,
        *,
        client_id: str,
        source_employee_id: str,
        kind: str,
        content: str,
        decision_log_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Emit a learning_event AND write to source employee's memory.

        Returns the learning_event id on success, None on failure (failure
        is logged but never raised — keep the writing employee's run intact).
        """
        if kind not in _VALID_LEARNING_KINDS:
            logger.warning(
                "feedback_loop.publish: invalid kind=%r — dropping event", kind,
            )
            return None

        # 1) Write to source employee's own memory (so the employee can recall
        #    its own past completions for self-similarity queries).
        try:
            await self._employee_memory.remember(
                client_id=client_id,
                employee_id=source_employee_id,
                content=content,
                kind=kind if kind in {"job_completion", "observation", "synthesis"} else "learning",
                metadata=metadata,
            )
        except Exception:
            logger.exception(
                "feedback_loop.publish: employee_memory.remember failed "
                "client=%s source=%s kind=%s",
                client_id, source_employee_id, kind,
            )

        # 2) Emit a learning_event row (durable peer-to-peer channel).
        try:
            event_id = await self._insert_learning_event(
                client_id=client_id,
                source_employee_id=source_employee_id,
                kind=kind,
                content=content,
                decision_log_id=decision_log_id,
                metadata=metadata,
            )
            return event_id
        except Exception:
            logger.exception(
                "feedback_loop.publish: learning_events insert failed "
                "client=%s source=%s kind=%s",
                client_id, source_employee_id, kind,
            )
            return None

    async def record_outcome(
        self,
        *,
        client_id: str,
        decision_id: str,
        outcome: str,
        source_employee_id: str,
        outcome_data: dict[str, Any] | None = None,
    ) -> None:
        """Backfill decision_log.outcome AND emit an outcome learning_event.

        ``source_employee_id`` is the employee whose decision produced this
        outcome (so subscribed employees can route on the right source).
        Failures are logged but not raised.
        """
        if outcome not in _VALID_OUTCOMES:
            logger.warning(
                "feedback_loop.record_outcome: invalid outcome=%r — dropping",
                outcome,
            )
            return

        # 1) Backfill decision_log.outcome (was the missing link before
        #    this slice — the schema was ready, no caller existed).
        try:
            await self._decision_logger.record_outcome(
                decision_id=decision_id,
                outcome=outcome,
                outcome_data=outcome_data,
            )
        except Exception:
            logger.exception(
                "feedback_loop.record_outcome: decision_logger backfill failed "
                "client=%s decision=%s outcome=%s",
                client_id, decision_id[:8], outcome,
            )

        # 2) Emit a learning_event so subscribed employees see the outcome.
        outcome_summary = (
            f"Outcome={outcome} for decision {decision_id[:8]} "
            f"by {source_employee_id}"
        )
        if outcome_data:
            outcome_summary += f". Data: {json.dumps(outcome_data)[:300]}"

        try:
            await self._insert_learning_event(
                client_id=client_id,
                source_employee_id=source_employee_id,
                kind="outcome",
                content=outcome_summary,
                decision_log_id=decision_id,
                metadata={"outcome": outcome, "outcome_data": outcome_data or {}},
            )
        except Exception:
            logger.exception(
                "feedback_loop.record_outcome: learning_events insert failed "
                "client=%s decision=%s",
                client_id, decision_id[:8],
            )

    # ---------------------------------------------------------------- #
    # Internal                                                          #
    # ---------------------------------------------------------------- #

    async def _insert_learning_event(
        self,
        *,
        client_id: str,
        source_employee_id: str,
        kind: str,
        content: str,
        decision_log_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> str:
        """Insert a learning_events row, embedding the content if possible.
        Returns the row id. Raises on insert failure."""
        record: dict[str, Any] = {
            "client_id": client_id,
            "source_employee_id": source_employee_id,
            "kind": kind,
            "content": content,
            "metadata": json.dumps(metadata or {}),
        }
        if decision_log_id is not None:
            record["decision_log_id"] = decision_log_id

        if self._embedder is not None:
            try:
                vector = await self._embedder(content)
                record["embedding"] = vector
            except Exception:
                logger.exception(
                    "feedback_loop: embedder failed during learning_event insert"
                )

        resp = await self._db.table("learning_events").insert(record).execute()
        rows = resp.data or []
        if not rows:
            raise RuntimeError(
                f"learning_events insert returned no rows: client={client_id} source={source_employee_id}"
            )
        return rows[0]["id"]
