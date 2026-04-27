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


def test_settings_env_vars_resolve_case_insensitive(monkeypatch):
    """``Settings.model_config`` sets ``case_sensitive=False`` so a
    lowercase env var (e.g. from a quirky shell config) resolves the
    same as the documented uppercase name. Lock that in against
    regression — operators sometimes set vars lowercase by accident,
    and a regression here would cause silent ValidationError on
    deploy.

    Plan 2 Task 2.0.3 (Plan 1 follow-up item 7)."""
    # Required fields use uppercase, the new SMARTLEAD_API_KEY is the
    # one we lowercase to verify the case-insensitive path.
    monkeypatch.setenv("CLIENT_ID", "test-client")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    # Lowercase-set field — should still be picked up by pydantic-settings.
    monkeypatch.setenv("smartlead_api_key", "lowercase-resolved")

    from config.settings import get_settings
    get_settings.cache_clear()
    s = get_settings()

    assert s.smartlead_api_key == "lowercase-resolved"


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


def test_settings_loads_without_cron_secret(monkeypatch):
    """Plan 1.5 Task 1.5.4 (follow-ups-plan1.md item 4): cron_secret is
    optional with empty default. Daemon-only deployments don't need it
    set; only the HTTP cron-trigger middleware reads it."""
    monkeypatch.setenv("CLIENT_ID", "test-client")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    # CRON_SECRET deliberately unset.

    from config.settings import get_settings
    get_settings.cache_clear()
    s = get_settings()  # must not raise ValidationError

    assert s.cron_secret == ""
