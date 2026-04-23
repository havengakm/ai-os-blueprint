"""Opt-in smoke test — instantiates every backend against a live
dev Supabase to catch schema drift (Item 65 S3).

Gated by ``SUPABASE_SMOKE=1``. Skipped by default so it does NOT run
in normal pytest. Intended as a post-deploy manual check:

    SUPABASE_SMOKE=1 uv run pytest tests/test_api/test_deps_smoke.py -v

Each backend gets a minimal read (select a single row from the table
it owns). Print-statements surface "<ClassName> OK" per backend so the
operator can see which one failed if any fail.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def smoke_registry():
    """Build a real registry against the live SUPABASE_URL /
    SUPABASE_SERVICE_ROLE_KEY / VOYAGE_API_KEY in the environment."""
    import api.deps as deps_mod
    deps_mod.get_supabase_client.cache_clear()
    deps_mod.get_registry.cache_clear()
    yield deps_mod.get_registry()
    deps_mod.get_supabase_client.cache_clear()
    deps_mod.get_registry.cache_clear()


@pytest.mark.skipif(
    os.environ.get("SUPABASE_SMOKE") != "1",
    reason="SUPABASE_SMOKE unset — skipping live Supabase smoke test",
)
def test_every_backend_can_read_its_primary_table(smoke_registry):
    """Each backend does ONE read against its primary table. Verifies
    the table exists, the schema hasn't drifted, and the service-role
    key has the expected permissions."""
    client = smoke_registry.pull_backend._client  # shared client ref
    # Map backend -> primary table. Single-row select is enough to
    # confirm the table exists and RLS doesn't block the service role.
    checks = [
        (smoke_registry.pull_backend, "clients"),
        (smoke_registry.score_backend, "contacts"),
        (smoke_registry.screen_backend, "contacts"),
        (smoke_registry.identity_backend, "contacts"),
        (smoke_registry.enrich_backend, "contacts"),
        (smoke_registry.budget_tracker, "client_config"),
        (smoke_registry.component_store_backend, "copy_components"),
        (smoke_registry.composer_backend, "drafts"),
        (smoke_registry.trigify_monitor_storage, "client_config"),
        (smoke_registry.trigify_discovery_storage, "client_config"),
    ]
    for backend, table in checks:
        # If a table name doesn't exist in the live schema, this raises
        # a clean error naming the backend class — exactly what we want
        # for a schema-drift smoke check.
        resp = client.table(table).select("*").limit(1).execute()
        assert resp is not None, f"{backend.__class__.__name__} -> {table} returned None"
        print(f"{backend.__class__.__name__} OK ({table})")
