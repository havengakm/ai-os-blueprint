import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_middleware(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "the-secret")

    from config.settings import get_settings
    get_settings.cache_clear()

    from api.middleware.verify_signatures import require_cron_secret

    app = FastAPI()

    @app.post("/protected", dependencies=[require_cron_secret()])
    async def protected():
        return {"ok": True}

    return app


def test_rejects_missing_secret(app_with_middleware):
    client = TestClient(app_with_middleware)
    r = client.post("/protected")
    assert r.status_code == 401


def test_rejects_wrong_secret(app_with_middleware):
    client = TestClient(app_with_middleware)
    r = client.post("/protected", headers={"X-Cron-Secret": "wrong"})
    assert r.status_code == 401


def test_accepts_correct_secret(app_with_middleware):
    client = TestClient(app_with_middleware)
    r = client.post("/protected", headers={"X-Cron-Secret": "the-secret"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@pytest.fixture
def app_with_empty_cron_secret(monkeypatch):
    """Daemon-only deployment shape (Plan 1.5 Task 1.5.4): CRON_SECRET unset."""
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    # CRON_SECRET deliberately unset; the autouse env-isolation fixture
    # already delenv'd every Settings field, so cron_secret defaults to "".

    from config.settings import get_settings
    get_settings.cache_clear()

    from api.middleware.verify_signatures import require_cron_secret

    app = FastAPI()

    @app.post("/protected", dependencies=[require_cron_secret()])
    async def protected():
        return {"ok": True}

    return app


def test_rejects_all_requests_when_cron_secret_empty(app_with_empty_cron_secret):
    """When cron_secret defaults to '' (daemon-only deployment), the HTTP
    cron-trigger endpoint must reject every request, even ones bearing an
    empty header. Locks down the security surface introduced by making
    cron_secret optional."""
    client = TestClient(app_with_empty_cron_secret)

    # No header.
    assert client.post("/protected").status_code == 401
    # Empty header.
    assert client.post(
        "/protected", headers={"X-Cron-Secret": ""}
    ).status_code == 401
    # Anything-non-empty header.
    assert client.post(
        "/protected", headers={"X-Cron-Secret": "anything"}
    ).status_code == 401
