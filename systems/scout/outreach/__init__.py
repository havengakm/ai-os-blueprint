"""Scout outreach package — component registry + research selector + composer."""
from systems.scout.outreach.component_store import (
    ComponentStore,
    ComponentStoreBackend,
    ComponentVariant,
    SyncSummary,
    VALID_COMPONENT_TYPES,
    VALID_STATUSES,
)
from systems.scout.outreach.composer import (
    AD_ACTIVITY_DIRECTORIES,
    COMPONENT_TYPES_ORDERED,
    Composer,
    ComposedDraft,
    ComposerSkip,
    ComposerStorageBackend,
    DEFAULT_EPSILON,
)
from systems.scout.outreach.research import (
    DecisionLoggerProtocol,
    ResearchFills,
    ResearchSelector,
)

__all__ = [
    "AD_ACTIVITY_DIRECTORIES",
    "COMPONENT_TYPES_ORDERED",
    "ComponentStore",
    "ComponentStoreBackend",
    "ComponentVariant",
    "ComposedDraft",
    "Composer",
    "ComposerSkip",
    "ComposerStorageBackend",
    "DEFAULT_EPSILON",
    "DecisionLoggerProtocol",
    "ResearchFills",
    "ResearchSelector",
    "SyncSummary",
    "VALID_COMPONENT_TYPES",
    "VALID_STATUSES",
]
