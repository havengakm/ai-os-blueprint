"""Plan 2 Phase 3 Task 2.3.3: inbox router smoke tests.

The inbox router exposes operator-facing endpoints to triage the
escalation queue:

  GET  /api/inbox/escalations
  POST /api/inbox/escalations/{id}/resolve
  POST /api/inbox/escalations/{id}/dismiss

All endpoints are gated by ``cron_secret_dep`` for v1 (the operator
uses the same shared secret used for cron triggers; the Next.js web
app side will swap to per-user auth in a later plan).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from systems.beacon.reply.escalation import EscalationRuntime


# --------------------------------------------------------------------------- #
# Fakes (match the EscalationRuntime fakes in test_escalation.py)             #
# --------------------------------------------------------------------------- #


class FakeEscalationBackend:
    def __init__(self, seed: list[dict] | None = None) -> None:
        self.inserted: list[dict] = list(seed or [])
        self.resolved: list[dict] = []
        self.dismissed: list[dict] = []

    async def insert_escalation(self, **kwargs):
        eid = f"esc-{len(self.inserted) + 1}"
        self.inserted.append({"id": eid, **kwargs})
        return eid

    async def mark_resolved(self, escalation_id, *, resolved_by):
        self.resolved.append(
            {"escalation_id": escalation_id, "resolved_by": resolved_by}
        )

    async def mark_dismissed(self, escalation_id, *, dismissed_by):
        self.dismissed.append(
            {"escalation_id": escalation_id, "dismissed_by": dismissed_by}
        )

    async def list_open(self, client_id):
        return [r for r in self.inserted if r.get("client_id") == client_id]


class FakeDecisionLogger:
    async def emit(self, **kwargs):
        pass


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def app_with_inbox(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "secret")

    from config.settings import get_settings

    get_settings.cache_clear()

    from api.main import create_app
    from api.routers import inbox

    backend = FakeEscalationBackend(
        seed=[
            {
                "id": "esc-1", "client_id": "c1", "contact_id": "u1",
                "reply_id": None, "escalation_type": "manual_flag",
                "summary": "test escalation", "status": "open",
            }
        ]
    )
    runtime = EscalationRuntime(
        backend=backend,
        decision_logger=FakeDecisionLogger(),
        slack_notifier=None,
    )

    app = create_app()
    app.dependency_overrides[inbox.get_escalation_runtime] = lambda: runtime

    return app, backend


# --------------------------------------------------------------------------- #
# GET /escalations                                                            #
# --------------------------------------------------------------------------- #


def test_list_endpoint_returns_open_escalations(app_with_inbox):
    app, backend = app_with_inbox
    client = TestClient(app)

    r = client.get(
        "/api/inbox/escalations",
        params={"client_id": "c1"},
        headers={"X-Cron-Secret": "secret"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["escalations"][0]["id"] == "esc-1"


def test_list_endpoint_requires_cron_secret(app_with_inbox):
    app, _ = app_with_inbox
    client = TestClient(app)

    r = client.get("/api/inbox/escalations", params={"client_id": "c1"})
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# POST /resolve                                                               #
# --------------------------------------------------------------------------- #


def test_resolve_endpoint_marks_escalation_resolved(app_with_inbox):
    app, backend = app_with_inbox
    client = TestClient(app)

    r = client.post(
        "/api/inbox/escalations/esc-1/resolve",
        json={"resolved_by": "kirsten@aios.dev"},
        headers={"X-Cron-Secret": "secret"},
    )
    assert r.status_code == 200
    assert r.json() == {"escalation_id": "esc-1", "status": "resolved"}
    assert backend.resolved == [
        {"escalation_id": "esc-1", "resolved_by": "kirsten@aios.dev"}
    ]


def test_resolve_endpoint_requires_cron_secret(app_with_inbox):
    app, _ = app_with_inbox
    client = TestClient(app)

    r = client.post(
        "/api/inbox/escalations/esc-1/resolve",
        json={"resolved_by": "x@y.com"},
    )
    assert r.status_code == 401


def test_resolve_endpoint_validates_resolved_by_present(app_with_inbox):
    app, _ = app_with_inbox
    client = TestClient(app)

    r = client.post(
        "/api/inbox/escalations/esc-1/resolve",
        json={},
        headers={"X-Cron-Secret": "secret"},
    )
    # FastAPI returns 422 on missing required body field
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# POST /dismiss                                                               #
# --------------------------------------------------------------------------- #


def test_dismiss_endpoint_marks_escalation_dismissed(app_with_inbox):
    app, backend = app_with_inbox
    client = TestClient(app)

    r = client.post(
        "/api/inbox/escalations/esc-1/dismiss",
        json={"dismissed_by": "kirsten@aios.dev"},
        headers={"X-Cron-Secret": "secret"},
    )
    assert r.status_code == 200
    assert r.json() == {"escalation_id": "esc-1", "status": "dismissed"}
    assert backend.dismissed == [
        {"escalation_id": "esc-1", "dismissed_by": "kirsten@aios.dev"}
    ]
