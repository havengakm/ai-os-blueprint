"""Scout outreach package — component registry + research selector + (future) composer/render stack."""
from systems.scout.outreach.component_store import (
    ComponentStore,
    ComponentStoreBackend,
    ComponentVariant,
    SyncSummary,
    VALID_COMPONENT_TYPES,
    VALID_STATUSES,
)
from systems.scout.outreach.research import (
    DecisionLoggerProtocol,
    ResearchFills,
    ResearchSelector,
)

__all__ = [
    "ComponentStore",
    "ComponentStoreBackend",
    "ComponentVariant",
    "DecisionLoggerProtocol",
    "ResearchFills",
    "ResearchSelector",
    "SyncSummary",
    "VALID_COMPONENT_TYPES",
    "VALID_STATUSES",
]
