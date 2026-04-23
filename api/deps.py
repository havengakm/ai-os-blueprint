"""FastAPI dependency providers for AIOS foundation + Supabase backends.

Every router in ``api/routers/`` uses ``Depends(get_xxx_backend)`` to
receive a process-wide singleton. The same ``SystemRegistry`` instance
is reused across requests — construction happens ONCE on the first
call; subsequent calls are lru_cache hits.

Single-writer note (Item 65 S4, Task 16b Step 1 review)
-------------------------------------------------------
``SupabaseBudgetTracker.record_spend`` assumes serialised writes to
``client_config.tier_spent_cents``. This process-singleton pattern
enforces it as long as every write goes through the API server OR the
Scout daemon — NOT both concurrently. If future deploys run them
side-by-side, switch ``record_spend`` to a Postgres advisory lock or a
version-column CAS. See ``aios/foundation/registry.py`` for the matching
note at the construction site.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

from supabase import create_client

from aios.foundation.registry import SystemRegistry, build_registry
from systems.scout.skill import ScoutSystem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Primary singletons
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_supabase_client() -> Any:
    """Service-role Supabase client (bypasses RLS).

    Reads ``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY`` from env.
    Cached process-wide — do NOT call with different env in the same
    process. Tests clear the cache via ``get_supabase_client.cache_clear()``.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    missing = [name for name, val in (
        ("SUPABASE_URL", url),
        ("SUPABASE_SERVICE_ROLE_KEY", key),
    ) if not val]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must both be set. "
            "Check .env or environment config."
        )
    return create_client(url, key)


@lru_cache(maxsize=1)
def get_registry() -> SystemRegistry:
    """Build the SystemRegistry ONCE per process.

    All backends share the same Supabase client (Item 65 S1).
    All foundation modules share the same embedder.
    """
    voyage_key = os.environ.get("VOYAGE_API_KEY")
    if not voyage_key:
        raise RuntimeError(
            "Missing required environment variable: VOYAGE_API_KEY. "
            "Required for the foundation embedder. "
            "Check .env or environment config."
        )
    return build_registry(
        supabase_client=get_supabase_client(),
        voyage_api_key=voyage_key,
    )


# ---------------------------------------------------------------------------
# Per-backend accessors (thin shims for FastAPI Depends())
# ---------------------------------------------------------------------------
# One accessor per SystemRegistry field. Routers call
# ``Depends(get_pull_backend)`` etc. so DI is declarative.


def get_decision_logger() -> Any:
    return get_registry().decision_logger


def get_knowledge_store() -> Any:
    return get_registry().knowledge_store


def get_memory_store() -> Any:
    return get_registry().memory_store


def get_pattern_matcher() -> Any:
    return get_registry().pattern_matcher


def get_autonomy_gate() -> Any:
    return get_registry().autonomy_gate


def get_embedder() -> Any:
    return get_registry().embedder


def get_pull_backend() -> Any:
    return get_registry().pull_backend


def get_score_backend() -> Any:
    return get_registry().score_backend


def get_screen_backend() -> Any:
    return get_registry().screen_backend


def get_identity_backend() -> Any:
    return get_registry().identity_backend


def get_enrich_backend() -> Any:
    return get_registry().enrich_backend


def get_budget_tracker() -> Any:
    """Budget tracker. See module docstring for the single-writer
    assumption on ``record_spend`` (Item 65 S4)."""
    return get_registry().budget_tracker


def get_component_store_backend() -> Any:
    return get_registry().component_store_backend


def get_composer_backend() -> Any:
    return get_registry().composer_backend


def get_trigify_monitor_storage() -> Any:
    return get_registry().trigify_monitor_storage


def get_trigify_discovery_storage() -> Any:
    return get_registry().trigify_discovery_storage


# ---------------------------------------------------------------------------
# System accessors
# ---------------------------------------------------------------------------
# Systems (Scout, future Beacon / Ad / Content) are BaseSystem subclasses
# that wrap the inner pipeline orchestrators with the mandatory foundation
# loop. Routers and the daemon depend on these rather than building stages
# directly — every dispatch is context-aware, autonomy-gated, and logged.


def get_scout_system() -> ScoutSystem:
    """ScoutSystem wired to production backends via the registry.

    Process-singleton — ``from_registry`` runs at most once per process.
    Uses a zero-arg cache (rather than ``@lru_cache`` keyed on the
    registry instance) because ``SystemRegistry`` is an unfrozen
    ``@dataclass`` and therefore unhashable: keying on it would raise
    ``TypeError`` on the first real call. ``get_registry`` is already a
    process-singleton upstream, so one cache is enough. Tests override
    this via ``app.dependency_overrides`` to inject mocks.
    """
    return _scout_system_singleton()


@lru_cache(maxsize=1)
def _scout_system_singleton() -> ScoutSystem:
    return ScoutSystem.from_registry(get_registry())
