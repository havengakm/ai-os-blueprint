from unittest.mock import AsyncMock

import pytest

from systems.scout.pipeline.pull import (
    PullOrchestrator,
    PullResult,
    SourceSummary,
)
from systems.scout.sources.base import RawCompanyContact


class _FakeStorage:
    """In-memory fake implementing the StorageBackend Protocol."""

    def __init__(self, active: list[str], existing_contacts=None) -> None:
        self.active = active
        self.existing = existing_contacts or []  # list of (source, source_id, domain) tuples
        self.inserted: list[RawCompanyContact] = []
        self.decisions: list[dict] = []

    async def get_active_directories(self, client_id: str) -> list[str]:
        return list(self.active)

    async def contact_exists(self, client_id, *, source=None, source_id=None, company_domain=None) -> bool:
        for src, sid, dom in self.existing:
            if source is not None and source_id is not None and src == source and sid == source_id:
                return True
            if company_domain and dom and dom == company_domain:
                return True
        return False

    async def insert_contact(self, client_id, contact) -> None:
        self.inserted.append(contact)

    async def log_decision(self, client_id, *, decision_type, decision, context, reasoning=None, confidence=None) -> None:
        self.decisions.append({
            "decision_type": decision_type,
            "decision": decision,
            "reasoning": reasoning,
            "context": context,
            "confidence": confidence,
        })


def _adapter(name: str, rows: list[RawCompanyContact]):
    """Build a mock adapter whose name property matches and .pull() returns the given rows."""
    mock = AsyncMock()
    mock.configure_mock(name=name)
    mock.pull.return_value = rows
    return mock


def _by_name(*adapters):
    """Build the routing-key dict the orchestrator expects, using each
    adapter's own ``.name`` as the key. Matches what these tests' fake
    ``_FakeStorage(active=[...])`` references — adapter.name and the
    routing key are intentionally identical in the unit tests; production
    factory code is the path that decouples them (see
    ``test_build_pull_adapters_clutch_routing_key_separate_from_adapter_name``)."""
    return {a.name: a for a in adapters}


def _row(company, *, source, source_id, domain=None):
    return RawCompanyContact(
        company=company,
        company_domain=domain,
        source=source,
        source_id=source_id,
    )


@pytest.mark.asyncio
async def test_orchestrator_dispatches_only_active_adapters():
    csv_adapter = _adapter("csv_ingest", [_row("A", source="csv_ingest", source_id="1", domain="a.com")])
    apollo = _adapter("apollo_company", [_row("B", source="apollo_company", source_id="org-1", domain="b.com")])
    clutch = _adapter("clutch:developers/shopify", [_row("C", source="clutch:developers/shopify", source_id="c", domain="c.com")])

    storage = _FakeStorage(active=["csv_ingest", "apollo_company"])  # clutch not active
    orch = PullOrchestrator(_by_name(csv_adapter, apollo, clutch), storage)
    result = await orch.run("clymb")

    assert result.total_inserted == 2  # csv + apollo; clutch skipped
    assert {s.adapter_name for s in result.per_source} == {"csv_ingest", "apollo_company"}
    clutch.pull.assert_not_called()


@pytest.mark.asyncio
async def test_orchestrator_respects_construction_order():
    csv_adapter = _adapter("csv_ingest", [])
    apollo = _adapter("apollo_company", [])
    storage = _FakeStorage(active=["apollo_company", "csv_ingest"])  # storage lists apollo first
    orch = PullOrchestrator(_by_name(csv_adapter, apollo), storage)  # construction order: csv first
    result = await orch.run("clymb")

    # per_source order follows construction order, not storage order
    assert [s.adapter_name for s in result.per_source] == ["csv_ingest", "apollo_company"]


@pytest.mark.asyncio
async def test_orchestrator_dedups_by_domain_across_sources():
    csv_adapter = _adapter("csv_ingest", [_row("Acme", source="csv_ingest", source_id="1", domain="acme.com")])
    apollo = _adapter("apollo_company", [_row("Acme", source="apollo_company", source_id="org-2", domain="acme.com")])

    storage = _FakeStorage(active=["csv_ingest", "apollo_company"])
    orch = PullOrchestrator(_by_name(csv_adapter, apollo), storage)
    result = await orch.run("clymb")

    # Both adapters pulled 1, but apollo's row should be deduped by domain
    assert result.total_pulled == 2
    assert result.total_inserted == 1
    assert result.total_skipped_duplicate == 1
    assert len(storage.inserted) == 1


@pytest.mark.asyncio
async def test_orchestrator_dedups_against_existing_contacts():
    csv_adapter = _adapter("csv_ingest", [_row("Acme", source="csv_ingest", source_id="1", domain="acme.com")])
    storage = _FakeStorage(
        active=["csv_ingest"],
        existing_contacts=[("csv_ingest", "1", "acme.com")],  # already in DB
    )
    orch = PullOrchestrator(_by_name(csv_adapter), storage)
    result = await orch.run("clymb")

    assert result.total_inserted == 0
    assert result.total_skipped_duplicate == 1


