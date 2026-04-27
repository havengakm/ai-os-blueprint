"""Tests for EnrichmentCoverageBackend.

Wraps the ``get_enrichment_coverage(client_id_param)`` RPC from
migration 021. The RPC returns a JSONB array of per-(niche, tier)
rollup objects; the backend unwraps to a list of dicts for the CLI.
"""
from __future__ import annotations

from systems.scout.supabase_backends.coverage import EnrichmentCoverageBackend
from tests.test_supabase_backends.fakes import FakeSupabaseClient


async def test_returns_list_when_rpc_returns_jsonb_array() -> None:
    fake = FakeSupabaseClient()
    fake.set_rpc(
        "get_enrichment_coverage",
        [
            {
                "niche": "creative_branding",
                "icp_tier": "A",
                "total_contacts": 12,
                "email_verified_pct": 91.7,
                "linkedin_pct": 100.0,
                "phone_pct": 75.0,
            },
            {
                "niche": "creative_branding",
                "icp_tier": "B",
                "total_contacts": 19,
                "email_verified_pct": 78.9,
                "linkedin_pct": 89.5,
                "phone_pct": 0.0,
            },
        ],
    )
    backend = EnrichmentCoverageBackend(fake)

    rows = await backend.get_enrichment_coverage("kirsten-client-zero")
    assert len(rows) == 2
    assert rows[0]["niche"] == "creative_branding"
    assert rows[0]["icp_tier"] == "A"
    assert rows[0]["email_verified_pct"] == 91.7


async def test_returns_empty_list_when_no_data() -> None:
    fake = FakeSupabaseClient()
    fake.set_rpc("get_enrichment_coverage", [])
    backend = EnrichmentCoverageBackend(fake)
    rows = await backend.get_enrichment_coverage("c1")
    assert rows == []


async def test_passes_client_id_param_to_rpc() -> None:
    fake = FakeSupabaseClient()
    fake.set_rpc("get_enrichment_coverage", [])
    backend = EnrichmentCoverageBackend(fake)
    await backend.get_enrichment_coverage("c-target")
    assert fake.rpc_calls("get_enrichment_coverage") == [
        {"name": "get_enrichment_coverage", "params": {"client_id_param": "c-target"}}
    ]


async def test_handles_none_data_returns_empty_list() -> None:
    """Defensive — if the RPC returns NULL (no rows matched the
    client_id), normalise to []."""
    fake = FakeSupabaseClient()
    fake.set_rpc("get_enrichment_coverage", None)
    backend = EnrichmentCoverageBackend(fake)
    assert await backend.get_enrichment_coverage("c1") == []
