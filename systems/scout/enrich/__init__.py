"""Scout enrichment package.

Exports the adapter protocol, result dataclass, concrete adapters, and the
tier-gated orchestrator. Later sub-tasks will add a Lusha phone adapter
and the Task 12d pipeline stage that wraps the orchestrator.
"""
from systems.scout.enrich.apollo_enrich import ApolloEnrichAdapter
from systems.scout.enrich.base import EnrichAdapter, EnrichResult
from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
from systems.scout.enrich.claude_research import ClaudeResearchAdapter
from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
from systems.scout.enrich.orchestrator import (
    TIER_ADAPTERS,
    BudgetTracker,
    EnrichOrchestrator,
    EnrichOrchestratorResult,
)
from systems.scout.enrich.trigify import TrigifyAdapter
from systems.scout.enrich.zerobounce import ZeroBounceAdapter

__all__ = [
    "TIER_ADAPTERS",
    "ApolloEnrichAdapter",
    "BudgetTracker",
    "ClaudeDeepResearchAdapter",
    "ClaudeResearchAdapter",
    "ClaudeWebTriggersAdapter",
    "EnrichAdapter",
    "EnrichOrchestrator",
    "EnrichOrchestratorResult",
    "EnrichResult",
    "TrigifyAdapter",
    "ZeroBounceAdapter",
]
