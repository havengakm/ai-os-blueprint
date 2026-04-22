"""Tests for ``api/routers/pipeline.py`` — per-stage endpoint dispatch.

Every endpoint is exercised via FastAPI TestClient. Stage construction
is monkeypatched to return stub stages, so no real Supabase / Apollo /
Claude / Voyage / Trigify calls happen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

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
# Stub stages
# ---------------------------------------------------------------------------


@dataclass
class _StubResult:
    """Minimal dataclass result — stands in for every stage's result type."""

    client_id: str
    dry_run: bool = False
    limit_seen: int | None = None
    calls: list[str] = field(default_factory=list)


class _StubStage:
    """Stub stage with a ``.run(client_id, *, dry_run, limit)`` coroutine
    that records the args + returns a ``_StubResult`` dataclass."""

    def __init__(self, name: str):
        self.name = name
        self.last_call: dict | None = None

    async def run(self, client_id: str, *, dry_run: bool = False, limit: int | None = None):
        self.last_call = {"client_id": client_id, "dry_run": dry_run, "limit": limit}
        return _StubResult(
            client_id=client_id,
            dry_run=dry_run,
            limit_seen=limit,
            calls=[self.name],
        )


class _StubPullStage(_StubStage):
    """Pull stage signature has no ``limit`` kwarg — the orchestrator uses
    ``max_companies_per_source`` instead. Override run accordingly."""
    async def run(self, client_id: str, *, dry_run: bool = False, **_):
        self.last_call = {"client_id": client_id, "dry_run": dry_run}
        return _StubResult(client_id=client_id, dry_run=dry_run, calls=[self.name])


# ---------------------------------------------------------------------------
# Fixtures — patch stage factories + deps accessors
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_pipeline(monkeypatch, app):
    """Build the FastAPI app, then monkeypatch every stage factory to
    return a stub stage. Returns a dict of the stubs so tests can assert
    on what was called."""
    import api.routers.pipeline as router_mod

    stubs = {
        "pull": _StubPullStage("pull"),
        "score": _StubStage("score"),
        "screen": _StubStage("screen"),
        "identity": _StubStage("identity"),
        "enrich": _StubStage("enrich"),
    }

    async def fake_pull(backend):
        return stubs["pull"]

    async def fake_score(backend):
        return stubs["score"]

    async def fake_screen(backend):
        return stubs["screen"]

    async def fake_identity(backend):
        return stubs["identity"]

    async def fake_enrich(enrich_backend, budget_tracker):
        return stubs["enrich"]

    monkeypatch.setattr(router_mod, "_build_pull_stage", fake_pull)
    monkeypatch.setattr(router_mod, "_build_score_stage", fake_score)
    monkeypatch.setattr(router_mod, "_build_screen_stage", fake_screen)
    monkeypatch.setattr(router_mod, "_build_identity_stage", fake_identity)
    monkeypatch.setattr(router_mod, "_build_enrich_stage", fake_enrich)

    # Composer: the factory itself we stub, and swap the backend via deps override.
    class _FakeComposer:
        def __init__(self):
            self.calls = []

        async def compose(self, client_id, contact, *, dry_run=False):
            self.calls.append({"client_id": client_id, "contact": contact, "dry_run": dry_run})
            return _StubResult(client_id=client_id, dry_run=dry_run, calls=["compose"])

    fake_composer = _FakeComposer()

    async def fake_build_composer(backend):
        return fake_composer

    monkeypatch.setattr(router_mod, "_build_composer", fake_build_composer)
    stubs["composer"] = fake_composer

    # Override the per-backend DI deps so get_registry() (which reads real
    # env) is never called during router handling.
    from api import deps as deps_mod
    for accessor_name in (
        "get_pull_backend",
        "get_score_backend",
        "get_screen_backend",
        "get_identity_backend",
        "get_enrich_backend",
        "get_budget_tracker",
        "get_composer_backend",
    ):
        app.dependency_overrides[getattr(deps_mod, accessor_name)] = lambda: object()

    yield stubs, app
    app.dependency_overrides.clear()


@pytest.fixture
def patched_client(patched_pipeline):
    stubs, app = patched_pipeline
    from fastapi.testclient import TestClient
    return stubs, TestClient(app)


# ---------------------------------------------------------------------------
# Per-stage endpoint smoke tests
# ---------------------------------------------------------------------------


def test_post_pull_dispatches_to_pull_stage(patched_client):
    stubs, client = patched_client
    r = client.post("/api/pipeline/pull", json={"client_id": "c1", "dry_run": False})
    assert r.status_code == 200, r.text
    assert stubs["pull"].last_call == {"client_id": "c1", "dry_run": False}
    assert r.json()["calls"] == ["pull"]


def test_post_score_dispatches_to_score_stage(patched_client):
    stubs, client = patched_client
    r = client.post("/api/pipeline/score", json={"client_id": "c1", "limit": 7})
    assert r.status_code == 200, r.text
    assert stubs["score"].last_call == {"client_id": "c1", "dry_run": False, "limit": 7}


def test_post_screen_dispatches_to_screen_stage(patched_client):
    stubs, client = patched_client
    r = client.post("/api/pipeline/screen", json={"client_id": "c1"})
    assert r.status_code == 200, r.text
    assert stubs["screen"].last_call == {"client_id": "c1", "dry_run": False, "limit": None}


def test_post_identity_dispatches_to_identity_stage(patched_client):
    stubs, client = patched_client
    r = client.post("/api/pipeline/identity", json={"client_id": "c1", "limit": 3})
    assert r.status_code == 200, r.text
    assert stubs["identity"].last_call == {"client_id": "c1", "dry_run": False, "limit": 3}


def test_post_enrich_dispatches_to_enrich_stage(patched_client):
    stubs, client = patched_client
    r = client.post("/api/pipeline/enrich", json={"client_id": "c1"})
    assert r.status_code == 200, r.text
    assert stubs["enrich"].last_call == {"client_id": "c1", "dry_run": False, "limit": None}


def test_post_render_dispatches_to_composer(patched_client):
    stubs, client = patched_client
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
    # composer.compose() was called once per contact with dry_run=True
    assert len(stubs["composer"].calls) == 2
    assert all(c["dry_run"] is True for c in stubs["composer"].calls)


# ---------------------------------------------------------------------------
# Validation + flag-forwarding
# ---------------------------------------------------------------------------


def test_missing_client_id_returns_422(patched_client):
    _stubs, client = patched_client
    r = client.post("/api/pipeline/score", json={"dry_run": True})
    assert r.status_code == 422
    assert "client_id" in r.text


def test_dry_run_forwarded_to_stage(patched_client):
    stubs, client = patched_client
    r = client.post("/api/pipeline/score", json={"client_id": "c1", "dry_run": True})
    assert r.status_code == 200, r.text
    assert stubs["score"].last_call["dry_run"] is True
