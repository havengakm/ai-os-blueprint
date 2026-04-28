"""Plan 2 Phase 5 Task 2.5.2: optimizer router smoke tests.

Operator-facing inbox endpoints for the recommendation queue:

  GET  /api/optimizer/recommendations?client_id=...
  POST /api/optimizer/recommendations/{id}/approve
  POST /api/optimizer/recommendations/{id}/reject

All cron_secret_dep-gated for v1 (same pattern as the inbox router).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from systems.optimizer.recommendations import RecommendationEngine, RecommendationRow


# --------------------------------------------------------------------------- #
# Fakes (same shape as the engine unit tests)                                 #
# --------------------------------------------------------------------------- #


class FakeStore:
    def __init__(self, seed=None) -> None:
        self.rows = list(seed or [])

    async def insert(self, row):
        self.rows.append(row)
        return row.id

    async def get(self, rec_id):
        for r in self.rows:
            if r.id == rec_id:
                return r
        return None

    async def update_status(self, rec_id, *, status, **kwargs):
        for r in self.rows:
            if r.id == rec_id:
                r.status = status
                if "reviewed_by" in kwargs:
                    r.reviewed_by = kwargs["reviewed_by"]
                if "reviewed_at" in kwargs:
                    r.reviewed_at = kwargs["reviewed_at"]
                return

    async def list_pending(self, client_id):
        return [r for r in self.rows if r.client_id == client_id and r.status == "pending"]

    async def list_pending_older_than(self, *, cutoff):
        return [r for r in self.rows if r.status == "pending" and r.created_at < cutoff]


class FakeDecisionLogger:
    async def emit(self, **kwargs):
        pass


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def app_with_optimizer(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "secret")

    from config.settings import get_settings

    get_settings.cache_clear()

    from api.main import create_app
    from api.routers import optimizer

    seed = [
        RecommendationRow(
            id="rec-1", client_id="c1",
            category="autonomy_promotion",
            payload={"target": "send_email"},
            reasoning="50+ acts at suggest with 85% success.",
            confidence=0.85,
            status="pending",
            created_at=datetime(2026, 4, 27, 0, 0, 0, tzinfo=timezone.utc),
        )
    ]
    store = FakeStore(seed=seed)
    engine = RecommendationEngine(
        store=store,
        decision_logger=FakeDecisionLogger(),
    )
    app = create_app()
    app.dependency_overrides[optimizer.get_recommendation_engine] = lambda: engine
    return app, store


# --------------------------------------------------------------------------- #
# GET                                                                         #
# --------------------------------------------------------------------------- #


def test_list_endpoint_returns_pending(app_with_optimizer):
    app, _ = app_with_optimizer
    client = TestClient(app)

    r = client.get(
        "/api/optimizer/recommendations",
        params={"client_id": "c1"},
        headers={"X-Cron-Secret": "secret"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    rec = body["recommendations"][0]
    assert rec["id"] == "rec-1"
    assert rec["category"] == "autonomy_promotion"
    assert rec["status"] == "pending"
    assert rec["confidence"] == 0.85


def test_list_endpoint_requires_cron_secret(app_with_optimizer):
    app, _ = app_with_optimizer
    client = TestClient(app)
    r = client.get("/api/optimizer/recommendations", params={"client_id": "c1"})
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# POST approve / reject                                                       #
# --------------------------------------------------------------------------- #


def test_approve_endpoint_transitions_status(app_with_optimizer):
    app, store = app_with_optimizer
    client = TestClient(app)

    r = client.post(
        "/api/optimizer/recommendations/rec-1/approve",
        json={"reviewed_by": "kirsten@aios.dev"},
        headers={"X-Cron-Secret": "secret"},
    )
    assert r.status_code == 200
    assert r.json() == {"recommendation_id": "rec-1", "status": "approved"}
    assert store.rows[0].status == "approved"
    assert store.rows[0].reviewed_by == "kirsten@aios.dev"


def test_reject_endpoint_transitions_status(app_with_optimizer):
    app, store = app_with_optimizer
    client = TestClient(app)

    r = client.post(
        "/api/optimizer/recommendations/rec-1/reject",
        json={"reviewed_by": "kirsten@aios.dev"},
        headers={"X-Cron-Secret": "secret"},
    )
    assert r.status_code == 200
    assert r.json() == {"recommendation_id": "rec-1", "status": "rejected"}
    assert store.rows[0].status == "rejected"


def test_approve_requires_reviewed_by(app_with_optimizer):
    app, _ = app_with_optimizer
    client = TestClient(app)
    r = client.post(
        "/api/optimizer/recommendations/rec-1/approve",
        json={},
        headers={"X-Cron-Secret": "secret"},
    )
    assert r.status_code == 422


def test_approve_unknown_id_returns_404(app_with_optimizer):
    app, _ = app_with_optimizer
    client = TestClient(app)
    r = client.post(
        "/api/optimizer/recommendations/rec-unknown/approve",
        json={"reviewed_by": "x@y.com"},
        headers={"X-Cron-Secret": "secret"},
    )
    assert r.status_code == 404


def test_approve_already_approved_returns_409(app_with_optimizer):
    app, store = app_with_optimizer
    store.rows[0].status = "approved"  # pre-flip
    client = TestClient(app)
    r = client.post(
        "/api/optimizer/recommendations/rec-1/approve",
        json={"reviewed_by": "x@y.com"},
        headers={"X-Cron-Secret": "secret"},
    )
    assert r.status_code == 409
