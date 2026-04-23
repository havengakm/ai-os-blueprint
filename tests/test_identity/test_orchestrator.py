"""Tests for IdentityOrchestrator — waterfall dispatch across identity adapters."""
from __future__ import annotations

import pytest

from systems.scout.identity.base import IdentityResult
from systems.scout.identity.orchestrator import IdentityOrchestrator, OrchestratorResult


# ---------------------------------------------------------------------------
# Minimal fakes — no real adapters, no real DB
# ---------------------------------------------------------------------------

class FakeAdapter:
    def __init__(self, name: str, result=None, raises: Exception | None = None):
        self.name = name
        self._result = result
        self._raises = raises
        self.resolve_calls: list[tuple] = []

    async def resolve(self, company, company_domain=None, **kwargs):
        self.resolve_calls.append((company, company_domain, kwargs))
        if self._raises:
            raise self._raises
        return self._result


class FakeLogger:
    def __init__(self):
        self.entries: list[dict] = []

    async def log_decision(self, **kwargs):
        self.entries.append(kwargs)
        return "fake-decision-id"


class ExplodingLogger:
    """Logger whose log_decision always raises — tests waterfall resilience."""
    async def log_decision(self, **kwargs):
        raise RuntimeError("logger exploded")


def _make_result(source: str, sources_attempted: list[str] | None = None) -> IdentityResult:
    return IdentityResult(
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        title="CEO",
        source=source,
        confidence=0.9,
        sources_attempted=sources_attempted or [],
    )


# ---------------------------------------------------------------------------
# 1. First adapter hits — rest never called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_returns_first_hit():
    apollo_result = _make_result("apollo_people", ["https://api.apollo.io/v1/mixed_people/search"])
    apollo = FakeAdapter("apollo_people", result=apollo_result)
    hunter = FakeAdapter("hunter_domain")
    claude = FakeAdapter("claude_scraper")

    orch = IdentityOrchestrator(adapters=[apollo, hunter, claude])
    result = await orch.resolve("client-1", "Acme Corp", "acme.com")

    assert isinstance(result, OrchestratorResult)
    assert result.identity is apollo_result
    assert result.source == "apollo_people"
    assert result.archived is False
    assert len(hunter.resolve_calls) == 0
    assert len(claude.resolve_calls) == 0


# ---------------------------------------------------------------------------
# 2. Apollo misses → Hunter hits
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_falls_through_to_hunter():
    hunter_result = _make_result("hunter_domain")
    apollo = FakeAdapter("apollo_people", result=None)
    hunter = FakeAdapter("hunter_domain", result=hunter_result)
    claude = FakeAdapter("claude_scraper")

    orch = IdentityOrchestrator(adapters=[apollo, hunter, claude])
    result = await orch.resolve("client-1", "Acme Corp", "acme.com")

    assert result.identity is hunter_result
    assert result.source == "hunter_domain"
    assert result.archived is False
    assert len(apollo.resolve_calls) == 1
    assert len(hunter.resolve_calls) == 1
    assert len(claude.resolve_calls) == 0


# ---------------------------------------------------------------------------
# 3. Apollo + Hunter miss → Claude hits
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_falls_through_to_claude():
    claude_result = _make_result("claude_scraper")
    apollo = FakeAdapter("apollo_people", result=None)
    hunter = FakeAdapter("hunter_domain", result=None)
    claude = FakeAdapter("claude_scraper", result=claude_result)

    orch = IdentityOrchestrator(adapters=[apollo, hunter, claude])
    result = await orch.resolve("client-1", "Acme Corp", "acme.com")

    assert result.identity is claude_result
    assert result.source == "claude_scraper"
    assert result.archived is False
    assert len(apollo.resolve_calls) == 1
    assert len(hunter.resolve_calls) == 1
    assert len(claude.resolve_calls) == 1


# ---------------------------------------------------------------------------
# 4. All miss → archived=True; 6 (combined). Archive log entry logged.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_archives_when_all_miss_and_logs_archive():
    apollo = FakeAdapter("apollo_people", result=None)
    hunter = FakeAdapter("hunter_domain", result=None)
    claude = FakeAdapter("claude_scraper", result=None)
    log = FakeLogger()

    orch = IdentityOrchestrator(adapters=[apollo, hunter, claude], decision_logger=log)
    result = await orch.resolve("client-1", "Acme Corp", "acme.com")

    # Result shape
    assert result.identity is None
    assert result.source is None
    assert result.archived is True
    assert result.sources_attempted == []

    # Archive log entry is the 4th entry (after 3 per-adapter entries)
    assert len(log.entries) == 4
    archive_entry = log.entries[3]
    assert archive_entry["decision"] == "identity_lookup:archive_no_decision_maker"
    assert archive_entry["decision_type"] == "identity_lookup"
    assert "sources_attempted" in archive_entry["context"]
    assert "adapters_called" in archive_entry["context"]


