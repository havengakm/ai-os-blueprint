"""Optimizer recommendation engine — operator approval queue.

Plan 2 Phase 5 Task 2.5.2. The Optimizer's weekly review job (Task
2.5.1) produces recommendations; this engine handles persistence,
approve / reject operator verdicts, and 7-day auto-expiry of stale
pending rows.

Applicators (Task 2.5.3) plug in via a registry — for v1 the engine
records the operator's verdict + emits decision_log; the actual
underlying change runs when 2.5.3's applicator implementations land.

Categories (must match migration 022 CHECK constraint):
- bandit_weight_adjustment
- variant_retirement
- adapter_score_weight
- autonomy_promotion
- grader_calibration
- send_time_shift
- cool_off_threshold
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import uuid4

import structlog


log = structlog.get_logger(__name__)


DEFAULT_AUTO_EXPIRE_DAYS: int = 7


RECOMMENDATION_CATEGORIES: tuple[str, ...] = (
    "bandit_weight_adjustment",
    "variant_retirement",
    "adapter_score_weight",
    "autonomy_promotion",
    "grader_calibration",
    "send_time_shift",
    "cool_off_threshold",
)
_VALID_CATEGORIES = frozenset(RECOMMENDATION_CATEGORIES)


# --------------------------------------------------------------------------- #
# Row dataclass                                                               #
# --------------------------------------------------------------------------- #


@dataclass
class RecommendationRow:
    """In-memory + over-the-wire representation of one optimizer_recommendation
    row. Status transitions: pending → approved | rejected | expired."""

    id: str
    client_id: str
    category: str
    payload: dict
    reasoning: str
    confidence: float | None
    status: str
    created_at: datetime
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    applied_at: datetime | None = None
    apply_error: str | None = None


# --------------------------------------------------------------------------- #
# Protocols                                                                   #
# --------------------------------------------------------------------------- #


class RecommendationStore(Protocol):
    async def insert(self, row: RecommendationRow) -> str: ...

    async def get(self, rec_id: str) -> RecommendationRow | None: ...

    async def update_status(
        self,
        rec_id: str,
        *,
        status: str,
        reviewed_by: str | None = None,
        reviewed_at: datetime | None = None,
        applied_at: datetime | None = None,
        apply_error: str | None = None,
    ) -> None: ...

    async def list_pending(self, client_id: str) -> list[RecommendationRow]: ...

    async def list_pending_older_than(
        self, *, cutoff: datetime,
    ) -> list[RecommendationRow]: ...


class DecisionLogger(Protocol):
    async def emit(
        self,
        *,
        client_id: str,
        decision_type: str,
        contact_id: str,
        payload: dict,
    ) -> None: ...


# --------------------------------------------------------------------------- #
# Engine                                                                      #
# --------------------------------------------------------------------------- #


class RecommendationEngine:
    def __init__(
        self,
        *,
        store: RecommendationStore,
        decision_logger: DecisionLogger,
        auto_expire_days: int = DEFAULT_AUTO_EXPIRE_DAYS,
    ) -> None:
        self._store = store
        self._logger = decision_logger
        self._auto_expire_days = auto_expire_days

    # ----- create ---------------------------------------------------------- #

    async def create(
        self,
        *,
        client_id: str,
        category: str,
        payload: dict,
        reasoning: str,
        confidence: float | None = None,
    ) -> str:
        if category not in _VALID_CATEGORIES:
            raise ValueError(
                f"unknown recommendation category {category!r}; "
                f"must be one of {sorted(_VALID_CATEGORIES)}"
            )
        if confidence is not None and not (0.0 <= confidence <= 1.0):
            raise ValueError(
                f"confidence must be in [0, 1]; got {confidence}"
            )

        row = RecommendationRow(
            id=str(uuid4()),
            client_id=client_id,
            category=category,
            payload=payload,
            reasoning=reasoning,
            confidence=confidence,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        return await self._store.insert(row)

    # ----- approve / reject ----------------------------------------------- #

    async def approve(
        self,
        rec_id: str,
        *,
        reviewed_by: str,
        now: datetime | None = None,
    ) -> None:
        await self._verdict(
            rec_id,
            verdict="approved",
            reviewed_by=reviewed_by,
            now=now,
        )

    async def reject(
        self,
        rec_id: str,
        *,
        reviewed_by: str,
        now: datetime | None = None,
    ) -> None:
        await self._verdict(
            rec_id,
            verdict="rejected",
            reviewed_by=reviewed_by,
            now=now,
        )

    async def _verdict(
        self,
        rec_id: str,
        *,
        verdict: str,
        reviewed_by: str,
        now: datetime | None,
    ) -> None:
        row = await self._store.get(rec_id)
        if row is None:
            raise LookupError(f"no recommendation with id={rec_id!r}")
        if row.status != "pending":
            raise RuntimeError(
                f"recommendation {rec_id!r} already {row.status}; "
                f"cannot transition to {verdict}"
            )
        now = now or datetime.now(timezone.utc)

        await self._store.update_status(
            rec_id,
            status=verdict,
            reviewed_by=reviewed_by,
            reviewed_at=now,
        )
        await self._logger.emit(
            client_id=row.client_id,
            decision_type="system_config",
            contact_id="",  # recommendations are client-scoped, not contact-scoped
            payload={
                "recommendation_id": rec_id,
                "category": row.category,
                "verdict": verdict,
                "reviewed_by": reviewed_by,
                "confidence": row.confidence,
            },
        )

    # ----- list / expire --------------------------------------------------- #

    async def list_pending(self, client_id: str) -> list[RecommendationRow]:
        return await self._store.list_pending(client_id)

    async def expire_stale(
        self,
        *,
        now: datetime | None = None,
        threshold_days: int | None = None,
    ) -> int:
        now = now or datetime.now(timezone.utc)
        threshold = threshold_days or self._auto_expire_days
        cutoff = now - timedelta(days=threshold)

        stale = await self._store.list_pending_older_than(cutoff=cutoff)
        for row in stale:
            await self._store.update_status(row.id, status="expired")
            log.info(
                "optimizer.recommendation.expired",
                rec_id=row.id,
                client_id=row.client_id,
                category=row.category,
                age_days=(now - row.created_at).days,
            )
        return len(stale)
