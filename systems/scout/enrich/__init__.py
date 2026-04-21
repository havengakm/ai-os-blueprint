"""Scout enrichment package.

Exports the adapter protocol, result dataclass, and concrete adapters.
Later sub-tasks will add additional adapters (Lusha phone) and the
orchestrator that wires them into the pipeline.
"""
from systems.scout.enrich.base import EnrichAdapter, EnrichResult
from systems.scout.enrich.claude_research import ClaudeResearchAdapter
from systems.scout.enrich.zerobounce import ZeroBounceAdapter

__all__ = ["ClaudeResearchAdapter", "EnrichAdapter", "EnrichResult", "ZeroBounceAdapter"]
