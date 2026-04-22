"""Tests for SupabaseIdentityBackend."""
from __future__ import annotations

from systems.scout.supabase_backends.identity import SupabaseIdentityBackend
from tests.test_supabase_backends.fakes import FakeSupabaseClient


async def test_get_eligible_contacts_applies_score_and_null_identity_filters() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                # Eligible
                {
                    "id": "u1", "client_id": "c1",
                    "company": "Foo", "company_domain": "foo.com",
                    "icp_score": 60, "first_name": None, "status": "screened",
                },
                # Ineligible: below floor
                {
                    "id": "u2", "client_id": "c1",
                    "company": "Bar", "company_domain": "bar.com",
                    "icp_score": 20, "first_name": None, "status": "screened",
                },
                # Ineligible: identity already resolved
                {
                    "id": "u3", "client_id": "c1",
                    "company": "Baz", "company_domain": "baz.com",
                    "icp_score": 75, "first_name": "Ada", "status": "ready",
                },
                # Ineligible: archived
                {
                    "id": "u4", "client_id": "c1",
                    "company": "Qux", "company_domain": "qux.com",
                    "icp_score": 75, "first_name": None, "status": "archived",
                },
            ]
        }
    )
    backend = SupabaseIdentityBackend(fake)

    contacts = await backend.get_eligible_contacts("c1", archive_floor=35)
    assert [c.contact_id for c in contacts] == ["u1"]
    assert contacts[0].company_name == "Foo"


async def test_get_eligible_contacts_honours_limit() -> None:
    tables = {
        "contacts": [
            {
                "id": f"u{i}", "client_id": "c1",
                "company": "X", "company_domain": None,
                "icp_score": 80, "first_name": None, "status": "screened",
            }
            for i in range(5)
        ]
    }
    fake = FakeSupabaseClient(tables=tables)
    backend = SupabaseIdentityBackend(fake)

    contacts = await backend.get_eligible_contacts("c1", archive_floor=35, limit=2)
    assert len(contacts) == 2


async def test_update_contact_identity_writes_fields_and_source() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {"id": "u1", "client_id": "c1", "raw_data": {"pre": 1}},
            ]
        }
    )
    backend = SupabaseIdentityBackend(fake)

    await backend.update_contact_identity(
        "c1", "u1",
        first_name="Ada", last_name="L", title="CEO",
        email="a@a.com", linkedin_url="https://li/ada",
        identity_source="apollo_people",
    )
    row = fake.rows("contacts")[0]
    assert row["first_name"] == "Ada"
    assert row["email"] == "a@a.com"
    assert row["raw_data"]["identity_source"] == "apollo_people"
    assert row["raw_data"]["pre"] == 1


async def test_archive_contact_no_decision_maker_sets_status() -> None:
    fake = FakeSupabaseClient(
        tables={"contacts": [{"id": "u1", "client_id": "c1", "status": "screened"}]}
    )
    backend = SupabaseIdentityBackend(fake)

    await backend.archive_contact_no_decision_maker("c1", "u1")
    assert fake.rows("contacts")[0]["status"] == "archived_no_decision_maker"


async def test_log_decision_writes_entry() -> None:
    fake = FakeSupabaseClient()
    backend = SupabaseIdentityBackend(fake)
    await backend.log_decision(
        "c1", decision_type="identity_lookup",
        decision="identity_stage_summary", context={"resolved": 4},
    )
    assert len(fake.rows("decision_log")) == 1
