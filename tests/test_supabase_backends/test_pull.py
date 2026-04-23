"""Tests for SupabasePullBackend."""
from __future__ import annotations

import pytest

from systems.scout.sources.base import RawCompanyContact
from systems.scout.supabase_backends.pull import SupabasePullBackend
from tests.test_supabase_backends.fakes import FakeSupabaseClient


# --------------------------------------------------------------------------- #
# get_active_directories                                                        #
# --------------------------------------------------------------------------- #


async def test_get_active_directories_returns_configured_list() -> None:
    fake = FakeSupabaseClient(
        tables={
            "client_config": [
                {"client_id": "c1", "active_directories": ["clutch", "apollo"]},
            ],
        }
    )
    backend = SupabasePullBackend(fake)

    assert await backend.get_active_directories("c1") == ["clutch", "apollo"]


async def test_get_active_directories_missing_client_returns_empty() -> None:
    fake = FakeSupabaseClient()
    backend = SupabasePullBackend(fake)

    assert await backend.get_active_directories("no-such-client") == []


# --------------------------------------------------------------------------- #
# contact_exists                                                                #
# --------------------------------------------------------------------------- #


async def test_contact_exists_matches_source_source_id() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {
                    "id": "uuid-1",
                    "client_id": "c1",
                    "source": "apollo",
                    "source_id": "aaa",
                    "company_domain": "foo.com",
                },
            ]
        }
    )
    backend = SupabasePullBackend(fake)

    assert await backend.contact_exists(
        "c1", source="apollo", source_id="aaa", company_domain=None,
    ) is True


async def test_contact_exists_matches_domain_fallback() -> None:
    fake = FakeSupabaseClient(
        tables={
            "contacts": [
                {
                    "id": "uuid-1",
                    "client_id": "c1",
                    "source": "apollo",
                    "source_id": "aaa",
                    "company_domain": "foo.com",
                },
            ]
        }
    )
    backend = SupabasePullBackend(fake)

    assert await backend.contact_exists(
        "c1", source="clutch", source_id="zzz", company_domain="foo.com",
    ) is True


async def test_contact_exists_no_match_returns_false() -> None:
    fake = FakeSupabaseClient(tables={"contacts": []})
    backend = SupabasePullBackend(fake)

    assert await backend.contact_exists(
        "c1", source="apollo", source_id="xxx", company_domain="bar.com",
    ) is False


async def test_contact_exists_raises_when_no_identifier() -> None:
    backend = SupabasePullBackend(FakeSupabaseClient())
    with pytest.raises(ValueError, match="at least one"):
        await backend.contact_exists("c1")


# --------------------------------------------------------------------------- #
# insert_contact                                                                #
# --------------------------------------------------------------------------- #


async def test_insert_contact_persists_row_with_on_conflict_ignore() -> None:
    fake = FakeSupabaseClient()
    backend = SupabasePullBackend(fake)

    contact = RawCompanyContact(
        company="Foo Inc",
        company_domain="foo.com",
        industry="saas",
        employees=25,
        source="apollo",
        source_id="aaa",
        raw_data={"external": True},
    )
    await backend.insert_contact("c1", contact)

    rows = fake.rows("contacts")
    assert len(rows) == 1
    assert rows[0]["company"] == "Foo Inc"
    assert rows[0]["status"] == "new"
    # Upsert on (client_id, source, source_id), ignore duplicates.
    assert fake._upsert_calls[0]["on_conflict"] == "client_id,source,source_id"
    assert fake._upsert_calls[0]["ignore_duplicates"] is True


# --------------------------------------------------------------------------- #
# log_decision                                                                  #
# --------------------------------------------------------------------------- #


async def test_log_decision_inserts_row() -> None:
    fake = FakeSupabaseClient()
    backend = SupabasePullBackend(fake)

    await backend.log_decision(
        "c1",
        decision_type="source_selection",
        decision="pulled",
        context={"adapter_name": "apollo", "pulled": 10},
        reasoning="test",
        confidence=0.9,
    )

    rows = fake.rows("decision_log")
    assert len(rows) == 1
    assert rows[0]["decision_type"] == "source_selection"
    assert rows[0]["context"] == {"adapter_name": "apollo", "pulled": 10}
    assert rows[0]["confidence"] == 0.9
    assert rows[0]["source"] == "system"


async def test_log_decision_exception_propagates() -> None:
    class BoomClient(FakeSupabaseClient):
        def table(self, name):  # type: ignore[override]
            raise RuntimeError("db down")

    backend = SupabasePullBackend(BoomClient())
    with pytest.raises(RuntimeError, match="db down"):
        await backend.log_decision(
            "c1", decision_type="x", decision="y", context={},
        )
