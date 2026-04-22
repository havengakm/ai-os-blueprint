"""Tests for ``api/routers/pipeline.py`` — per-stage endpoint dispatch.

Task 16.5 refactor: endpoints dispatch through ``ScoutSystem`` instead of
constructing stages directly. Tests override the
``get_scout_system`` dependency with a stub ScoutSystem and assert the
right ``run_<stage>`` method was called with the body params.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Legacy stub endpoint — kept from the original Task 8 test
# ---------------------------------------------------------------------------


def test_pipeline_trigger_requires_cron_secret(client):
    r = client.post("/api/pipeline/trigger")
    assert r.status_code == 401


def test_pipeline_trigger_accepts_valid_secret(client):
    r = client.post(
        "/api/pipeline/trigger",
        headers={"X-Cron-Secret": "test-cron"},
        json={"stage": "pull", "dry_run": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["stage"] == "pull"
    assert body["dry_run"] is True
    assert "status" in body


# ---------------------------------------------------------------------------
# Stub ScoutSystem — records per-method calls, returns a dataclass result
# ---------------------------------------------------------------------------


@dataclass
class _StubResult:
    client_id: str
    dry_run: bool = False
    limit_seen: int | None = None
    method: str = ""


class _StubScoutSystem:
    """Stub ScoutSystem with the 6 ``run_<stage>`` methods the router uses."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run_pull(self, client_id, *, dry_run=False, limit=None):
        self.calls.append({"method": "run_pull", "client_id": client_id,
                           "dry_run": dry_run, "limit": limit})
        return _StubResult(client_id=client_id, dry_run=dry_run, limit_seen=limit, method="run_pull")

    async def run_score(self, client_id, *, dry_run=False, limit=None, phase="v1"):
        self.calls.append({"method": "run_score", "client_id": client_id,
                           "dry_run": dry_run, "limit": limit, "phase": phase})
        return _StubResult(client_id=client_id, dry_run=dry_run, limit_seen=limit, method="run_score")

    async def run_screen(self, client_id, *, dry_run=False, limit=None):
        self.calls.append({"method": "run_screen", "client_id": client_id,
                           "dry_run": dry_run, "limit": limit})
        return _StubResult(client_id=client_id, dry_run=dry_run, limit_seen=limit, method="run_screen")

    async def run_identity(self, client_id, *, dry_run=False, limit=None):
        self.calls.append({"method": "run_identity", "client_id": client_id,
                           "dry_run": dry_run, "limit": limit})
        return _StubResult(client_id=client_id, dry_run=dry_run, limit_seen=limit, method="run_identity")

    async def run_enrich(self, client_id, *, dry_run=False, limit=None):
        self.calls.append({"method": "run_enrich", "client_id": client_id,
                           "dry_run": dry_run, "limit": limit})
        return _StubResult(client_id=client_id, dry_run=dry_run, limit_seen=limit, method="run_enrich")

    async def run_compose(self, client_id, contacts, *, dry_run=False):
        self.calls.append({"method": "run_compose", "client_id": client_id,
                           "contacts": list(contacts), "dry_run": dry_run})
        return {
            "client_id": client_id,
            "dry_run": dry_run,
            "total_eligible": len(contacts),
            "total_composed": len(contacts),
            "total_skipped": 0,
            "composed": [{"contact_id": c.get("contact_id", "")} for c in contacts],
            "skipped": [],
        }


# ---------------------------------------------------------------------------
# Fixtures — override the get_scout_system dependency with a stub
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_pipeline(app):
    """Override ``get_scout_system`` with a stub. Returns (stub, app)."""
    from api import deps as deps_mod

    stub = _StubScoutSystem()
    app.dependency_overrides[deps_mod.get_scout_system] = lambda: stub
    yield stub, app
    app.dependency_overrides.clear()


@pytest.fixture
def patched_client(patched_pipeline):
    stub, app = patched_pipeline
    from fastapi.testclient import TestClient
    return stub, TestClient(app)


# ---------------------------------------------------------------------------
# Per-stage endpoint smoke tests
# ---------------------------------------------------------------------------


def test_post_pull_dispatches_to_scout_run_pull(patched_client):
    stub, client = patched_client
    r = client.post("/api/pipeline/pull", json={"client_id": "c1", "dry_run": False})
    assert r.status_code == 200, r.text
    assert len(stub.calls) == 1
    assert stub.calls[0] == {
        "method": "run_pull", "client_id": "c1", "dry_run": False, "limit": None,
    }
    assert r.json()["method"] == "run_pull"


def test_post_score_dispatches_to_scout_run_score(patched_client):
    stub, client = patched_client
    r = client.post("/api/pipeline/score", json={"client_id": "c1", "limit": 7})
    assert r.status_code == 200, r.text
    call = stub.calls[0]
    assert call["method"] == "run_score"
    assert call["client_id"] == "c1"
    assert call["limit"] == 7
    assert call["dry_run"] is False


def test_post_screen_dispatches_to_scout_run_screen(patched_client):
    stub, client = patched_client
    r = client.post("/api/pipeline/screen", json={"client_id": "c1"})
    assert r.status_code == 200, r.text
    assert stub.calls[0] == {
        "method": "run_screen", "client_id": "c1", "dry_run": False, "limit": None,
    }


def test_post_identity_dispatches_to_scout_run_identity(patched_client):
    stub, client = patched_client
    r = client.post("/api/pipeline/identity", json={"client_id": "c1", "limit": 3})
    assert r.status_code == 200, r.text
    assert stub.calls[0] == {
        "method": "run_identity", "client_id": "c1", "dry_run": False, "limit": 3,
    }


def test_post_enrich_dispatches_to_scout_run_enrich(patched_client):
    stub, client = patched_client
    r = client.post("/api/pipeline/enrich", json={"client_id": "c1"})
    assert r.status_code == 200, r.text
    assert stub.calls[0] == {
        "method": "run_enrich", "client_id": "c1", "dry_run": False, "limit": None,
    }


def test_post_render_dispatches_to_scout_run_compose(patched_client):
    stub, client = patched_client
    r = client.post(
        "/api/pipeline/render",
        json={
            "client_id": "c1",
            "dry_run": True,
            "contacts": [{"contact_id": "X"}, {"contact_id": "Y"}],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_eligible"] == 2
    assert body["total_composed"] + body["total_skipped"] == 2
    # Compose called once with the full contacts list
    assert len(stub.calls) == 1
    call = stub.calls[0]
    assert call["method"] == "run_compose"
    assert call["dry_run"] is True
    assert len(call["contacts"]) == 2


def test_post_render_respects_limit_truncation(patched_client):
    stub, client = patched_client
    r = client.post(
        "/api/pipeline/render",
        json={
            "client_id": "c1",
            "limit": 1,
            "contacts": [{"contact_id": "X"}, {"contact_id": "Y"}],
        },
    )
    assert r.status_code == 200, r.text
    # The router truncates to limit before handing to scout.run_compose
    assert len(stub.calls[0]["contacts"]) == 1


# ---------------------------------------------------------------------------
# Validation + flag-forwarding
# ---------------------------------------------------------------------------


def test_missing_client_id_returns_422(patched_client):
    _stub, client = patched_client
    r = client.post("/api/pipeline/score", json={"dry_run": True})
    assert r.status_code == 422
    assert "client_id" in r.text


def test_dry_run_forwarded_to_scout(patched_client):
    stub, client = patched_client
    r = client.post("/api/pipeline/score", json={"client_id": "c1", "dry_run": True})
    assert r.status_code == 200, r.text
    assert stub.calls[0]["dry_run"] is True
