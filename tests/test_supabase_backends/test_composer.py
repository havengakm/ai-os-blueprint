"""Tests for SupabaseComposerBackend."""
from __future__ import annotations

from typing import Any

import pytest

from systems.scout.supabase_backends.composer import SupabaseComposerBackend
from tests.test_supabase_backends.fakes import FakeSupabaseClient


async def test_fetch_approved_variants_groups_by_type_and_applies_learned_stats() -> None:
    fake = FakeSupabaseClient(
        tables={
            "component_variants": [
                {
                    "client_id": "c1", "component_type": "icebreaker",
                    "variant_key": "ib_v1", "niche": "n", "offer_label": "o",
                    "variant_content": "hello", "status": "approved",
                    "metadata": {}, "ab_epsilon": 0.1,
                    "win_rate": 0.42, "sample_size": 100,
                },
                {
                    "client_id": "c1", "component_type": "icebreaker",
                    "variant_key": "ib_v2", "niche": "n", "offer_label": "o",
                    "variant_content": "hi", "status": "approved",
                    "metadata": {}, "ab_epsilon": 0.1,
                    "win_rate": None, "sample_size": 0,
                },
                {
                    "client_id": "c1", "component_type": "cta",
                    "variant_key": "cta_v1", "niche": "n", "offer_label": "o",
                    "variant_content": "book a call", "status": "approved",
                    "metadata": {}, "ab_epsilon": 0.1,
                    "win_rate": None, "sample_size": 0,
                },
                # Wrong status — must NOT appear.
                {
                    "client_id": "c1", "component_type": "cta",
                    "variant_key": "cta_v2", "niche": "n", "offer_label": "o",
                    "variant_content": "draft", "status": "draft",
                    "metadata": {}, "ab_epsilon": 0.1,
                    "win_rate": None, "sample_size": 0,
                },
            ]
        }
    )
    backend = SupabaseComposerBackend(fake)

    result = await backend.fetch_approved_variants("c1", "n", "o")
    assert set(result.keys()) == {"icebreaker", "cta"}
    assert len(result["icebreaker"]) == 2
    assert len(result["cta"]) == 1
    # Plan 2 learned stats flow through.
    ib_first = next(v for v in result["icebreaker"] if v.variant_key == "ib_v1")
    assert ib_first.win_rate == 0.42
    assert ib_first.sample_size == 100


async def test_fetch_approved_variants_no_match_returns_empty_dict() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseComposerBackend(fake)
    result = await backend.fetch_approved_variants("c1", "n", "o")
    assert result == {}


async def test_fetch_active_directories_returns_list() -> None:
    fake = FakeSupabaseClient(
        tables={
            "client_config": [
                {"client_id": "c1",
                 "active_directories": ["google_ads_library", "clutch"]}
            ]
        }
    )
    backend = SupabaseComposerBackend(fake)
    assert await backend.fetch_active_directories("c1") == [
        "google_ads_library", "clutch",
    ]


async def test_persist_draft_inserts_and_returns_uuid() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseComposerBackend(fake)

    draft_id = await backend.persist_draft(
        "c1", "contact-uuid-1",
        subject="hello",
        body="world",
        component_selections={"icebreaker": "ib_v1", "cta": "cta_v1"},
        research_sources=[{"url": "https://foo.com"}],
    )
    assert isinstance(draft_id, str)
    rows = fake.rows("outreach_drafts")
    assert len(rows) == 1
    row = rows[0]
    assert row["client_id"] == "c1"
    assert row["contact_id"] == "contact-uuid-1"
    assert row["subject"] == "hello"
    assert row["body"] == "world"
    assert row["component_selections"] == {
        "icebreaker": "ib_v1", "cta": "cta_v1",
    }
    assert row["research_sources"] == [{"url": "https://foo.com"}]
    assert row["status"] == "rendered"


async def test_persist_draft_raises_when_no_rows_returned() -> None:
    """If the insert returns no data, surface a clear error."""

    class EmptyInsertClient(FakeSupabaseClient):
        def table(self, name: str):  # type: ignore[override]
            builder = super().table(name)
            original_execute = builder.execute

            def empty_execute():
                result = original_execute()
                result.data = []
                return result

            builder.execute = empty_execute  # type: ignore[method-assign]
            return builder

    fake = EmptyInsertClient()
    backend = SupabaseComposerBackend(fake)
    with pytest.raises(RuntimeError, match="insert returned no rows"):
        await backend.persist_draft(
            "c1", "u1",
            subject="s", body="b",
            component_selections={}, research_sources=[],
        )


async def test_log_decision_writes_entry_with_source() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseComposerBackend(fake)
    await backend.log_decision(
        "c1",
        decision_type="render_draft",
        decision="render_draft:u1:Hello...",
        context={"contact_id": "u1"},
        reasoning="composed",
        source="system",
        confidence=None,
    )
    rows = fake.rows("decision_log")
    assert len(rows) == 1
    assert rows[0]["source"] == "system"
    assert rows[0]["decision_type"] == "render_draft"


# ---------------------------------------------------------------------------
# fetch_eligible_contacts                                                       #
# ---------------------------------------------------------------------------


