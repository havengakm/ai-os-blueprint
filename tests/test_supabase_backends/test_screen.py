"""Tests for SupabaseScreenBackend."""
from __future__ import annotations

from systems.scout.supabase_backends.screen import SupabaseScreenBackend
from tests.test_supabase_backends.fakes import FakeSupabaseClient


async def test_get_client_config_reads_blacklists() -> None:
    fake = FakeSupabaseClient(
        tables={
            "icp_definitions": [
                {
                    "client_id": "c1",
                    "blacklist_companies": ["Evil"],
                    "blacklist_domains": ["evil.com"],
                }
            ]
        }
    )
    backend = SupabaseScreenBackend(fake)

    cfg = await backend.get_client_config("c1")
    assert cfg["icp"]["blacklist_companies"] == ["Evil"]
    assert cfg["icp"]["blacklist_domains"] == ["evil.com"]


async def test_get_client_config_missing_icp_returns_empty_icp() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseScreenBackend(fake)
    cfg = await backend.get_client_config("c1")
    assert cfg == {"icp": {}}


async def test_get_contacts_for_screening_filters_by_status() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {
                    "id": "u1", "client_id": "c1", "status": "screened",
                    "first_name": "Ada", "last_name": "L",
                    "company": "Foo", "company_domain": "foo.com",
                },
                {
                    "id": "u2", "client_id": "c1", "status": "new",
                    "first_name": None, "last_name": None,
                    "company": None, "company_domain": None,
                },
            ]
        }
    )
    backend = SupabaseScreenBackend(fake)

    contacts = await backend.get_contacts_for_screening("c1")
    assert [c.contact_id for c in contacts] == ["u1"]


async def test_mark_contact_passed_transitions_status() -> None:
    fake = FakeSupabaseClient(
        tables={"contacts": [{"id": "u1", "client_id": "c1", "status": "screened"}]}
    )
    backend = SupabaseScreenBackend(fake)

    await backend.mark_contact_passed("c1", "u1")
    assert fake.rows("contacts")[0]["status"] == "ready"


async def test_mark_contact_rejected_sets_dead_and_reason() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "client_id": "c1", "status": "screened",
                 "raw_data": {"seeded": 1}},
            ]
        }
    )
    backend = SupabaseScreenBackend(fake)

    await backend.mark_contact_rejected("c1", "u1", reason="missing_name")
    row = fake.rows("contacts")[0]
    assert row["status"] == "dead"
    assert row["raw_data"]["screen_reject_reason"] == "missing_name"
    assert row["raw_data"]["seeded"] == 1


async def test_log_decision_writes_to_decision_log() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseScreenBackend(fake)
    await backend.log_decision(
        "c1", decision_type="icp_threshold", decision="screen_summary",
        context={"rejections": 3},
    )
    assert len(fake.rows("decision_log")) == 1