# ---------------------------------------------------------------------------
# 5. Per-adapter log entries are correct
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_logs_per_adapter_call():
    apollo = FakeAdapter("apollo_people", result=None)
    hunter = FakeAdapter("hunter_domain", result=None)
    claude = FakeAdapter("claude_scraper", result=None)
    log = FakeLogger()

    orch = IdentityOrchestrator(adapters=[apollo, hunter, claude], decision_logger=log)
    await orch.resolve("client-1", "Acme Corp", "acme.com")

    # 3 per-adapter + 1 archive = 4 total; pick first 3
    per_adapter = log.entries[:3]
    decisions = [e["decision"] for e in per_adapter]

    assert "identity_lookup:apollo_people:miss" in decisions
    assert "identity_lookup:hunter_domain:miss" in decisions
    assert "identity_lookup:claude_scraper:miss" in decisions

    for entry in per_adapter:
        assert entry["decision_type"] == "identity_lookup"
        assert entry["source"] == "system"


# ---------------------------------------------------------------------------
# 7. Adapter raises → waterfall continues; exception logged as miss
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_swallows_adapter_exceptions():
    import httpx

    hunter_result = _make_result("hunter_domain")
    apollo = FakeAdapter("apollo_people", raises=httpx.HTTPError("connection refused"))
    hunter = FakeAdapter("hunter_domain", result=hunter_result)
    log = FakeLogger()

    orch = IdentityOrchestrator(adapters=[apollo, hunter], decision_logger=log)
    result = await orch.resolve("client-1", "Acme Corp", "acme.com")

    assert result.identity is hunter_result
    assert result.archived is False

    # Apollo exception must be recorded as a miss
    apollo_entry = log.entries[0]
    assert "apollo_people" in apollo_entry["decision"]
    assert "HTTPError" in apollo_entry["reasoning"]


# ---------------------------------------------------------------------------
# 8. Logger raises → waterfall still works
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_swallows_logger_exceptions():
    apollo_result = _make_result("apollo_people")
    apollo = FakeAdapter("apollo_people", result=apollo_result)

    orch = IdentityOrchestrator(adapters=[apollo], decision_logger=ExplodingLogger())
    result = await orch.resolve("client-1", "Acme Corp", "acme.com")

    assert result.identity is apollo_result
    assert result.archived is False


# ---------------------------------------------------------------------------
# 9. Custom order — Claude first, Apollo second; Hunter skipped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_order_can_be_customized():
    apollo_result = _make_result("apollo_people")
    apollo = FakeAdapter("apollo_people", result=apollo_result)
    hunter = FakeAdapter("hunter_domain", result=_make_result("hunter_domain"))
    claude = FakeAdapter("claude_scraper", result=None)

    orch = IdentityOrchestrator(
        adapters=[apollo, hunter, claude],
        order=("claude_scraper", "apollo_people"),
    )
    result = await orch.resolve("client-1", "Acme Corp", "acme.com")

    # Claude called first (miss), then Apollo (hit)
    assert len(claude.resolve_calls) == 1
    assert len(apollo.resolve_calls) == 1
    assert len(hunter.resolve_calls) == 0
    assert result.source == "apollo_people"


# ---------------------------------------------------------------------------
# 10. Missing adapter name in order → no error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_handles_missing_adapters_silently():
    apollo_result = _make_result("apollo_people")
    apollo = FakeAdapter("apollo_people", result=apollo_result)

    orch = IdentityOrchestrator(
        adapters=[apollo],
        order=("nonexistent_adapter", "apollo_people"),
    )
    result = await orch.resolve("client-1", "Acme Corp", "acme.com")

    assert result.identity is apollo_result
    assert result.archived is False


# ---------------------------------------------------------------------------
# 11. No logger provided — no crash
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_works_without_logger():
    apollo_result = _make_result("apollo_people")
    apollo = FakeAdapter("apollo_people", result=apollo_result)

    orch = IdentityOrchestrator(adapters=[apollo], decision_logger=None)
    result = await orch.resolve("client-1", "Acme Corp", "acme.com")

    assert result.identity is apollo_result
    assert result.archived is False


# ---------------------------------------------------------------------------
# 12. sources_attempted aggregated from winning adapter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_aggregates_sources_attempted_on_hit():
    url = "https://api.apollo.io/v1/mixed_people/search"
    apollo_result = _make_result("apollo_people", sources_attempted=[url])
    apollo = FakeAdapter("apollo_people", result=apollo_result)

    orch = IdentityOrchestrator(adapters=[apollo])
    result = await orch.resolve("client-1", "Acme Corp", "acme.com")

    assert url in result.sources_attempted


# ---------------------------------------------------------------------------
# 13. All miss → sources_attempted == []
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_uses_empty_sources_list_when_all_miss():
    apollo = FakeAdapter("apollo_people", result=None)
    hunter = FakeAdapter("hunter_domain", result=None)

    orch = IdentityOrchestrator(adapters=[apollo, hunter])
    result = await orch.resolve("client-1", "Acme Corp", "acme.com")

    assert result.sources_attempted == []
    assert result.archived is True


# ---------------------------------------------------------------------------
# 14. Empty adapters list → archived=True immediately
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_handles_empty_adapters():
    log = FakeLogger()
    orch = IdentityOrchestrator(adapters=[], decision_logger=log)
    result = await orch.resolve("client-1", "Acme Corp", "acme.com")

    assert result.identity is None
    assert result.source is None
    assert result.archived is True
    assert result.sources_attempted == []
    # Archive log entry still emitted
    assert len(log.entries) == 1
    assert log.entries[0]["decision"] == "identity_lookup:archive_no_decision_maker"
