import os
import pytest
from pydantic import ValidationError


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test-client")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("CRON_SECRET", "test-cron")

    from config.settings import get_settings
    get_settings.cache_clear()  # reset lru_cache
    s = get_settings()

    assert s.client_id == "test-client"
    assert s.supabase_url == "https://test.supabase.co"
    assert s.anthropic_api_key == "test-anthropic"
    assert s.environment == "development"  # default


def test_settings_missing_required_raises(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from config.settings import get_settings
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()


def test_settings_lead_stack_keys_default_empty(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test-client")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("CRON_SECRET", "test-cron")

    from config.settings import get_settings
    get_settings.cache_clear()
    s = get_settings()

    assert s.lusha_api_key == ""
    assert s.hunter_api_key == ""
    assert s.cognism_api_key == ""


def test_settings_lead_stack_keys_override(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test-client")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.setenv("LUSHA_API_KEY", "l-key")

    from config.settings import get_settings
    get_settings.cache_clear()
    s = get_settings()

    assert s.lusha_api_key == "l-key"
