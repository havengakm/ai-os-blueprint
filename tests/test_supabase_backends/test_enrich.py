"""Tests for SupabaseEnrichBackend + SupabaseBudgetTracker."""
from __future__ import annotations

from systems.scout.supabase_backends.enrich import (
    SupabaseBudgetTracker,
    SupabaseEnrichBackend,
)
from tests.test_supabase_backends.fakes import FakeSupabaseClient


# --------------------------------------------------------------------------- #
# SupabaseEnrichBackend                                                         #
# --------------------------------------------------------------------------- #


async def test_get_eligible_contacts_for_enrich_filters() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                # Eligible
                {
                    "id": "u1", "client_id": "c1", "icp_score": 80,
                    "first_name": "Ada", "enriched_at": None,
                    "status": "ready", "icp_tier": "A",
                    "email": "a@a.com", "company": "Foo",
                    "company_domain": "foo.com", "linkedin_url": None,
                    "industry": "saas", "research_data": {},
                },
                # Ineligible: below floor
                {
                    "id": "u2", "client_id": "c1", "icp_score": 20,
                    "first_name": "Ada", "enriched_at": None,
                    "status": "ready", "icp_tier": "D",
                    "email": None, "company": "X", "company_domain": None,
                    "linkedin_url": None, "industry": None, "research_data": {},
                },
                # Ineligible: already enriched
                {
                    "id": "u3", "client_id": "c1", "icp_score": 80,
                    "first_name": "B", "enriched_at": "2026-04-22T00:00:00Z",
                    "status": "enriched", "icp_tier": "A",
                    "email": "b@b.com", "company": "Y", "company_domain": None,
                    "linkedin_url": None, "industry": None, "research_data": {},
                },
                # Ineligible: no identity
                {
                    "id": "u4", "client_id": "c1", "icp_score": 80,
                    "first_name": None, "enriched_at": None,
                    "status": "ready", "icp_tier": "A",
                    "email": None, "company": "Z", "company_domain": None,
                    "linkedin_url": None, "industry": None, "research_data": {},
                },
                # Ineligible: archived
                {
                    "id": "u5", "client_id": "c1", "icp_score": 80,
                    "first_name": "X", "enriched_at": None,
                    "status": "archived", "icp_tier": "A",
                    "email": None, "company": "W", "company_domain": None,
                    "linkedin_url": None, "industry": None, "research_data": {},
                },
            ]
        }
    )
    backend = SupabaseEnrichBackend(fake)

    contacts = await backend.get_eligible_contacts_for_enrich(
        "c1", archive_floor=35,
    )
    assert [c.contact_id for c in contacts] == ["u1"]
    assert contacts[0].icp_tier == "A"
    assert contacts[0].company == "Foo"


async def test_get_client_trigify_search_ids_returns_list() -> None:
    fake = FakeSupabaseClient(
        tables={
            "client_config": [
                {"client_id": "c1", "trigify_search_ids": ["search-1", "search-2"]}
            ]
        }
    )
    backend = SupabaseEnrichBackend(fake)
    assert await backend.get_client_trigify_search_ids("c1") == ["search-1", "search-2"]


async def test_get_client_trigify_search_ids_missing_returns_empty() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseEnrichBackend(fake)
    assert await backend.get_client_trigify_search_ids("c1") == []


async def test_update_contact_enrich_data_deep_merges() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {
                    "id": "u1", "client_id": "c1",
                    "research_data": {
                        "ad_activity": {"ad_count": 3, "platforms": ["google"]},
                        "triggers": ["old"],
                    },
                }
            ]
        }
    )
    backend = SupabaseEnrichBackend(fake)

    patch = {
        "ad_activity": {"ad_count": 7, "platforms": ["linkedin"]},
        "triggers": ["new"],
        "signals": {"pain_match": True},
    }
    await backend.update_contact_enrich_data(
        "c1", "u1",
        research_data_patch=patch,
        email_verified=True,
        email_catch_all=False,
        enriched_at_utc="2026-04-22T00:00:00Z",
    )

    row = fake.rows("contacts")[0]
    # Deep-merge: scalar overwrite, list concat.
    assert row["research_data"]["ad_activity"]["ad_count"] == 7
    assert row["research_data"]["ad_activity"]["platforms"] == ["google", "linkedin"]
    assert row["research_data"]["triggers"] == ["old", "new"]
    assert row["research_data"]["signals"] == {"pain_match": True}
    assert row["email_verified"] is True
    assert row["email_catch_all"] is False
    assert row["enriched_at"] == "2026-04-22T00:00:00Z"
    assert row["status"] == "enriched"


