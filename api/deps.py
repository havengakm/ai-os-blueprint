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


# ---------------------------------------------------------------------------
# Beacon backends + webhook handler
# ---------------------------------------------------------------------------
# Beacon's send + reply ingest backends share the same Supabase client as
# Scout (single-writer assumption — see module docstring).


def get_beacon_send_backend() -> Any:
    """Real-Supabase impl of the SendBackend Protocol (SendStage)."""
    return _beacon_send_backend_singleton()


def get_beacon_webhook_backend() -> Any:
    """Real-Supabase impl of the BeaconWebhookBackend Protocol."""
    return _beacon_webhook_backend_singleton()


def get_beacon_decision_logger() -> Any:
    """SupabaseDecisionLogger — used by both SendStage and WebhookHandler."""
    return _beacon_decision_logger_singleton()


def get_beacon_webhook_handler() -> Any:
    """Production WebhookHandler wired to the real Supabase backends.

    Used as a FastAPI ``dependency_overrides`` target for
    ``api.routers.beacon_webhooks.get_webhook_handler``. Tests override
    this with a fake-backed handler instead.
    """
    return _beacon_webhook_handler_singleton()


@lru_cache(maxsize=1)
def _beacon_send_backend_singleton() -> Any:
    from systems.beacon.storage.send_supabase_backend import SupabaseSendBackend
    return SupabaseSendBackend(get_supabase_client())


@lru_cache(maxsize=1)
def _beacon_webhook_backend_singleton() -> Any:
    from systems.beacon.storage.webhook_supabase_backend import (
        SupabaseWebhookBackend,
    )
    return SupabaseWebhookBackend(get_supabase_client())


@lru_cache(maxsize=1)
def _beacon_decision_logger_singleton() -> Any:
    from systems.beacon.storage.decision_logger_supabase import (
        SupabaseDecisionLogger,
    )
    return SupabaseDecisionLogger(get_supabase_client())


@lru_cache(maxsize=1)
def _beacon_webhook_handler_singleton() -> Any:
    from systems.beacon.pipeline.webhook_handler import WebhookHandler
    return WebhookHandler(
        backend=get_beacon_webhook_backend(),
        decision_logger=get_beacon_decision_logger(),
    )


# ---------------------------------------------------------------------------
# Escalation runtime + Slack notifier (Plan 2 Phase 3 Task 2.3.3)
# ---------------------------------------------------------------------------


def get_escalation_backend() -> Any:
    return _escalation_backend_singleton()


def get_slack_notifier() -> Any:
    """Returns ``HttpxSlackNotifier`` if ``settings.slack_webhook_url`` is
    set, else ``None``. EscalationRuntime treats None as "Slack disabled"
    and skips that path silently (DB insert + decision_log still fire)."""
    return _slack_notifier_singleton()


def get_escalation_runtime() -> Any:
    return _escalation_runtime_singleton()


@lru_cache(maxsize=1)
def _escalation_backend_singleton() -> Any:
    from systems.beacon.storage.escalation_supabase_backend import (
        SupabaseEscalationBackend,
    )
    return SupabaseEscalationBackend(get_supabase_client())


@lru_cache(maxsize=1)
def _slack_notifier_singleton() -> Any:
    from config.settings import get_settings
    from systems.beacon.reply.slack_notifier import HttpxSlackNotifier

    url = get_settings().slack_webhook_url
    if not url:
        return None
    return HttpxSlackNotifier(webhook_url=url)


@lru_cache(maxsize=1)
def _escalation_runtime_singleton() -> Any:
    from systems.beacon.reply.escalation import EscalationRuntime
    return EscalationRuntime(
        backend=get_escalation_backend(),
        decision_logger=get_beacon_decision_logger(),
        slack_notifier=get_slack_notifier(),
    )


# ---------------------------------------------------------------------------
# Cool-off runtime (Plan 2 Phase 3 Task 2.3.4)
# ---------------------------------------------------------------------------


def get_cool_off_backend() -> Any:
    return _cool_off_backend_singleton()


def get_cool_off_runtime() -> Any:
    return _cool_off_runtime_singleton()


@lru_cache(maxsize=1)
def _cool_off_backend_singleton() -> Any:
    from systems.beacon.storage.cool_off_supabase_backend import (
        SupabaseCoolOffBackend,
    )
    return SupabaseCoolOffBackend(get_supabase_client())


@lru_cache(maxsize=1)
def _cool_off_runtime_singleton() -> Any:
    from systems.beacon.reply.cool_off import CoolOffRuntime
    return CoolOffRuntime(
        backend=get_cool_off_backend(),
        decision_logger=get_beacon_decision_logger(),
    )


# ---------------------------------------------------------------------------
# Optimizer recommendation engine (Plan 2 Phase 5 Task 2.5.2)
# ---------------------------------------------------------------------------


def get_optimizer_recommendation_store() -> Any:
    return _optimizer_recommendation_store_singleton()


def get_optimizer_recommendation_engine() -> Any:
    return _optimizer_recommendation_engine_singleton()


@lru_cache(maxsize=1)
def _optimizer_recommendation_store_singleton() -> Any:
    from systems.optimizer.storage.recommendation_supabase_store import (
        SupabaseRecommendationStore,
    )
    return SupabaseRecommendationStore(get_supabase_client())


@lru_cache(maxsize=1)
def _optimizer_recommendation_engine_singleton() -> Any:
    from systems.optimizer.recommendations import RecommendationEngine
    return RecommendationEngine(
        store=get_optimizer_recommendation_store(),
        decision_logger=get_beacon_decision_logger(),
    )