@pytest.mark.asyncio
async def test_orchestrator_dry_run_does_not_persist():
    csv_adapter = _adapter("csv_ingest", [_row("Acme", source="csv_ingest", source_id="1", domain="acme.com")])
    storage = _FakeStorage(active=["csv_ingest"])
    orch = PullOrchestrator(_by_name(csv_adapter), storage)
    result = await orch.run("clymb", dry_run=True)

    assert result.dry_run is True
    assert result.total_inserted == 1  # counted as would-be insert
    assert len(storage.inserted) == 0  # but nothing persisted
    # Adapter got dry_run=True forwarded
    assert csv_adapter.pull.await_args.kwargs["dry_run"] is True


@pytest.mark.asyncio
async def test_orchestrator_source_filter_narrows_active_set():
    csv_adapter = _adapter("csv_ingest", [])
    apollo = _adapter("apollo_company", [])
    storage = _FakeStorage(active=["csv_ingest", "apollo_company"])
    orch = PullOrchestrator(_by_name(csv_adapter, apollo), storage)

    await orch.run("clymb", source_filter=["csv_ingest"])
    assert csv_adapter.pull.await_count == 1
    apollo.pull.assert_not_called()


@pytest.mark.asyncio
async def test_orchestrator_forwards_adapter_kwargs():
    csv_adapter = _adapter("csv_ingest", [])
    storage = _FakeStorage(active=["csv_ingest"])
    orch = PullOrchestrator(_by_name(csv_adapter), storage)

    await orch.run(
        "clymb",
        adapter_kwargs={"csv_ingest": {"csv_content": "Company Name\nFoo"}},
    )

    csv_adapter.pull.assert_awaited_once()
    kwargs = csv_adapter.pull.await_args.kwargs
    assert kwargs["csv_content"] == "Company Name\nFoo"
    assert kwargs["client_id"] == "clymb"


@pytest.mark.asyncio
async def test_orchestrator_logs_when_adapter_not_registered():
    storage = _FakeStorage(active=["ghost_adapter"])
    orch = PullOrchestrator({}, storage)
    result = await orch.run("clymb")

    assert result.total_inserted == 0
    assert any(
        d["decision"] == "source_adapter_not_registered"
        for d in storage.decisions
    )


@pytest.mark.asyncio
async def test_orchestrator_captures_adapter_errors_and_continues():
    failing = _adapter("csv_ingest", [])
    failing.pull.side_effect = RuntimeError("boom")
    ok = _adapter("apollo_company", [_row("ok", source="apollo_company", source_id="1", domain="ok.com")])

    storage = _FakeStorage(active=["csv_ingest", "apollo_company"])
    orch = PullOrchestrator(_by_name(failing, ok), storage)
    result = await orch.run("clymb")

    failing_summary = next(s for s in result.per_source if s.adapter_name == "csv_ingest")
    ok_summary = next(s for s in result.per_source if s.adapter_name == "apollo_company")
    assert failing_summary.error and "boom" in failing_summary.error
    assert ok_summary.inserted == 1  # sibling adapter still runs


@pytest.mark.asyncio
async def test_orchestrator_logs_summary_decision_per_source():
    csv_adapter = _adapter("csv_ingest", [_row("Acme", source="csv_ingest", source_id="1", domain="acme.com")])
    storage = _FakeStorage(active=["csv_ingest"])
    orch = PullOrchestrator(_by_name(csv_adapter), storage)

    await orch.run("clymb")

    assert any(
        d["decision"] == "source_adapter_pulled" and d["context"]["adapter_name"] == "csv_ingest"
        for d in storage.decisions
    )


@pytest.mark.asyncio
async def test_orchestrator_dedups_null_domain_rows_with_same_company():
    """C1 regression — two Clutch-style rows with null domain but different source_ids
    but same underlying company must dedup within a run."""
    clutch_a = _adapter("clutch:developers/shopify", [
        _row("Acme Co", source="clutch:developers/shopify", source_id="shopify-acme", domain=None),
    ])
    clutch_b = _adapter("clutch:developers/wordpress", [
        _row("Acme Co", source="clutch:developers/wordpress", source_id="wp-acme", domain=None),
    ])
    storage = _FakeStorage(active=["clutch:developers/shopify", "clutch:developers/wordpress"])
    orch = PullOrchestrator(_by_name(clutch_a, clutch_b), storage)
    result = await orch.run("clymb")

    assert result.total_pulled == 2
    assert result.total_inserted == 1  # second was deduped by company name
    assert result.total_skipped_duplicate == 1
