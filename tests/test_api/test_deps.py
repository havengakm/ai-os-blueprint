"""Tests for ``api/deps.py`` — DI providers + singleton semantics.

Covers Item 65 S1 (single DI provider) + S2 (singleton not factory)
+ S4 (single-writer docstring presence).
"""
from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def deps_env(monkeypatch):
    """Stub every env var + supabase.create_client so deps.py is importable
    without real credentials. Clears both lru_caches between tests."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-voyage-key")

    # Fake Supabase client — we don't need a real one for DI semantics.
    fake_client = object()

    def fake_create_client(url, key):
        return fake_client

    # Patch create_client in both the supabase module (authoritative
    # source) and the api.deps module (already-imported binding).
    import api.deps as deps_mod
    import supabase
    monkeypatch.setattr(supabase, "create_client", fake_create_client)
    monkeypatch.setattr(deps_mod, "create_client", fake_create_client)

    # Clear caches so each test gets a fresh build.
    deps_mod.get_supabase_client.cache_clear()
    deps_mod.get_registry.cache_clear()

    yield deps_mod, fake_client

    deps_mod.get_supabase_client.cache_clear()
    deps_mod.get_registry.cache_clear()


# ---------------------------------------------------------------------------
# get_supabase_client
# ---------------------------------------------------------------------------


def test_get_supabase_client_returns_cached_instance(deps_env):
    deps_mod, fake_client = deps_env
    a = deps_mod.get_supabase_client()
    b = deps_mod.get_supabase_client()
    assert a is b
    assert a is fake_client


def test_get_supabase_client_missing_url_raises_clean_error(monkeypatch):
    import api.deps as deps_mod
    deps_mod.get_supabase_client.cache_clear()
    deps_mod.get_registry.cache_clear()
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "x")
    with pytest.raises(RuntimeError) as exc_info:
        deps_mod.get_supabase_client()
    msg = str(exc_info.value)
    assert "SUPABASE_URL" in msg
    assert "SUPABASE_SERVICE_ROLE_KEY" in msg
    deps_mod.get_supabase_client.cache_clear()


def test_get_supabase_client_missing_key_raises_clean_error(monkeypatch):
    import api.deps as deps_mod
    deps_mod.get_supabase_client.cache_clear()
    deps_mod.get_registry.cache_clear()
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        deps_mod.get_supabase_client()
    msg = str(exc_info.value)
    assert "SUPABASE_URL" in msg
    assert "SUPABASE_SERVICE_ROLE_KEY" in msg
    deps_mod.get_supabase_client.cache_clear()


# ---------------------------------------------------------------------------
# get_registry
# ---------------------------------------------------------------------------


def test_get_registry_builds_all_named_fields(deps_env):
    deps_mod, _ = deps_env
    registry = deps_mod.get_registry()
    expected = {
        "decision_logger",
        "knowledge_store",
        "memory_store",
        "pattern_matcher",
        "autonomy_gate",
        "embedder",
        # Phase 1 of structural rewrite (2026-04-29) — added.
        "employee_memory",
        "feedback_loop",
        "pull_backend",
        "cheap_resolve_backend",
        "score_backend",
        "screen_backend",
        "identity_backend",
        "enrich_backend",
        "budget_tracker",
        "component_store_backend",
        "composer_backend",
        "trigify_monitor_storage",
        "trigify_discovery_storage",
    }
    actual = {f.name for f in fields(registry)}
    assert actual == expected
    # Every field populated
    for name in expected:
        assert getattr(registry, name) is not None, name


def test_get_registry_returns_same_instance(deps_env):
    deps_mod, _ = deps_env
    a = deps_mod.get_registry()
    b = deps_mod.get_registry()
    assert a is b


def test_get_registry_missing_voyage_key_raises_clean_error(monkeypatch):
    import api.deps as deps_mod
    deps_mod.get_supabase_client.cache_clear()
    deps_mod.get_registry.cache_clear()
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "x")
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

    # Fake create_client so we don't hit the internet
    import supabase
    monkeypatch.setattr(supabase, "create_client", lambda u, k: object())
    monkeypatch.setattr(deps_mod, "create_client", lambda u, k: object())

    with pytest.raises(RuntimeError) as exc_info:
        deps_mod.get_registry()
    assert "VOYAGE_API_KEY" in str(exc_info.value)
    deps_mod.get_supabase_client.cache_clear()
    deps_mod.get_registry.cache_clear()


# ---------------------------------------------------------------------------
# Per-backend accessors
# ---------------------------------------------------------------------------


def test_get_pull_backend_delegates_to_registry(deps_env):
    deps_mod, _ = deps_env
    registry = deps_mod.get_registry()
    assert deps_mod.get_pull_backend() is registry.pull_backend


def test_all_accessors_delegate_to_registry(deps_env):
    """Every SystemRegistry field has a matching get_xxx() accessor that
    returns the registry instance."""
    deps_mod, _ = deps_env
    registry = deps_mod.get_registry()
    accessor_map = {
        "decision_logger": deps_mod.get_decision_logger,
        "knowledge_store": deps_mod.get_knowledge_store,
        "memory_store": deps_mod.get_memory_store,
        "pattern_matcher": deps_mod.get_pattern_matcher,
        "autonomy_gate": deps_mod.get_autonomy_gate,
        "embedder": deps_mod.get_embedder,
        # Phase 1 of structural rewrite (2026-04-29) — added.
        "employee_memory": deps_mod.get_employee_memory,
        "feedback_loop": deps_mod.get_feedback_loop,
        "pull_backend": deps_mod.get_pull_backend,
        "cheap_resolve_backend": deps_mod.get_cheap_resolve_backend,
        "score_backend": deps_mod.get_score_backend,
        "screen_backend": deps_mod.get_screen_backend,
        "identity_backend": deps_mod.get_identity_backend,
        "enrich_backend": deps_mod.get_enrich_backend,
        "budget_tracker": deps_mod.get_budget_tracker,
        "component_store_backend": deps_mod.get_component_store_backend,
        "composer_backend": deps_mod.get_composer_backend,
        "trigify_monitor_storage": deps_mod.get_trigify_monitor_storage,
        "trigify_discovery_storage": deps_mod.get_trigify_discovery_storage,
    }
    for field_name, accessor in accessor_map.items():
        expected = getattr(registry, field_name)
        assert accessor() is expected, field_name
    # Also: one accessor per field (no drift)
    assert set(accessor_map.keys()) == {f.name for f in fields(registry)}


# ---------------------------------------------------------------------------
# build_registry — direct invocation
# ---------------------------------------------------------------------------


def test_build_registry_direct_constructs_non_none_fields():
    """Exercise build_registry directly with a stub client — no env, no
    lru_cache involvement. Verifies construction does not silently skip
    any field."""
    from aios.dependency_container import build_registry
    fake_client = object()
    registry = build_registry(supabase_client=fake_client, voyage_api_key="stub")
    for f in fields(registry):
        assert getattr(registry, f.name) is not None, f.name


def test_build_registry_logs_info_on_success(caplog):
    """Log emission: build_registry logs 'SystemRegistry built' at INFO."""
    from aios.dependency_container import build_registry
    with caplog.at_level("INFO"):
        build_registry(supabase_client=object(), voyage_api_key="stub")
    assert any(
        "SystemRegistry built" in r.message and r.levelname == "INFO"
        for r in caplog.records
    )


# ---------------------------------------------------------------------------
# get_scout_system — singleton + unhashable-registry regression
# ---------------------------------------------------------------------------


def test_get_scout_system_returns_singleton_without_dependency_overrides(deps_env):
    """Regression: ``get_scout_system()`` called directly (NO
    ``app.dependency_overrides`` short-circuit) must return the same
    instance twice and must NOT raise ``TypeError: unhashable type``.

    Guards against a previous bug where ``_get_scout_system_cached`` was
    ``@lru_cache``d on a ``SystemRegistry`` argument — but ``SystemRegistry``
    is an unfrozen ``@dataclass`` (``__hash__ = None``), so the first real
    call would raise. Tests missed it because they hit the
    ``dependency_overrides`` path instead.
    """
    deps_mod, _ = deps_env
    # Reset the scout-system cache so the test starts clean.
    deps_mod._scout_system_singleton.cache_clear()

    a = deps_mod.get_scout_system()
    b = deps_mod.get_scout_system()
    assert a is b  # singleton

    deps_mod._scout_system_singleton.cache_clear()


# ---------------------------------------------------------------------------
# Single-writer documentation (Item 65 S4)
# ---------------------------------------------------------------------------


def test_single_writer_docstring_present_in_registry_and_deps():
    """The single-writer assumption for ``record_spend`` must be
    documented in both ``aios/foundation/registry.py`` and
    ``api/deps.py`` so a code-search lands on either file."""
    repo_root = Path(__file__).resolve().parents[2]
    registry_src = (repo_root / "aios" / "foundation" / "registry.py").read_text()
    deps_src = (repo_root / "api" / "deps.py").read_text()
    for src, label in ((registry_src, "registry.py"), (deps_src, "deps.py")):
        assert "Single-writer" in src or "single-writer" in src, label
        assert "record_spend" in src, label
        assert "Item 65" in src or "S4" in src, label
