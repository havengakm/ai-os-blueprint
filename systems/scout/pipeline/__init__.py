"""Scout pipeline stages — pull, screen, score, identity, enrich.

Each stage is a standalone dispatcher that wraps its domain logic /
orchestrator with a storage Protocol, a Result dataclass, and a summary
decision_log entry. BaseSystem wiring lives in Task 16.5 onward.
"""
from systems.scout.pipeline.enrich import (
    EnrichContactRow,
    EnrichStage,
    EnrichStageResult,
    EnrichStorageBackend,
)

__all__ = [
    "EnrichContactRow",
    "EnrichStage",
    "EnrichStageResult",
    "EnrichStorageBackend",
]
