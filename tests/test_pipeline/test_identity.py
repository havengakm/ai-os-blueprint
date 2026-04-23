"""Tests for the identity-lookup pipeline stage (Task 9.5e).

Uses in-memory fakes for both storage and orchestrator — no real adapters needed.
"""
from __future__ import annotations

import pytest

from systems.scout.identity.orchestrator import OrchestratorResult
from systems.scout.identity.base import IdentityResult
from systems.scout.pipeline.identity import (
    ContactRow,
    IdentityStage,
    IdentityStageResult,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeStorage:
    def __init__(self, contacts: list[ContactRow]):
        self.contacts = contacts
        self.updates: list[dict] = []
        self.archives: list[str] = []  # contact_ids
        self.decisions: list[dict] = []
        self.raise_on_update: Exception | None = None
        self.raise_on_archive: Exception | None = None

    async def get_eligible_contacts(self, client_id, *, archive_floor, limit=None):
        filtered = [c for c in self.contacts if c.icp_score >= archive_floor]
        return filtered[:limit] if limit else filtered

    async def update_contact_identity(self, client_id, contact_id, **fields):
        if self.raise_on_update:
            raise self.raise_on_update
        self.updates.append({"contact_id": contact_id, **fields})

    async def archive_contact_no_decision_maker(self, client_id, contact_id):
        if self.raise_on_archive:
            raise self.raise_on_archive
        self.archives.append(contact_id)

    async def log_decision(self, client_id, **kwargs):
        self.decisions.append({"client_id": client_id, **kwargs})


class FakeOrchestrator:
    """Stand-in that returns pre-programmed OrchestratorResult per-company."""

    def __init__(self, results_by_company: dict[str, OrchestratorResult]):
        self.results = results_by_company
        self.calls: list[tuple] = []

    async def resolve(self, client_id, company, company_domain=None, **kwargs):
        self.calls.append((client_id, company, company_domain))
        return self.results.get(
            company,
            OrchestratorResult(
                identity=None, source=None, sources_attempted=[], archived=True
            ),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_identity(source: str = "apollo_people") -> IdentityResult:
    return IdentityResult(
        first_name="Alice",
        last_name="Smith",
        title="CEO",
        email="alice@acme.com",
        linkedin_url="https://linkedin.com/in/alicesmith",
        source=source,
        confidence=0.9,
        sources_attempted=["https://api.apollo.io/v1/people/search"],
    )


def make_hit(source: str = "apollo_people") -> OrchestratorResult:
    return OrchestratorResult(
        identity=make_identity(source),
        source=source,
        sources_attempted=["https://api.apollo.io/v1/people/search"],
        archived=False,
    )


MISS = OrchestratorResult(
    identity=None, source=None, sources_attempted=[], archived=True
)


CLIENT = "client-abc"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stage_resolves_hit_updates_contact():
    contact = ContactRow(
        contact_id="c1", company_name="Acme", company_domain="acme.com", icp_score=50
    )
    storage = FakeStorage([contact])
    orc = FakeOrchestrator({"Acme": make_hit("apollo_people")})
    stage = IdentityStage(orc, storage)

    result = await stage.run(CLIENT)

    assert result.total_resolved == 1
    assert result.total_archived == 0
    assert result.total_errored == 0
    assert result.by_source["apollo_people"] == 1
    assert len(storage.updates) == 1
    assert storage.updates[0]["contact_id"] == "c1"
    assert storage.updates[0]["first_name"] == "Alice"
    assert len(storage.archives) == 0


@pytest.mark.asyncio
async def test_stage_archives_on_miss():
    contact = ContactRow(
        contact_id="c1", company_name="Acme", company_domain="acme.com", icp_score=50
    )
    storage = FakeStorage([contact])
    orc = FakeOrchestrator({"Acme": MISS})
    stage = IdentityStage(orc, storage)

    result = await stage.run(CLIENT)

    assert result.total_resolved == 0
    assert result.total_archived == 1
    assert storage.archives == ["c1"]
    assert len(storage.updates) == 0


@pytest.mark.asyncio
async def test_stage_honours_archive_floor():
    contacts = [
        ContactRow("c1", "Low", None, icp_score=20),
        ContactRow("c2", "Mid", None, icp_score=35),
        ContactRow("c3", "High", None, icp_score=60),
    ]
    storage = FakeStorage(contacts)
    orc = FakeOrchestrator({})
    stage = IdentityStage(orc, storage)  # default floor=35

    result = await stage.run(CLIENT)

    # Only c2 (35) and c3 (60) should be dispatched; c1 (20) excluded
    assert result.total_eligible == 2
    assert len(orc.calls) == 2
    dispatched_companies = {call[1] for call in orc.calls}
    assert dispatched_companies == {"Mid", "High"}


@pytest.mark.asyncio
async def test_stage_custom_archive_floor():
    contacts = [
        ContactRow("c1", "Low", None, icp_score=20),
        ContactRow("c2", "Mid", None, icp_score=35),
        ContactRow("c3", "High", None, icp_score=60),
    ]
    storage = FakeStorage(contacts)
    orc = FakeOrchestrator({})
    stage = IdentityStage(orc, storage, archive_floor=50)

    result = await stage.run(CLIENT)

    assert result.total_eligible == 1
    assert len(orc.calls) == 1
    assert orc.calls[0][1] == "High"


@pytest.mark.asyncio
async def test_stage_dry_run_skips_persistence():
    contact = ContactRow("c1", "Acme", "acme.com", icp_score=50)
    storage = FakeStorage([contact])
    orc = FakeOrchestrator({"Acme": make_hit()})
    stage = IdentityStage(orc, storage)

    result = await stage.run(CLIENT, dry_run=True)

    assert result.dry_run is True
    # Orchestrator still called
    assert len(orc.calls) == 1
    # No persistence
    assert len(storage.updates) == 0
    assert len(storage.archives) == 0
    # Summary decision still logged
    summary_decisions = [d for d in storage.decisions if d.get("decision") == "identity_stage_summary"]
    assert len(summary_decisions) == 1


@pytest.mark.asyncio
async def test_stage_dry_run_still_counts():
    contacts = [
        ContactRow("c1", "Acme", "acme.com", icp_score=50),
        ContactRow("c2", "Beta", "beta.com", icp_score=60),
        ContactRow("c3", "Gamma", "gamma.com", icp_score=40),
    ]
    storage = FakeStorage(contacts)
    orc = FakeOrchestrator({
        "Acme": make_hit("apollo_people"),
        "Beta": MISS,
        "Gamma": make_hit("hunter_domain"),
    })
    stage = IdentityStage(orc, storage)

    result = await stage.run(CLIENT, dry_run=True)

    assert result.total_eligible == 3
    assert result.total_resolved == 2
    assert result.total_archived == 1
    assert result.total_errored == 0
    assert result.dry_run is True


@pytest.mark.asyncio
async def test_stage_mixed_batch():
    contacts = [
        ContactRow("c1", "Alpha", "alpha.com", icp_score=55),
        ContactRow("c2", "Beta", "beta.com", icp_score=60),
        ContactRow("c3", "Gamma", "gamma.com", icp_score=45),
        ContactRow("c4", "Delta", "delta.com", icp_score=70),
        ContactRow("c5", "Epsilon", "eps.com", icp_score=50),
    ]
    storage = FakeStorage(contacts)
    orc = FakeOrchestrator({
        "Alpha": make_hit("apollo_people"),
        "Beta": make_hit("apollo_people"),
        "Gamma": make_hit("hunter_domain"),
        "Delta": MISS,
        "Epsilon": MISS,
    })
    stage = IdentityStage(orc, storage)

    result = await stage.run(CLIENT)

    assert result.total_resolved == 3
    assert result.total_archived == 2
    assert result.total_errored == 0
    assert result.by_source == {"apollo_people": 2, "hunter_domain": 1, "claude_scraper": 0}
    assert len(storage.updates) == 3
    assert len(storage.archives) == 2


@pytest.mark.asyncio
async def test_stage_persistence_error_does_not_abort():
    contacts = [
        ContactRow("c1", "Alpha", "alpha.com", icp_score=50),
        ContactRow("c2", "Beta", "beta.com", icp_score=50),
        ContactRow("c3", "Gamma", "gamma.com", icp_score=50),
    ]
    storage = FakeStorage(contacts)
    storage.raise_on_update = RuntimeError("DB unavailable")
    orc = FakeOrchestrator({
        "Alpha": make_hit(),
        "Beta": make_hit(),
        "Gamma": make_hit(),
    })
    stage = IdentityStage(orc, storage)

    result = await stage.run(CLIENT)

    # All three updates fail, so all three become errors
    assert result.total_errored == 3
    assert result.total_resolved == 0
    # A persist-failure decision was logged for each
    fail_decisions = [
        d for d in storage.decisions
        if str(d.get("decision", "")).startswith("identity_stage:persist_failed:")
    ]
    assert len(fail_decisions) == 3


@pytest.mark.asyncio
async def test_stage_persistence_error_partial():
    """First contact update fails; remaining two still process."""
    contacts = [
        ContactRow("c1", "Alpha", "alpha.com", icp_score=50),
        ContactRow("c2", "Beta", "beta.com", icp_score=50),
        ContactRow("c3", "Gamma", "gamma.com", icp_score=50),
    ]

    class PartialFailStorage(FakeStorage):
        def __init__(self, contacts):
            super().__init__(contacts)
            self._update_call_count = 0

        async def update_contact_identity(self, client_id, contact_id, **fields):
            self._update_call_count += 1
            if self._update_call_count == 1:
                raise RuntimeError("first update fails")
            await super().update_contact_identity(client_id, contact_id, **fields)

    storage = PartialFailStorage(contacts)
    orc = FakeOrchestrator({
        "Alpha": make_hit(),
        "Beta": make_hit(),
        "Gamma": make_hit(),
    })
    stage = IdentityStage(orc, storage)

    result = await stage.run(CLIENT)

    assert result.total_errored == 1
    assert result.total_resolved == 2
    assert len(storage.updates) == 2


@pytest.mark.asyncio
async def test_stage_archive_persistence_error():
    contacts = [
        ContactRow("c1", "Alpha", "alpha.com", icp_score=50),
        ContactRow("c2", "Beta", "beta.com", icp_score=50),
    ]
    storage = FakeStorage(contacts)
    storage.raise_on_archive = RuntimeError("archive write failed")
    orc = FakeOrchestrator({"Alpha": MISS, "Beta": MISS})
    stage = IdentityStage(orc, storage)

    result = await stage.run(CLIENT)

    assert result.total_archived == 0
    assert result.total_errored == 2
    assert len(storage.archives) == 0


@pytest.mark.asyncio
async def test_stage_limit_caps_batch():
    contacts = [
        ContactRow(f"c{i}", f"Company{i}", f"co{i}.com", icp_score=50)
        for i in range(10)
    ]
    storage = FakeStorage(contacts)
    orc = FakeOrchestrator({})
    stage = IdentityStage(orc, storage)

    result = await stage.run(CLIENT, limit=3)

    assert result.total_eligible == 3
    assert len(orc.calls) == 3


@pytest.mark.asyncio
async def test_stage_logs_summary_decision():
    contact = ContactRow("c1", "Acme", "acme.com", icp_score=50)
    storage = FakeStorage([contact])
    orc = FakeOrchestrator({"Acme": make_hit("apollo_people")})
    stage = IdentityStage(orc, storage)

    result = await stage.run(CLIENT)

    summary_decisions = [
        d for d in storage.decisions if d.get("decision") == "identity_stage_summary"
    ]
    assert len(summary_decisions) == 1
    d = summary_decisions[0]
    assert d["decision_type"] == "identity_lookup"
    ctx = d["context"]
    assert ctx["client_id"] == CLIENT
    assert "dry_run" in ctx
    assert "total_eligible" in ctx
    assert "total_resolved" in ctx
    assert "total_archived" in ctx
    assert "total_errored" in ctx
    assert "by_source" in ctx


@pytest.mark.asyncio
async def test_stage_empty_eligible_set():
    storage = FakeStorage([])
    orc = FakeOrchestrator({})
    stage = IdentityStage(orc, storage)

    result = await stage.run(CLIENT)

    assert result.total_eligible == 0
    assert len(orc.calls) == 0
    # Summary still logged
    summary_decisions = [
        d for d in storage.decisions if d.get("decision") == "identity_stage_summary"
    ]
    assert len(summary_decisions) == 1


@pytest.mark.asyncio
async def test_stage_by_source_shape_consistent_even_when_empty():
    storage = FakeStorage([])
    orc = FakeOrchestrator({})
    stage = IdentityStage(orc, storage)

    result = await stage.run(CLIENT)

    assert set(result.by_source.keys()) == {"apollo_people", "hunter_domain", "claude_scraper"}
    assert all(v == 0 for v in result.by_source.values())
