import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolate_env_from_dotenv(monkeypatch):
    """Plan 1.5 Task 1.5.3 (follow-ups-plan1.md item 3): prevent
    pydantic-settings from reading .env during tests.

    Without this fixture, tests that rely on ``monkeypatch.delenv(...)``
    + ``get_settings.cache_clear()`` silently pick up the operator's
    populated ``.env`` file in the worktree root, producing false
    passes (e.g. ``test_settings_missing_required_raises`` does NOT
    raise because pydantic-settings reads SUPABASE_URL etc. from
    .env regardless of monkeypatch).

    Strategy: override Settings.model_config['env_file'] = None for the
    duration of every test so pydantic-settings has no .env to read.
    Cache-clear before AND after so neither the test under cache nor
    the next-but-cached test pollutes each other.

    Workaround this replaces: ``mv .env .env.test-disabled`` before
    every test run.
    """
    from config.settings import Settings, get_settings
    get_settings.cache_clear()
    # 1. Block .env reading at the model level.
    new_config = {**Settings.model_config, "env_file": None}
    monkeypatch.setattr(Settings, "model_config", new_config)
    # 2. Clear any process-env values that direnv/shell may have injected
    #    from the operator's .env, so each test starts from a known-empty
    #    state and must opt-in to the vars it needs via monkeypatch.setenv.
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)
    yield
    get_settings.cache_clear()


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
