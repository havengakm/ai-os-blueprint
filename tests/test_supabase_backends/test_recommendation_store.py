"""Tests for SupabaseRecommendationStore.

Conforms to ``systems.optimizer.recommendations.RecommendationStore``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from systems.optimizer.recommendations import RecommendationRow
from systems.optimizer.storage.recommendation_supabase_store import (
    SupabaseRecommendationStore,
)
from tests.test_supabase_backends.fakes import FakeSupabaseClient


def _now() -> datetime:
    return datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)


def _row(rid: str, *, status: str = "pending", created_at: datetime | None = None) -> RecommendationRow:
    return RecommendationRow(
        id=rid,
        client_id="c1",
        category="autonomy_promotion",
        payload={"target": "send_email"},
        reasoning="x",
        confidence=0.9,
        status=status,
        created_at=created_at or _now(),
    )


# --------------------------------------------------------------------------- #
# insert                                                                      #
# --------------------------------------------------------------------------- #


async def test_insert_persists_row():
    fake = FakeSupabaseClient()
    store = SupabaseRecommendationStore(fake)

    rec_id = await store.insert(_row("rec-1"))
    assert rec_id == "rec-1"

    rows = fake.rows("optimizer_recommendation")
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "rec-1"
    assert row["client_id"] == "c1"
    assert row["category"] == "autonomy_promotion"
    assert row["status"] == "pending"
    assert row["payload"]["target"] == "send_email"
    assert row["confidence"] == 0.9


# --------------------------------------------------------------------------- #
# get                                                                         #
# --------------------------------------------------------------------------- #


async def test_get_returns_row_when_present():
    fake = FakeSupabaseClient(
        tables={
            "optimizer_recommendation": [
                {
                    "id": "rec-1", "client_id": "c1",
                    "category": "autonomy_promotion",
                    "payload": {}, "reasoning": "x", "confidence": 0.9,
                    "status": "pending",
                    "created_at": _now().isoformat(),
                }
            ]
        }
    )
    store = SupabaseRecommendationStore(fake)
    row = await store.get("rec-1")
    assert row is not None
    assert row.id == "rec-1"
    assert row.status == "pending"


async def test_get_returns_none_when_absent():
    fake = FakeSupabaseClient()
    store = SupabaseRecommendationStore(fake)
    row = await store.get("rec-missing")
    assert row is None


# --------------------------------------------------------------------------- #
# update_status                                                               #
# --------------------------------------------------------------------------- #


async def test_update_status_transitions_to_approved_with_reviewed_fields():
    now = _now()
    fake = FakeSupabaseClient(
        tables={
            "optimizer_recommendation": [
                {
                    "id": "rec-1", "status": "pending",
                    "reviewed_by": None, "reviewed_at": None,
                }
            ]
        }
    )
    store = SupabaseRecommendationStore(fake)
    await store.update_status(
        "rec-1",
        status="approved",
        reviewed_by="op@x.com",
        reviewed_at=now,
    )
    row = fake.rows("optimizer_recommendation")[0]
    assert row["status"] == "approved"
    assert row["reviewed_by"] == "op@x.com"
    assert row["reviewed_at"] == now.isoformat()


async def test_update_status_to_expired_only_changes_status():
    fake = FakeSupabaseClient(
        tables={
            "optimizer_recommendation": [
                {"id": "rec-1", "status": "pending", "reviewed_by": None}
            ]
        }
    )
    store = SupabaseRecommendationStore(fake)
    await store.update_status("rec-1", status="expired")
    row = fake.rows("optimizer_recommendation")[0]
    assert row["status"] == "expired"
    # reviewed_by stays untouched on expiry — operator didn't act
    assert row["reviewed_by"] is None


# --------------------------------------------------------------------------- #
# list_pending                                                                #
# --------------------------------------------------------------------------- #


async def test_list_pending_filters_by_client_and_status():
    now = _now()
    fake = FakeSupabaseClient(
        tables={
            "optimizer_recommendation": [
                {
                    "id": "r1", "client_id": "c1", "status": "pending",
                    "category": "autonomy_promotion",
                    "payload": {}, "reasoning": "x", "confidence": 0.9,
                    "created_at": now.isoformat(),
                },
                {
                    "id": "r2", "client_id": "c1", "status": "approved",
                    "category": "autonomy_promotion",
                    "payload": {}, "reasoning": "x", "confidence": 0.9,
                    "created_at": now.isoformat(),
                },
                {
                    "id": "r3", "client_id": "c2", "status": "pending",
                    "category": "autonomy_promotion",
                    "payload": {}, "reasoning": "x", "confidence": 0.9,
                    "created_at": now.isoformat(),
                },
            ]
        }
    )
    store = SupabaseRecommendationStore(fake)
    rows = await store.list_pending("c1")
    assert [r.id for r in rows] == ["r1"]


# --------------------------------------------------------------------------- #
# list_pending_older_than                                                     #
# --------------------------------------------------------------------------- #


async def test_list_pending_older_than_filters_by_age():
    now = _now()
    old = now - timedelta(days=10)
    recent = now - timedelta(days=2)

    fake = FakeSupabaseClient(
        tables={
            "optimizer_recommendation": [
                {
                    "id": "r-old", "client_id": "c1", "status": "pending",
                    "category": "autonomy_promotion",
                    "payload": {}, "reasoning": "x", "confidence": 0.9,
                    "created_at": old.isoformat(),
                },
                {
                    "id": "r-recent", "client_id": "c1", "status": "pending",
                    "category": "autonomy_promotion",
                    "payload": {}, "reasoning": "x", "confidence": 0.9,
                    "created_at": recent.isoformat(),
                },
                {
                    "id": "r-old-but-approved", "client_id": "c1",
                    "status": "approved",
                    "category": "autonomy_promotion",
                    "payload": {}, "reasoning": "x", "confidence": 0.9,
                    "created_at": old.isoformat(),
                },
            ]
        }
    )
    store = SupabaseRecommendationStore(fake)
    cutoff = now - timedelta(days=7)
    stale = await store.list_pending_older_than(cutoff=cutoff)
    assert [r.id for r in stale] == ["r-old"]
