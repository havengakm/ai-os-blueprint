"""Real Supabase backend implementations for every Protocol shipped by
Plan 1 Tasks 9.5e / 12c / 12d / 13 / 15.

Each backend wraps a ``supabase.Client`` and conforms to a Protocol
defined in ``systems/scout/pipeline/`` or ``systems/scout/outreach/``.
The service-role key bypasses RLS, which is appropriate for these
operator-triggered stages.

The most important class here is :class:`SupabaseComponentStoreBackend`.
Its ``update_variants`` method enforces the item-62 gate: the sync path
MUST NOT clobber Plan 2's learned ``win_rate`` / ``sample_size``
statistics. See the class docstring for the allow-list invariant.
"""
from __future__ import annotations

from systems.scout.supabase_backends.component_store import (
    SupabaseComponentStoreBackend,
)
from systems.scout.supabase_backends.composer import SupabaseComposerBackend
from systems.scout.supabase_backends.enrich import (
    SupabaseBudgetTracker,
    SupabaseEnrichBackend,
)
from systems.scout.supabase_backends.identity import SupabaseIdentityBackend
from systems.scout.supabase_backends.pull import SupabasePullBackend
from systems.scout.supabase_backends.score import SupabaseScoreBackend
from systems.scout.supabase_backends.screen import SupabaseScreenBackend

__all__ = [
    "SupabaseBudgetTracker",
    "SupabaseComponentStoreBackend",
    "SupabaseComposerBackend",
    "SupabaseEnrichBackend",
    "SupabaseIdentityBackend",
    "SupabasePullBackend",
    "SupabaseScoreBackend",
    "SupabaseScreenBackend",
]
