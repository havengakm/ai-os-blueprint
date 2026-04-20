"""Tests for the ScreenStage pipeline class and screen_contact pure function (Task 11).

Uses in-memory fakes for storage.
"""
from __future__ import annotations

import pytest

from systems.scout.pipeline.screen import (
    ContactToScreen,
    ScreenStage,
    ScreenStageResult,
    screen_contact,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeStorage:
    def __init__(self, config=None, contacts=None):
        self.config = config or {}
        self.contacts = contacts or []
        self.passed: list[dict] = []
        self.rejected: list[dict] = []
        self.decisions: list[dict] = []
        self.raise_on_pass: Exception | None = None
        self.raise_on_reject: Exception | None = None

    async def get_client_config(self, client_id):
        return self.config

    async def get_contacts_for_screening(self, client_id, *, limit=None):
        return self.contacts[:limit] if limit else list(self.contacts)

    async def mark_contact_passed(self, client_id, contact_id):
        if self.raise_on_pass:
            raise self.raise_on_pass
        self.passed.append({"client_id": client_id, "contact_id": contact_id})

    async def mark_contact_rejected(self, client_id, contact_id, *, reason):
        if self.raise_on_reject:
            raise self.raise_on_reject
        self.rejected.append({"client_id": client_id, "contact_id": contact_id, "reason": reason})

    async def log_decision(self, client_id, **kwargs):
        self.decisions.append({"client_id": client_id, **kwargs})


# ---------------------------------------------------------------------------
# Helpers: pre-built contacts
# ---------------------------------------------------------------------------


def valid_contact(contact_id: str = "c-valid") -> ContactToScreen:
    return ContactToScreen(
        contact_id=contact_id,
        first_name="Alice",
        last_name="Smith",
        company="Acme Corp",
        company_domain="acme.com",
    )


def no_name_contact(contact_id: str = "c-noname") -> ContactToScreen:
    return ContactToScreen(
        contact_id=contact_id,
        first_name=None,
        last_name=None,
        company="Acme Corp",
        company_domain="acme.com",
    )


def no_company_contact(contact_id: str = "c-nocompany") -> ContactToScreen:
    return ContactToScreen(
        contact_id=contact_id,
        first_name="Bob",
        last_name="Jones",
        company=None,
        company_domain="bob.com",
    )


def blacklisted_company_contact(contact_id: str = "c-blkco") -> ContactToScreen:
    return ContactToScreen(
        contact_id=contact_id,
        first_name="Eve",
        last_name="Black",
        company="Bad Corp",
        company_domain="bad.com",
    )


def blacklisted_domain_contact(contact_id: str = "c-blkdom") -> ContactToScreen:
    return ContactToScreen(
        contact_id=contact_id,
        first_name="Frank",
        last_name="Dark",
        company="SomeOtherCorp",
        company_domain="evil.io",
    )


ICP_CONFIG = {
    "icp": {
        "blacklist_companies": ["Bad Corp", "Spam Inc"],
        "blacklist_domains": ["evil.io", "spam.net"],
    }
}


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------


def test_screen_passes_valid_contact():
    passed, reason = screen_contact(
        {
            "first_name": "Alice",
            "last_name": "Smith",
            "company": "Acme",
            "company_domain": "acme.com",
        },
        ICP_CONFIG,
    )
    assert passed is True
    assert reason == ""


def test_screen_rejects_missing_name():
    passed, reason = screen_contact(
        {
            "first_name": "",
            "last_name": None,
            "company": "Acme",
            "company_domain": "acme.com",
        },
        ICP_CONFIG,
    )
    assert passed is False
    assert reason == "missing_name"


def test_screen_rejects_missing_company():
    passed, reason = screen_contact(
        {
            "first_name": "Alice",
            "last_name": "Smith",
            "company": None,
            "company_domain": "acme.com",
        },
        ICP_CONFIG,
    )
    assert passed is False
    assert reason == "missing_company"


def test_screen_rejects_blacklisted_company():
    passed, reason = screen_contact(
        {
            "first_name": "Eve",
            "last_name": "B",
            "company": "bad corp",   # case-insensitive
            "company_domain": "bad.com",
        },
        ICP_CONFIG,
    )
    assert passed is False
    assert reason.startswith("blacklisted_company:")
    assert "bad corp" in reason.lower()


def test_screen_rejects_blacklisted_domain():
    passed, reason = screen_contact(
        {
            "first_name": "Frank",
            "last_name": "Dark",
            "company": "SomeOtherCorp",
            "company_domain": "EVIL.IO",  # case-insensitive
        },
        ICP_CONFIG,
    )
    assert passed is False
    assert reason.startswith("blacklisted_domain:")


def test_screen_handles_missing_icp_block():
    """No icp key in client_config → no blacklists, contact passes without crash."""
    passed, reason = screen_contact(
        {
            "first_name": "Alice",
            "last_name": "Smith",
            "company": "Safe Corp",
            "company_domain": "safe.com",
        },
        {},  # empty config, no icp block
    )
    assert passed is True
    assert reason == ""


def test_screen_short_circuits_at_first_rejection():
    """Missing name AND blacklisted company → first rule fires ('missing_name')."""
    passed, reason = screen_contact(
        {
            "first_name": None,
            "last_name": "",
            "company": "Bad Corp",
            "company_domain": "bad.com",
        },
        ICP_CONFIG,
    )
    assert passed is False
    assert reason == "missing_name"


# ---------------------------------------------------------------------------
# Stage tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screen_stage_passes_valid_contact():
    """One valid contact → mark_contact_passed called with correct args."""
    storage = FakeStorage(config=ICP_CONFIG, contacts=[valid_contact()])
    stage = ScreenStage(storage)

    result = await stage.run("client-1")

    assert result.total_eligible == 1
    assert result.total_passed == 1
    assert result.total_rejected == 0
    assert result.total_errored == 0
    assert len(storage.passed) == 1
    assert storage.passed[0]["contact_id"] == "c-valid"
    assert len(storage.rejected) == 0


@pytest.mark.asyncio
async def test_screen_stage_rejects_blacklisted():
    """One blacklisted-company contact → mark_contact_rejected called with reason."""
    storage = FakeStorage(config=ICP_CONFIG, contacts=[blacklisted_company_contact()])
    stage = ScreenStage(storage)

    result = await stage.run("client-1")

    assert result.total_eligible == 1
    assert result.total_rejected == 1
    assert result.total_passed == 0
    assert len(storage.rejected) == 1
    assert storage.rejected[0]["contact_id"] == "c-blkco"
    assert storage.rejected[0]["reason"].startswith("blacklisted_company:")


@pytest.mark.asyncio
async def test_screen_stage_dry_run_skips_persistence():
    """dry_run=True: no pass/reject calls, summary still logged."""
    storage = FakeStorage(
        config=ICP_CONFIG,
        contacts=[valid_contact(), blacklisted_company_contact()],
    )
    stage = ScreenStage(storage)

    result = await stage.run("client-1", dry_run=True)

    assert result.dry_run is True
    assert result.total_eligible == 2
    assert len(storage.passed) == 0
    assert len(storage.rejected) == 0
    # Summary still logged
    summary = next(d for d in storage.decisions if d.get("decision") == "screen_stage_summary")
    assert summary["context"]["dry_run"] is True


@pytest.mark.asyncio
async def test_screen_stage_mixed_batch_buckets():
    """4 contacts: 1 pass, 1 missing_name, 1 blacklisted_company, 1 blacklisted_domain.
    rejections_by_reason has correct counts per bucket."""
    contacts = [
        valid_contact("c-pass"),
        no_name_contact("c-name"),
        blacklisted_company_contact("c-co"),
        blacklisted_domain_contact("c-dom"),
    ]
    storage = FakeStorage(config=ICP_CONFIG, contacts=contacts)
    stage = ScreenStage(storage)

    result = await stage.run("client-1")

    assert result.total_eligible == 4
    assert result.total_passed == 1
    assert result.total_rejected == 3
    assert result.total_errored == 0
    assert result.rejections_by_reason["missing_name"] == 1
    assert result.rejections_by_reason["missing_company"] == 0
    assert result.rejections_by_reason["blacklisted_company"] == 1
    assert result.rejections_by_reason["blacklisted_domain"] == 1


@pytest.mark.asyncio
async def test_screen_stage_persist_error_continues():
    """mark_contact_passed raises for all contacts. Loop continues, total_errored correct."""
    contacts = [valid_contact(f"c-{i}") for i in range(3)]
    storage = FakeStorage(config=ICP_CONFIG, contacts=contacts)
    storage.raise_on_pass = RuntimeError("db down")
    stage = ScreenStage(storage)

    result = await stage.run("client-1")

    assert result.total_eligible == 3
    assert result.total_errored == 3
    assert result.total_passed == 0
    # Loop did not abort after first error
    assert len(storage.passed) == 0


@pytest.mark.asyncio
async def test_screen_stage_logs_summary():
    """Summary entry has all 7 required context keys and correct decision string."""
    storage = FakeStorage(
        config=ICP_CONFIG,
        contacts=[valid_contact(), no_name_contact()],
    )
    stage = ScreenStage(storage)

    await stage.run("client-1")

    summary = next(
        (d for d in storage.decisions if d.get("decision") == "screen_stage_summary"),
        None,
    )
    assert summary is not None
    assert summary["decision_type"] == "icp_threshold"
    assert summary["client_id"] == "client-1"

    ctx = summary["context"]
    required_keys = {
        "client_id", "dry_run", "total_eligible", "total_passed",
        "total_rejected", "total_errored", "rejections_by_reason",
    }
    assert required_keys.issubset(ctx.keys()), f"Missing: {required_keys - ctx.keys()}"


@pytest.mark.asyncio
async def test_screen_stage_empty_contacts():
    """Zero eligible contacts: loop never runs, summary still logged, all counters 0."""
    storage = FakeStorage(config=ICP_CONFIG, contacts=[])
    stage = ScreenStage(storage)

    result = await stage.run("client-1")

    assert result.total_eligible == 0
    assert result.total_passed == 0
    assert result.total_rejected == 0
    assert result.total_errored == 0
    assert len(storage.passed) == 0
    assert len(storage.rejected) == 0
    summary = next(d for d in storage.decisions if d.get("decision") == "screen_stage_summary")
    assert summary is not None


@pytest.mark.asyncio
async def test_screen_stage_rejections_buckets_always_initialized():
    """Empty run: rejections_by_reason has all 4 keys, all 0."""
    storage = FakeStorage(config=ICP_CONFIG, contacts=[])
    stage = ScreenStage(storage)

    result = await stage.run("client-1")

    expected_keys = {"missing_name", "missing_company", "blacklisted_company", "blacklisted_domain"}
    assert set(result.rejections_by_reason.keys()) == expected_keys
    assert all(v == 0 for v in result.rejections_by_reason.values())