def _enriched_contact(
    *,
    contact_id: str,
    client_id: str = "c1",
    tier: str = "A",
    score: int = 80,
    status: str = "enriched",
    niche: str = "n",
    **extra: Any,
) -> dict[str, Any]:
    row = {
        "id": contact_id,
        "client_id": client_id,
        "icp_tier": tier,
        "icp_score": score,
        "status": status,
        "niche": niche,
        "first_name": "Jane",
        "company": "Acme",
        "email": f"{contact_id}@example.com",
        "research_data": {},
    }
    row.update(extra)
    return row


async def test_fetch_eligible_contacts_returns_enriched_tier_abc() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                _enriched_contact(contact_id="u1", tier="A", score=90),
                _enriched_contact(contact_id="u2", tier="B", score=70),
                _enriched_contact(contact_id="u3", tier="C", score=50),
            ]
        }
    )
    backend = SupabaseComposerBackend(fake)

    result = await backend.fetch_eligible_contacts("c1")

    assert [c["contact_id"] for c in result] == ["u1", "u2", "u3"]
    # Each row has composer-friendly keys.
    first = result[0]
    assert first["niche"] == "n"
    assert first["first_name"] == "Jane"
    assert first["icp_tier"] == "A"
    assert first["icp_score"] == 90
    assert first["research_data"] == {}


async def test_fetch_eligible_contacts_excludes_tier_d_and_archive() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                _enriched_contact(contact_id="u1", tier="A"),
                # Tier D — must NOT appear.
                _enriched_contact(contact_id="u2", tier="D"),
                # Archived status — must NOT appear.
                _enriched_contact(contact_id="u3", tier="A", status="archived"),
                # Not yet enriched — must NOT appear.
                _enriched_contact(contact_id="u4", tier="A", status="screened"),
            ]
        }
    )
    backend = SupabaseComposerBackend(fake)

    result = await backend.fetch_eligible_contacts("c1")
    assert [c["contact_id"] for c in result] == ["u1"]


async def test_fetch_eligible_contacts_excludes_contacts_with_existing_draft() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                _enriched_contact(contact_id="u1", tier="A", score=90),
                _enriched_contact(contact_id="u2", tier="B", score=80),
                _enriched_contact(contact_id="u3", tier="C", score=70),
            ],
            "outreach_drafts": [
                # u2 already drafted — must be skipped.
                {"id": "d-1", "client_id": "c1", "contact_id": "u2",
                 "status": "rendered"},
            ],
        }
    )
    backend = SupabaseComposerBackend(fake)

    result = await backend.fetch_eligible_contacts("c1")
    assert [c["contact_id"] for c in result] == ["u1", "u3"]


async def test_fetch_eligible_contacts_orders_by_tier_then_score_desc() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                _enriched_contact(contact_id="c-low", tier="C", score=95),
                _enriched_contact(contact_id="a-low", tier="A", score=40),
                _enriched_contact(contact_id="a-high", tier="A", score=99),
                _enriched_contact(contact_id="b-mid", tier="B", score=60),
            ]
        }
    )
    backend = SupabaseComposerBackend(fake)

    result = await backend.fetch_eligible_contacts("c1")
    # A ranks above B ranks above C; within a tier, higher score first.
    assert [c["contact_id"] for c in result] == [
        "a-high", "a-low", "b-mid", "c-low",
    ]


async def test_fetch_eligible_contacts_respects_limit() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                _enriched_contact(contact_id=f"u{i}", tier="A", score=100 - i)
                for i in range(5)
            ]
        }
    )
    backend = SupabaseComposerBackend(fake)

    result = await backend.fetch_eligible_contacts("c1", limit=2)
    assert len(result) == 2
    # Top-ranked pair (u0 score 100, u1 score 99).
    assert [c["contact_id"] for c in result] == ["u0", "u1"]


async def test_fetch_eligible_contacts_empty_returns_empty_list() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseComposerBackend(fake)

    result = await backend.fetch_eligible_contacts("c1")
    assert result == []


async def test_fetch_eligible_contacts_applies_server_side_ordering() -> None:
    """Supabase default caps results at ~1000 rows. Without server-side
    ordering, a client with >1000 eligible contacts would get an arbitrary
    slice, not the top-scoring slice. The contacts query must include both
    ``.order("icp_tier")`` and ``.order("icp_score", desc=True)``."""

    class OrderCapturingClient(FakeSupabaseClient):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.contacts_orders: list[tuple[str, bool]] = []

        def table(self, name: str):  # type: ignore[override]
            builder = super().table(name)
            if name == "contacts":
                original_execute = builder.execute
                orders_ref = self.contacts_orders

                def capturing_execute():
                    orders_ref.extend(builder._orders)
                    return original_execute()

                builder.execute = capturing_execute  # type: ignore[method-assign]
            return builder

    fake = OrderCapturingClient(
        tables={"contacts": [_enriched_contact(contact_id="u1", tier="A")]}
    )
    backend = SupabaseComposerBackend(fake)

    await backend.fetch_eligible_contacts("c1")

    assert ("icp_tier", False) in fake.contacts_orders
    assert ("icp_score", True) in fake.contacts_orders


async def test_fetch_eligible_contacts_filters_by_client_id() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                _enriched_contact(contact_id="u1", client_id="c1"),
                _enriched_contact(contact_id="u-other", client_id="c2"),
            ]
        }
    )
    backend = SupabaseComposerBackend(fake)

    result = await backend.fetch_eligible_contacts("c1")
    assert [c["contact_id"] for c in result] == ["u1"]