async def test_update_contact_enrich_data_honours_none_email_fields() -> None:
    """When email_verified / email_catch_all are None, the columns must
    NOT be touched (treated as 'no update')."""
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {
                    "id": "u1", "client_id": "c1",
                    "research_data": {},
                    "email_verified": True,   # pre-existing
                    "email_catch_all": False, # pre-existing
                }
            ]
        }
    )
    backend = SupabaseEnrichBackend(fake)

    await backend.update_contact_enrich_data(
        "c1", "u1",
        research_data_patch={"note": "hi"},
        email_verified=None, email_catch_all=None,
        enriched_at_utc="2026-04-22T00:00:00Z",
    )
    row = fake.rows("contacts")[0]
    # Pre-existing values preserved.
    assert row["email_verified"] is True
    assert row["email_catch_all"] is False


# --------------------------------------------------------------------------- #
# SupabaseBudgetTracker                                                         #
# --------------------------------------------------------------------------- #


async def test_budget_tracker_remaining_cents_subtracts_spent() -> None:
    fake = FakeSupabaseClient(
        tables={
            "client_config": [
                {
                    "client_id": "c1",
                    "tier_budgets_cents": {"A": 100, "B": 50},
                    "tier_spent_cents": {"A": 30, "B": 10},
                }
            ]
        }
    )
    tracker = SupabaseBudgetTracker(fake)

    assert await tracker.remaining_cents("c1", "A") == 70
    assert await tracker.remaining_cents("c1", "B") == 40


async def test_budget_tracker_remaining_cents_missing_tier_returns_zero() -> None:
    fake = FakeSupabaseClient(
        tables={
            "client_config": [
                {"client_id": "c1", "tier_budgets_cents": {"A": 100},
                 "tier_spent_cents": {}}
            ]
        }
    )
    tracker = SupabaseBudgetTracker(fake)
    assert await tracker.remaining_cents("c1", "X") == 0


async def test_budget_tracker_remaining_cents_missing_client_returns_zero() -> None:
    tracker = SupabaseBudgetTracker(FakeSupabaseClient())
    assert await tracker.remaining_cents("ghost", "A") == 0


async def test_budget_tracker_record_spend_increments() -> None:
    fake = FakeSupabaseClient(
        tables={
            "client_config": [
                {
                    "client_id": "c1",
                    "tier_budgets_cents": {"A": 100},
                    "tier_spent_cents": {"A": 10},
                }
            ]
        }
    )
    tracker = SupabaseBudgetTracker(fake)

    await tracker.record_spend("c1", "A", 25)
    row = fake.rows("client_config")[0]
    assert row["tier_spent_cents"]["A"] == 35

    # Idempotent in the sense of "record twice = twice the debit"
    # (NOT a no-op dedup — each call is an accounting event).
    await tracker.record_spend("c1", "A", 15)
    assert fake.rows("client_config")[0]["tier_spent_cents"]["A"] == 50


async def test_budget_tracker_returns_int() -> None:
    fake = FakeSupabaseClient(
        tables={
            "client_config": [
                {"client_id": "c1",
                 "tier_budgets_cents": {"A": 100},
                 "tier_spent_cents": {"A": 30}}
            ]
        }
    )
    tracker = SupabaseBudgetTracker(fake)
    remaining = await tracker.remaining_cents("c1", "A")
    assert isinstance(remaining, int)


async def test_log_decision_writes_entry() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseEnrichBackend(fake)
    await backend.log_decision(
        "c1", decision_type="enrich_contact",
        decision="enrich_stage_summary", context={"total": 5},
    )
    assert len(fake.rows("decision_log")) == 1
