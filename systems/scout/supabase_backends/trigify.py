"""Supabase backends for Trigify monitor provisioning + discovery storage.

Two thin classes implementing the Protocols from:
  - systems/scout/sources/trigify_monitors.py::TrigifyMonitorStorage
  - systems/scout/sources/trigify_discovery.py::DiscoveryStorage

Both operate on client_config rows. No new tables; columns already exist
(trigify_search_ids from migration 005; trigify_discovery_config from
migration 009).
"""
from __future__ import annotations

import logging
from typing import Any

from systems.scout.supabase_backends._base import (
    SupabaseLike,
    insert_decision_log_row,
)

logger = logging.getLogger(__name__)


class SupabaseTrigifyMonitorStorage:
    """Persists monitor search IDs for a client.

    Called by the ``scripts/configure_trigify_monitors.py`` CLI after a
    successful ``TrigifyMonitorCreator.provision_from_yaml`` run.
    """

    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def update_trigify_search_ids(
        self, client_id: str, search_ids: list[str],
    ) -> None:
        """Overwrite client_config.trigify_search_ids. Idempotent.

        Matches Task 1.5.9a's TrigifyMonitorStorage Protocol. Single-writer
        discipline (operator-triggered, not concurrent) makes this safe
        without optimistic locking.
        """
        (
            self._client.table("client_config")
            .update({"trigify_search_ids": list(search_ids)})
            .eq("client_id", client_id)
            .execute()
        )


class SupabaseDiscoveryStorage:
    """Reads client discovery config + logs decisions.

    Called by the ``scripts/run_trigify_discovery.py`` CLI and the Scout
    daemon daily cron. Conforms to Task 1.5.9b's DiscoveryStorage Protocol.
    """

    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def get_trigify_search_ids(self, client_id: str) -> list[str]:
        """Return ``client_config.trigify_search_ids`` for this client.

        Missing row or null column returns ``[]`` — the discovery source
        treats that as ``no_monitors_configured`` and exits early.
        """
        resp = (
            self._client.table("client_config")
            .select("trigify_search_ids")
            .eq("client_id", client_id)
            .limit(1)
            .execute()
        )
        rows = getattr(resp, "data", None) or []
        if not rows:
            return []
        return list(rows[0].get("trigify_search_ids") or [])

    async def get_discovery_config(self, client_id: str) -> dict[str, Any]:
        """Return ``client_config.trigify_discovery_config`` JSONB.

        Missing row or null column returns ``{}`` — DiscoveryConfig then
        falls back to the Max-webinar defaults (threshold=10, cap=100,
        all 4 subsets enabled).
        """
        resp = (
            self._client.table("client_config")
            .select("trigify_discovery_config")
            .eq("client_id", client_id)
            .limit(1)
            .execute()
        )
        rows = getattr(resp, "data", None) or []
        if not rows:
            return {}
        return dict(rows[0].get("trigify_discovery_config") or {})

    async def log_decision(
        self,
        client_id: str,
        *,
        decision_type: str,
        decision: str,
        context: dict[str, Any],
        reasoning: str | None = None,
        confidence: float | None = None,
    ) -> None:
        """Append a decision_log row. Used for per-search / per-engager
        outcome tracking inside the discovery source."""
        insert_decision_log_row(
            self._client,
            client_id=client_id,
            decision_type=decision_type,
            decision=decision,
            context=context,
            reasoning=reasoning,
            confidence=confidence,
        )
