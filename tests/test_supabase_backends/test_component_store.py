"""Tests for SupabaseComponentStoreBackend.

The single most important test in the entire Task 16b Step 1 is
``test_update_variants_preserves_learned_stats`` — it proves the item-62
gate invariant via a hostile payload: even if a caller passes win_rate=0.99
/ sample_size=999 on the ComponentVariant, the update MUST NOT reach those
columns in the DB.
"""
from __future__ import annotations

import pytest

from systems.scout.outreach.component_store import ComponentVariant
from systems.scout.supabase_backends.component_store import (
    SupabaseComponentStoreBackend,
)
from tests.test_supabase_backends.fakes import FakeSupabaseClient


# --------------------------------------------------------------------------- #
# ITEM-62 GATE — preserves Plan 2 learned stats                                #
# --------------------------------------------------------------------------- #


async def test_update_variants_preserves_learned_stats() -> None:
    """Hostile-payload regression test for backlog item 62.

    Scenario:
    1. insert_variants creates a row via the loader path (win_rate=None,
       sample_size=0 — DB defaults).
    2. Plan 2's cohort evaluator (simulated here by a direct row mutation)
       writes win_rate=0.42 + sample_size=100.
    3. A malicious/buggy caller passes a ComponentVariant with
       win_rate=0.99 and sample_size=999 to update_variants.
    4. Assert DB row's learned stats are UNCHANGED (0.42 / 100) AND
       the four allowed columns WERE updated to the new values.
    """
    fake = FakeSupabaseClient()
    backend = SupabaseComponentStoreBackend(fake)

    # --- Step 1: loader-path insert (no learned stats set) ----------------
    loader_variant = ComponentVariant(
        variant_key="agency_growth_hook_v1",
        component_type="icebreaker",
        niche="cro_growth_ugc_agency",
        offer_label="pipeline_audit",
        variant_content="Original content — loader path",
        status="draft",
        metadata={"author": "Kirsten"},
        ab_epsilon=0.1,
    )
    await backend.insert_variants("client-zero", [loader_variant])

    rows = fake.rows("component_variants")
    assert len(rows) == 1
    assert rows[0].get("win_rate") is None  # unset at insert time
    assert rows[0].get("sample_size") is None or rows[0].get("sample_size") == 0
    variant_id = rows[0]["id"]

    # --- Step 2: Plan 2 writes learned stats (direct row mutation) -------
    rows[0]["win_rate"] = 0.42
    rows[0]["sample_size"] = 100
    # Sanity — learned stats are set.
    assert fake.rows("component_variants")[0]["win_rate"] == 0.42
    assert fake.rows("component_variants")[0]["sample_size"] == 100

    # --- Step 3: HOSTILE payload on the sync path ------------------------
    hostile_variant = ComponentVariant(
        variant_key="agency_growth_hook_v1",
        component_type="icebreaker",
        niche="cro_growth_ugc_agency",
        offer_label="pipeline_audit",
        variant_content="UPDATED content — new operator edit",
        status="approved",          # changed
        metadata={"author": "Kirsten", "updated": True},
        ab_epsilon=0.2,             # changed
        win_rate=0.99,              # HOSTILE — must not reach DB
        sample_size=999,            # HOSTILE — must not reach DB
    )
    await backend.update_variants("client-zero", [(variant_id, hostile_variant)])

    # --- Step 4: assertions ----------------------------------------------
    final = fake.rows("component_variants")[0]

    # Learned stats UNCHANGED — this is the whole point of the gate.
    assert final["win_rate"] == 0.42, (
        f"win_rate clobbered by update_variants: expected 0.42, got {final['win_rate']!r}. "
        "Item-62 gate breached."
    )
    assert final["sample_size"] == 100, (
        f"sample_size clobbered by update_variants: expected 100, got {final['sample_size']!r}. "
        "Item-62 gate breached."
    )

    # Allowed columns WERE updated.
    assert final["variant_content"] == "UPDATED content — new operator edit"
    assert final["status"] == "approved"
    assert final["metadata"] == {"author": "Kirsten", "updated": True}
    assert final["ab_epsilon"] == 0.2

    # Defence-in-depth: the update_calls payload must only contain the
    # four allow-listed columns.
    assert len(fake._update_calls) == 1
    payload_keys = set(fake._update_calls[0]["payload"].keys())
    assert payload_keys == {
        "variant_content", "status", "metadata", "ab_epsilon",
    }, f"update payload leaked columns: {payload_keys}"


