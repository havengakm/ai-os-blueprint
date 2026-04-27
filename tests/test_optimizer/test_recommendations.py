"""Plan 2 Phase 5 Task 2.5.2: RecommendationEngine tests.

The engine is the operator-facing entrypoint to the recommendation
queue. It emits recommendations (from the weekly review job) +
handles operator approve / reject / list. Applicators (Task 2.5.3)
plug in via a registry — for v1 the engine just records the
operator's verdict + emits decision_log; the actual underlying
change happens when 2.5.3 applicators land.

Auto-expire: pending recommendations older than 7 days transition
to ``status='expired'`` so the operator's queue stays current.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from systems.optimizer.recommendations import (
    RECOMMENDATION_CATEGORIES,
    RecommendationEngine,
    RecommendationRow,
    DEFAULT_AUTO_EXPIRE_DAYS,
)


# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #


class FakeStore:
    def __init__(self, seed: list[RecommendationRow] | None = None) -> None:
        self.rows: list[RecommendationRow] = list(seed or [])
        self.applied: list[str] = []

    async def insert(self, row: RecommendationRow) -> str:
        self.rows.append(row)
        return row.id

    async def get(self, rec_id: str) -> RecommendationRow | None:
        for r in self.rows:
            if r.id == rec_id:
                return r
        return None

    async def update_status(
        self,
        rec_id: str,
        *,
        status: str,
        reviewed_by: str | None = None,
        reviewed_at: datetime | None = None,
        applied_at: datetime | None = None,
        apply_error: str | None = None,
    ) -> None:
        for r in self.rows:
            if r.id == rec_id:
                r.status = status
                if reviewed_by is not None:
                    r.reviewed_by = reviewed_by
                if reviewed_at is not None:
                    r.reviewed_at = reviewed_at
                if applied_at is not None:
                    r.applied_at = applied_at
                if apply_error is not None:
                    r.apply_error = apply_error
                return

    async def list_pending(self, client_id: str) -> list[RecommendationRow]:
        return [r for r in self.rows if r.client_id == client_id and r.status == "pending"]

    async def list_pending_older_than(
        self, *, cutoff: datetime,
    ) -> list[RecommendationRow]:
        return [
            r for r in self.rows
            if r.status == "pending" and r.created_at < cutoff
        ]


class FakeDecisionLogger:
    def __init__(self) -> None:
        self.emits: list[dict] = []

    async def emit(self, **kwargs):
        self.emits.append(kwargs)


def _engine(*, store=None, logger=None):
    return RecommendationEngine(
        store=store or FakeStore(),
        decision_logger=logger or FakeDecisionLogger(),
    )


def _now() -> datetime:
    return datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Constants sanity                                                            #
# --------------------------------------------------------------------------- #


def test_default_auto_expire_is_7_days():
    """Per Plan 2 doc: pending recommendations expire after 7 days."""
    assert DEFAULT_AUTO_EXPIRE_DAYS == 7


def test_categories_match_migration_022_check_constraint():
    expected = {
        "bandit_weight_adjustment",
        "variant_retirement",
        "adapter_score_weight",
        "autonomy_promotion",
        "grader_calibration",
        "send_time_shift",
        "cool_off_threshold",
    }
    assert set(RECOMMENDATION_CATEGORIES) == expected


# --------------------------------------------------------------------------- #
# create()                                                                    #
# --------------------------------------------------------------------------- #


async def test_create_persists_pending_row():
    store = FakeStore()
    engine = _engine(store=store)

    rec_id = await engine.create(
        client_id="c1",
        category="bandit_weight_adjustment",
        payload={"variant_key": "icebreaker:tier1:v3", "delta": 0.1},
        reasoning="Tier 1 v3 has 12% reply rate vs 5% baseline.",
        confidence=0.85,
    )
    assert rec_id
    assert len(store.rows) == 1
    row = store.rows[0]
    assert row.client_id == "c1"
    assert row.category == "bandit_weight_adjustment"
    assert row.payload["variant_key"] == "icebreaker:tier1:v3"
    assert row.confidence == 0.85
    assert row.status == "pending"


async def test_create_with_invalid_category_raises():
    engine = _engine()
    with pytest.raises(ValueError) as exc:
        await engine.create(
            client_id="c1",
            category="not_a_category",
            payload={},
            reasoning="x",
        )
    assert "not_a_category" in str(exc.value)


async def test_create_with_invalid_confidence_raises():
    engine = _engine()
    with pytest.raises(ValueError) as exc:
        await engine.create(
            client_id="c1",
            category="autonomy_promotion",
            payload={},
            reasoning="x",
            confidence=1.5,
        )
    assert "confidence" in str(exc.value).lower()


# --------------------------------------------------------------------------- #
# approve() / reject()                                                        #
# --------------------------------------------------------------------------- #


async def test_approve_sets_status_and_reviewed_fields():
    seed = [
        RecommendationRow(
            id="rec-1",
            client_id="c1",
            category="autonomy_promotion",
            payload={},
            reasoning="x",
            confidence=0.9,
            status="pending",
            created_at=_now(),
        )
    ]
    store = FakeStore(seed=seed)
    engine = _engine(store=store)

    await engine.approve("rec-1", reviewed_by="kirsten@aios.dev", now=_now())

    row = store.rows[0]
    assert row.status == "approved"
    assert row.reviewed_by == "kirsten@aios.dev"
    assert row.reviewed_at == _now()


async def test_reject_sets_status_and_reviewed_fields():
    seed = [
        RecommendationRow(
            id="rec-1",
            client_id="c1",
            category="variant_retirement",
            payload={},
            reasoning="x",
            confidence=0.5,
            status="pending",
            created_at=_now(),
        )
    ]
    store = FakeStore(seed=seed)
    engine = _engine(store=store)

    await engine.reject("rec-1", reviewed_by="kirsten@aios.dev", now=_now())

    row = store.rows[0]
    assert row.status == "rejected"
    assert row.reviewed_by == "kirsten@aios.dev"


async def test_approve_emits_decision_log():
    seed = [
        RecommendationRow(
            id="rec-1",
            client_id="c1",
            category="autonomy_promotion",
            payload={"target": "send_email"},
            reasoning="x",
            confidence=0.9,
            status="pending",
            created_at=_now(),
        )
    ]
    logger = FakeDecisionLogger()
    engine = _engine(store=FakeStore(seed=seed), logger=logger)

    await engine.approve("rec-1", reviewed_by="op@x.com", now=_now())

    assert len(logger.emits) == 1
    emit = logger.emits[0]
    assert emit["decision_type"] == "system_config"
    assert emit["payload"]["recommendation_id"] == "rec-1"
    assert emit["payload"]["category"] == "autonomy_promotion"
    assert emit["payload"]["verdict"] == "approved"


async def test_approve_already_approved_raises():
    seed = [
        RecommendationRow(
            id="rec-1",
            client_id="c1",
            category="autonomy_promotion",
            payload={},
            reasoning="x",
            confidence=0.9,
            status="approved",  # already approved
            created_at=_now(),
        )
    ]
    engine = _engine(store=FakeStore(seed=seed))

    with pytest.raises(RuntimeError) as exc:
        await engine.approve("rec-1", reviewed_by="op@x.com", now=_now())
    assert "approved" in str(exc.value).lower()


async def test_approve_unknown_id_raises():
    engine = _engine()
    with pytest.raises(LookupError):
        await engine.approve("rec-unknown", reviewed_by="op@x.com", now=_now())


# --------------------------------------------------------------------------- #
# expire_stale()                                                              #
# --------------------------------------------------------------------------- #


async def test_expire_stale_transitions_old_pending_rows():
    now = _now()
    old = now - timedelta(days=8)
    recent = now - timedelta(days=2)

    seed = [
        RecommendationRow(
            id="rec-old", client_id="c1", category="autonomy_promotion",
            payload={}, reasoning="x", confidence=0.9, status="pending",
            created_at=old,
        ),
        RecommendationRow(
            id="rec-recent", client_id="c1", category="autonomy_promotion",
            payload={}, reasoning="x", confidence=0.9, status="pending",
            created_at=recent,
        ),
        RecommendationRow(
            id="rec-already-rejected", client_id="c1", category="autonomy_promotion",
            payload={}, reasoning="x", confidence=0.9, status="rejected",
            created_at=old,
        ),
    ]
    store = FakeStore(seed=seed)
    engine = _engine(store=store)

    expired_count = await engine.expire_stale(now=now)

    assert expired_count == 1
    statuses = {r.id: r.status for r in store.rows}
    assert statuses["rec-old"] == "expired"
    assert statuses["rec-recent"] == "pending"
    assert statuses["rec-already-rejected"] == "rejected"


async def test_expire_stale_uses_custom_threshold_days():
    now = _now()
    six_days_ago = now - timedelta(days=6)
    seed = [
        RecommendationRow(
            id="rec-1", client_id="c1", category="autonomy_promotion",
            payload={}, reasoning="x", confidence=0.9, status="pending",
            created_at=six_days_ago,
        ),
    ]
    store = FakeStore(seed=seed)
    engine = _engine(store=store)

    # Threshold 5 days → 6-day-old row expires.
    n = await engine.expire_stale(now=now, threshold_days=5)
    assert n == 1
    assert store.rows[0].status == "expired"


# --------------------------------------------------------------------------- #
# list_pending()                                                              #
# --------------------------------------------------------------------------- #


async def test_list_pending_returns_only_pending_for_client():
    now = _now()
    seed = [
        RecommendationRow(
            id="r1", client_id="c1", category="autonomy_promotion",
            payload={}, reasoning="x", confidence=0.9, status="pending",
            created_at=now,
        ),
        RecommendationRow(
            id="r2", client_id="c1", category="variant_retirement",
            payload={}, reasoning="y", confidence=0.7, status="approved",
            created_at=now,
        ),
        RecommendationRow(
            id="r3", client_id="c2", category="autonomy_promotion",
            payload={}, reasoning="z", confidence=0.5, status="pending",
            created_at=now,
        ),
    ]
    engine = _engine(store=FakeStore(seed=seed))

    rows = await engine.list_pending("c1")
    assert [r.id for r in rows] == ["r1"]
