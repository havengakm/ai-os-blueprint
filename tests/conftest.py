import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app(monkeypatch):
    # Minimal env for settings to load
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")

    from config.settings import get_settings
    get_settings.cache_clear()

    from api.main import create_app
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)