async def test_update_variants_allow_list_is_class_level_frozenset() -> None:
    """The allow-list must be a frozenset AT CLASS LEVEL — immutable,
    not rebuilt on every update call."""
    cls = SupabaseComponentStoreBackend
    assert hasattr(cls, "_UPDATABLE_COLUMNS")
    assert isinstance(cls._UPDATABLE_COLUMNS, frozenset)
    assert cls._UPDATABLE_COLUMNS == frozenset({
        "variant_content", "status", "metadata", "ab_epsilon",
    })


# --------------------------------------------------------------------------- #
# Happy paths                                                                   #
# --------------------------------------------------------------------------- #


async def test_insert_variants_writes_rows_without_learned_stats() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseComponentStoreBackend(fake)

    variants = [
        ComponentVariant(
            variant_key=f"key_{i}",
            component_type="icebreaker",
            niche="n",
            offer_label="o",
            variant_content=f"content {i}",
        )
        for i in range(3)
    ]
    await backend.insert_variants("c1", variants)

    assert len(fake.rows("component_variants")) == 3
    # win_rate/sample_size MUST NOT appear in the insert payload (DB defaults).
    call = fake._insert_calls[0]
    for row in call["rows"]:
        assert "win_rate" not in row
        assert "sample_size" not in row


async def test_insert_variants_noop_on_empty_list() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseComponentStoreBackend(fake)

    await backend.insert_variants("c1", [])
    assert fake._insert_calls == []
    assert fake.rows("component_variants") == []


async def test_fetch_existing_groups_by_niche_offer() -> None:
    fake = FakeSupabaseClient(
        tables={
            "component_variants": [
                {
                    "id": "uuid-1",
                    "client_id": "c1",
                    "component_type": "icebreaker",
                    "variant_key": "k1",
                    "niche": "n",
                    "offer_label": "o",
                    "variant_content": "v1",
                    "status": "draft",
                    "metadata": {},
                    "ab_epsilon": 0.1,
                    "win_rate": None,
                    "sample_size": 0,
                },
                {
                    "id": "uuid-2",
                    "client_id": "c1",
                    "component_type": "icebreaker",
                    "variant_key": "k_other",
                    "niche": "n",
                    "offer_label": "o",
                    "variant_content": "v2",
                    "status": "draft",
                    "metadata": {},
                    "ab_epsilon": 0.1,
                    "win_rate": None,
                    "sample_size": 0,
                },
            ],
        }
    )
    backend = SupabaseComponentStoreBackend(fake)

    existing = await backend.fetch_existing(
        "c1",
        [("icebreaker", "k1", "n", "o")],
    )
    assert list(existing.keys()) == [("icebreaker", "k1", "n", "o")]
    assert existing[("icebreaker", "k1", "n", "o")]["id"] == "uuid-1"


async def test_fetch_existing_empty_keys_returns_empty() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseComponentStoreBackend(fake)
    assert await backend.fetch_existing("c1", []) == {}


# --------------------------------------------------------------------------- #
# Guard paths                                                                   #
# --------------------------------------------------------------------------- #


async def test_update_variants_noop_on_empty_updates() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseComponentStoreBackend(fake)
    await backend.update_variants("c1", [])
    assert fake._update_calls == []


async def test_update_variants_exception_propagates() -> None:
    """If Supabase raises, the backend must NOT swallow it."""

    class BoomClient(FakeSupabaseClient):
        def table(self, name):  # type: ignore[override]
            raise RuntimeError("supabase unreachable")

    backend = SupabaseComponentStoreBackend(BoomClient())
    variant = ComponentVariant(
        variant_key="k", component_type="icebreaker", niche="n",
        offer_label="o", variant_content="c",
    )
    with pytest.raises(RuntimeError, match="supabase unreachable"):
        await backend.update_variants("c1", [("some-id", variant)])
