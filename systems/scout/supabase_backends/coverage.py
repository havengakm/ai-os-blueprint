"""EnrichmentCoverageBackend — thin wrapper over the
``get_enrichment_coverage`` Postgres RPC (migration 021).

Plan 2 Phase 4 Task 2.4.5. The RPC returns a JSONB array of
per-(niche, tier) coverage rollups; this wrapper normalises None /
list shape so the cost_dashboard CLI (Task 2.4.6) gets a clean
``list[dict]`` regardless of the underlying client's response shape.

Per-row fields (from migration 021's view):
  - niche
  - icp_tier (one of 'A', 'B', 'C')
  - total_contacts
  - email_present_count, email_verified_count
  - linkedin_present_count
  - phone_present_count
  - domain_resolved_count
  - trigger_events_count
  - email_verified_pct, linkedin_pct, phone_pct
"""
from __future__ import annotations

from systems.scout.supabase_backends._base import SupabaseLike


class EnrichmentCoverageBackend:
    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def get_enrichment_coverage(self, client_id: str) -> list[dict]:
        resp = (
            self._client
            .rpc("get_enrichment_coverage", {"client_id_param": client_id})
            .execute()
        )
        data = resp.data
        if data is None:
            return []
        # Postgres jsonb_agg returns either a JSONB array or NULL; the
        # supabase-py client deserialises arrays as Python lists. Some
        # client versions wrap a single jsonb result in a list of one
        # element — handle both shapes defensively.
        if isinstance(data, list) and data and isinstance(data[0], list):
            return data[0]
        return list(data) if isinstance(data, list) else []
