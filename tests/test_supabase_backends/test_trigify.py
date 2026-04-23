"""Tests for SupabaseTrigifyMonitorStorage + SupabaseDiscoveryStorage."""
from __future__ import annotations

from systems.scout.supabase_backends.trigify import (
    SupabaseDiscoveryStorage,
    SupabaseTrigifyMonitorStorage,
)
from tests.test_supabase_backends.fakes import FakeSupabaseClient


# --------------------------------------------------------------------------- #
# SupabaseTrigifyMonitorStorage                                                #
# --------------------------------------------------------------------------- #


async def test_update_trigify_search_ids_overwrites_row() -> None:
    fake = FakeSupabaseClient(
        tables={
            "client_config": [
                {"client_id": "c1", "trigify_search_ids": ["old-1"]}
            ]
        }
    )
    storage = SupabaseTrigifyMonitorStorage(fake)

    await storage.update_trigify_search_ids("c1", ["new-1", "new-2", "new-3"])

    row = fake.rows("client_config")[0]
    assert row["trigify_search_ids"] == ["new-1", "new-2", "new-3"]

    # Confirm we used UPDATE (not INSERT / UPSERT).
    assert len(fake._update_calls) == 1
    update = fake._update_calls[0]
    assert update["table"] == "client_config"
    assert update["payload"] == {"trigify_search_ids": ["new-1", "new-2", "new-3"]}
    # Filter should be client_id = c1.
    assert ("eq", "client_id", "c1") in update["filters"]


# --------------------------------------------------------------------------- #
# SupabaseDiscoveryStorage                                                     #
# --------------------------------------------------------------------------- #


async def test_get_trigify_search_ids_missing_row_returns_empty() -> None:
    storage = SupabaseDiscoveryStorage(FakeSupabaseClient())
    assert await storage.get_trigify_search_ids("ghost") == []


async def test_get_trigify_search_ids_null_column_returns_empty() -> None:
    fake = FakeSupabaseClient(
        tables={
            "client_config": [
                {"client_id": "c1", "trigify_search_ids": None}
            ]
        }
    )
    storage = SupabaseDiscoveryStorage(fake)
    assert await storage.get_trigify_search_ids("c1") == []


async def test_get_trigify_search_ids_returns_populated_list() -> None:
    fake = FakeSupabaseClient(
        tables={
            "client_config": [
                {
                    "client_id": "c1",
                    "trigify_search_ids": ["sid-a", "sid-b", "sid-c"],
                }
            ]
        }
    )
    storage = SupabaseDiscoveryStorage(fake)
    result = await storage.get_trigify_search_ids("c1")
    assert result == ["sid-a", "sid-b", "sid-c"]


async def test_get_discovery_config_missing_returns_empty_dict() -> None:
    storage = SupabaseDiscoveryStorage(FakeSupabaseClient())
    assert await storage.get_discovery_config("ghost") == {}


async def test_get_discovery_config_returns_full_dict() -> None:
    cfg = {
        "min_engagement_to_pull": 5,
        "max_leads_per_run": 50,
        "search_subsets_enabled": ["intent", "competitor"],
    }
    fake = FakeSupabaseClient(
        tables={
            "client_config": [
                {"client_id": "c1", "trigify_discovery_config": cfg}
            ]
        }
    )
    storage = SupabaseDiscoveryStorage(fake)
    assert await storage.get_discovery_config("c1") == cfg


async def test_get_discovery_config_null_column_returns_empty() -> None:
    fake = FakeSupabaseClient(
        tables={
            "client_config": [
                {"client_id": "c1", "trigify_discovery_config": None}
            ]
        }
    )
    storage = SupabaseDiscoveryStorage(fake)
    assert await storage.get_discovery_config("c1") == {}


async def test_log_decision_writes_decision_log_row() -> None:
    fake = FakeSupabaseClient()
    storage = SupabaseDiscoveryStorage(fake)

    await storage.log_decision(
        "c1",
        decision_type="trigify_discovery",
        decision="pull_completed",
        context={"searches_queried": 4, "leads_returned": 12},
        reasoning="daily cron",
        confidence=0.9,
    )

    rows = fake.rows("decision_log")
    assert len(rows) == 1
    row = rows[0]
    assert row["client_id"] == "c1"
    assert row["decision_type"] == "trigify_discovery"
    assert row["decision"] == "pull_completed"
    assert row["context"] == {"searches_queried": 4, "leads_returned": 12}
    assert row["reasoning"] == "daily cron"
    assert row["confidence"] == 0.9
    assert row["source"] == "system"
