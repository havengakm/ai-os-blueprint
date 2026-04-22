"""Tests for SupabaseComposerBackend."""
from __future__ import annotations

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
