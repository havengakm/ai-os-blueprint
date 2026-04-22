"""Tests for SupabaseScoreBackend."""
from __future__ import annotations

import pytest

from systems.scout.supabase_backends.score import SupabaseScoreBackend
from tests.test_supabase_backends.fakes import FakeSupabaseClient


# --------------------------------------------------------------------------- #
# get_client_config                                                             #
# --------------------------------------------------------------------------- #


async def test_get_client_config_merges_config_and_icp() -> None:
    fake = FakeSupabaseClient(
        tables={
            "client_config": [
                {
                    "client_id": "c1",
                    "weights": {"fit": 40, "intent": 30, "reach": 20, "recency": 10},
                    "tier_thresholds": {"A": 80, "archive_floor": 35},
                },
            ],
            "icp_definitions": [
                {
                    "client_id": "c1",
                    "industries": ["saas"],
                    "titles": ["CEO"],
                    "employee_min": 10,
                    "employee_max": 100,
                    "geographies": ["US"],
                    "blacklist_companies": ["Evil Corp"],
                    "blacklist_domains": ["evil.com"],
                },
            ],
        }
    )
    backend = SupabaseScoreBackend(fake)

    cfg = await backend.get_client_config("c1")
    assert cfg["weights"]["fit"] == 40
    assert cfg["tier_thresholds"]["archive_floor"] == 35
    assert cfg["icp"]["industries"] == ["saas"]
    assert cfg["icp"]["blacklist_domains"] == ["evil.com"]


async def test_get_client_config_missing_rows_returns_defaults() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseScoreBackend(fake)

    cfg = await backend.get_client_config("c1")
    assert cfg == {"weights": {}, "tier_thresholds": {}, "icp": {}}


# --------------------------------------------------------------------------- #
# get_contacts_for_scoring                                                      #
# --------------------------------------------------------------------------- #


async def test_get_contacts_for_scoring_v1_filters_null_score() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {
                    "id": "u1", "client_id": "c1", "icp_score": None,
                    "industry": "saas", "title": "CEO", "employees": 25,
                    "geography": "US", "email": "a@a.com", "email_verified": True,
                    "linkedin_url": None, "phone": None,
                    "raw_data": {}, "research_data": {},
                },
                {
                    "id": "u2", "client_id": "c1", "icp_score": 80,
                    "industry": "saas", "title": "CEO", "employees": 25,
                    "geography": "US", "email": "b@b.com", "email_verified": True,
                    "linkedin_url": None, "phone": None,
                    "raw_data": {}, "research_data": {},
                },
            ]
        }
    )
    backend = SupabaseScoreBackend(fake)

    contacts = await backend.get_contacts_for_scoring("c1", phase="v1")
    assert len(contacts) == 1
    assert contacts[0].contact_id == "u1"


async def test_get_contacts_for_scoring_unknown_phase_raises() -> None:
    backend = SupabaseScoreBackend(FakeSupabaseClient())
    with pytest.raises(ValueError, match="unknown phase"):
        await backend.get_contacts_for_scoring("c1", phase="v3")


# --------------------------------------------------------------------------- #
# update_contact_score                                                          #
# --------------------------------------------------------------------------- #


async def test_update_contact_score_v1_transitions_status() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "client_id": "c1", "icp_score": None, "status": "new"},
            ]
        }
    )
    backend = SupabaseScoreBackend(fake)

    await backend.update_contact_score("c1", "u1", score=75, tier="A", phase="v1")
    row = fake.rows("contacts")[0]
    assert row["icp_score"] == 75
    assert row["icp_tier"] == "A"
    assert row["status"] == "screened"


async def test_update_contact_score_v2_leaves_status_unchanged() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {
                    "id": "u1", "client_id": "c1",
                    "icp_score": 70, "status": "enriched",
                },
            ]
        }
    )
    backend = SupabaseScoreBackend(fake)

    await backend.update_contact_score("c1", "u1", score=85, tier="A", phase="v2")
    row = fake.rows("contacts")[0]
    assert row["icp_score"] == 85
    assert row["icp_tier"] == "A"
    assert row["status"] == "enriched"


# --------------------------------------------------------------------------- #
# archive_contact + log_decision                                                #
# --------------------------------------------------------------------------- #


async def test_archive_contact_sets_status_and_preserves_raw_data() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "client_id": "c1", "status": "new",
                 "raw_data": {"external": True}},
            ]
        }
    )
    backend = SupabaseScoreBackend(fake)

    await backend.archive_contact("c1", "u1", reason="below_archive_floor")
    row = fake.rows("contacts")[0]
    assert row["status"] == "archived"
    assert row["raw_data"]["archive_reason"] == "below_archive_floor"
    assert row["raw_data"]["external"] is True


async def test_log_decision_writes_to_decision_log() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseScoreBackend(fake)
    await backend.log_decision(
        "c1", decision_type="icp_threshold", decision="score_stage_summary",
        context={"phase": "v1"},
    )
    assert len(fake.rows("decision_log")) == 1
