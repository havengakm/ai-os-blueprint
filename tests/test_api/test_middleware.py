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
