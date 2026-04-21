"""Scout enrichment package.

Exports the adapter protocol, result dataclass, and concrete adapters.
Later sub-tasks will add additional adapters (Lusha phone, Claude research)
and the orchestrator that wires them into the pipeline.
"""
from systems.scout.enrich.base import EnrichAdapter, EnrichResult
from systems.scout.enrich.zerobounce import ZeroBounceAdapter

__all__ = ["EnrichAdapter", "EnrichResult", "ZeroBounceAdapter"]
