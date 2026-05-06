"""SystemRegistry — singleton holder for all foundation modules + Supabase backends.

Built once at startup via ``api/deps.py::get_registry()``. Consumers
(FastAPI routers, the Scout daemon, scripts) fetch named instances rather
than constructing their own. Backends are stateless aside from the shared
Supabase client, so a single process-wide singleton is safe.

INTERIM LOCATION (Phase 1, 2026-05-05): This file used to live at
``aios/foundation/registry.py`` and was moved here when foundation got
extracted into the ``aios-foundation`` pip package. It depends on
``systems.scout.supabase_backends`` so it can't ship inside the foundation
package. Phase 3 of the AIOS reorg migrates this file to
``clymb-co-deployment/registry.py`` (the per-deployment dependency-wiring
location). Until Phase 3 lands, this is the canonical home.

Single-writer assumptions (Item 65 S4, Task 16b Step 1 review)
-------------------------------------------------------------
``SupabaseBudgetTracker.record_spend`` uses read-modify-write on
``client_config.tier_spent_cents``. This is safe ONLY while all writes go
through a single process (the API server, OR the Scout daemon — not
both concurrently). If Plan 2 adds webhook-driven replay or concurrent
workers, wrap ``record_spend`` with a Postgres advisory lock or migrate
to a version-column CAS pattern. See ``api/deps.py`` docstring for the
matching note surfaced to deployment readers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, fields
from typing import Any

from aios.foundation.autonomy import AutonomyGate
from aios.foundation.decision_logger import DecisionLogger
from aios.foundation.embedder import VoyageEmbedder
from aios.foundation.employee_memory import EmployeeMemory, EmployeeMemoryPgVector
from aios.foundation.feedback_loop import FeedbackLoop
from aios.foundation.knowledge import KnowledgeStore
from aios.foundation.pattern_matcher import PatternMatcher
from aios.memory.store import MemoryStore
from aios.scout.supabase_backends import (
    SupabaseBudgetTracker,
    SupabaseCheapResolveBackend,
    SupabaseComponentStoreBackend,
    SupabaseComposerBackend,
    SupabaseDiscoveryStorage,
    SupabaseEnrichBackend,
    SupabaseIdentityBackend,
    SupabasePullBackend,
    SupabaseScoreBackend,
    SupabaseScreenBackend,
    SupabaseTrigifyMonitorStorage,
)

logger = logging.getLogger(__name__)


@dataclass
class SystemRegistry:
    """Named singletons. Instantiated once via :func:`build_registry`.

    Every field is a fully-constructed, ready-to-use instance that shares
    the same underlying Supabase client. Consumers treat this as an
    immutable bundle of dependencies — do NOT reassign fields after
    construction (the lru_cache in ``api/deps.py`` hands the same object
    to every caller).
    """

    # Foundation modules
    decision_logger: DecisionLogger
    knowledge_store: KnowledgeStore
    memory_store: MemoryStore
    pattern_matcher: PatternMatcher
    autonomy_gate: AutonomyGate
    embedder: VoyageEmbedder
    # Phase 1 of structural rewrite (2026-04-29) — added for the
    # AI-Employee + COO + decision-feedback-loop architecture.
    employee_memory: EmployeeMemory
    feedback_loop: FeedbackLoop

    # Supabase backends (11 total — 9 pipeline + 2 Trigify; cheap_resolve added 2026-04-29)
    pull_backend: SupabasePullBackend
    cheap_resolve_backend: SupabaseCheapResolveBackend
    score_backend: SupabaseScoreBackend
    screen_backend: SupabaseScreenBackend
    identity_backend: SupabaseIdentityBackend
    enrich_backend: SupabaseEnrichBackend
    budget_tracker: SupabaseBudgetTracker
    component_store_backend: SupabaseComponentStoreBackend
    composer_backend: SupabaseComposerBackend
    trigify_monitor_storage: SupabaseTrigifyMonitorStorage
    trigify_discovery_storage: SupabaseDiscoveryStorage


def build_registry(
    supabase_client: Any,
    *,
    voyage_api_key: str,
) -> SystemRegistry:
    """Construct all named instances from the shared Supabase client + Voyage key.

    Call ONCE at application startup. Instances are stateless aside from
    the injected client, so the returned registry is safe to share across
    request handlers.

    Single-writer assumption (Item 65 S4): the budget tracker's
    read-modify-write on ``client_config.tier_spent_cents`` is safe only
    when this process is the sole writer. See the module docstring.
    """
    embedder = VoyageEmbedder(api_key=voyage_api_key)

    # Foundation: DecisionLogger, KnowledgeStore, PatternMatcher, MemoryStore all
    # accept (db, embedder=None). AutonomyGate takes just db.
    decision_logger = DecisionLogger(supabase_client, embedder=embedder)
    knowledge_store = KnowledgeStore(supabase_client, embedder=embedder)
    pattern_matcher = PatternMatcher(supabase_client, embedder=embedder)
    memory_store = MemoryStore(supabase_client, embedder=embedder)
    autonomy_gate = AutonomyGate(supabase_client)

    # Phase 1 of structural rewrite — Employee memory + feedback loop.
    # employee_memory backs onto employee_memory + employee_subscriptions
    # tables (scripts/sql/024_employee_memory_and_standup.sql).
    # feedback_loop fans out to employee_memory + decision_logger +
    # learning_events on every job completion / outcome arrival.
    employee_memory = EmployeeMemoryPgVector(supabase_client, embedder=embedder)
    feedback_loop = FeedbackLoop(
        db=supabase_client,
        decision_logger=decision_logger,
        employee_memory=employee_memory,
        embedder=embedder,
    )

    # Supabase backends — every one takes just the shared client.
    # NOTE (Item 65 S4): BudgetTracker.record_spend assumes serialised
    # writes. Document here so code-search hits this file too.
    pull_backend = SupabasePullBackend(supabase_client)
    cheap_resolve_backend = SupabaseCheapResolveBackend(supabase_client)
    score_backend = SupabaseScoreBackend(supabase_client)
    screen_backend = SupabaseScreenBackend(supabase_client)
    identity_backend = SupabaseIdentityBackend(supabase_client)
    enrich_backend = SupabaseEnrichBackend(supabase_client)
    budget_tracker = SupabaseBudgetTracker(supabase_client)
    component_store_backend = SupabaseComponentStoreBackend(supabase_client)
    composer_backend = SupabaseComposerBackend(supabase_client)
    trigify_monitor_storage = SupabaseTrigifyMonitorStorage(supabase_client)
    trigify_discovery_storage = SupabaseDiscoveryStorage(supabase_client)

    registry = SystemRegistry(
        decision_logger=decision_logger,
        knowledge_store=knowledge_store,
        memory_store=memory_store,
        pattern_matcher=pattern_matcher,
        autonomy_gate=autonomy_gate,
        embedder=embedder,
        employee_memory=employee_memory,
        feedback_loop=feedback_loop,
        pull_backend=pull_backend,
        cheap_resolve_backend=cheap_resolve_backend,
        score_backend=score_backend,
        screen_backend=screen_backend,
        identity_backend=identity_backend,
        enrich_backend=enrich_backend,
        budget_tracker=budget_tracker,
        component_store_backend=component_store_backend,
        composer_backend=composer_backend,
        trigify_monitor_storage=trigify_monitor_storage,
        trigify_discovery_storage=trigify_discovery_storage,
    )

    logger.info("SystemRegistry built with %d singletons", len(fields(registry)))
    return registry
