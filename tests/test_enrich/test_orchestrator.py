"""Tests for EnrichOrchestrator — tier-gated fan-out dispatch across
enrichment adapters."""
from __future__ import annotations

from typing import Any

import pytest

from systems.scout.enrich.base import EnrichResult
from systems.scout.enrich.orchestrator import (
    TIER_ADAPTERS,
    EnrichOrchestrator,
    EnrichOrchestratorResult,
)


# --------------------------------------------------------------------------- #
# Minimal fakes — no real adapters, no real DB, no real budget backend          #
# --------------------------------------------------------------------------- #

class FakeEnrichAdapter:
    """Fake adapter honouring the EnrichAdapter protocol."""

    def __init__(
        self,
        name: str,
        cost_cents_per_call: int = 1,
        result: EnrichResult | None = None,
        raises: Exception | None = None,
        call_log: list[str] | None = None,
    ) -> None:
        self.name = name
        self.cost_cents_per_call = cost_cents_per_call
        # If no explicit result was provided, synthesise a default matching the
        # adapter's declared cost. Tests may also inject their own EnrichResult
        # to exercise cost/reason variations.
        self._result = result if result is not None else EnrichResult(
            adapter_name=name,
            ok=True,
            data={},
            cost_cents=cost_cents_per_call,
            reason="ok",
        )
        self._raises = raises
        self._call_log = call_log  # shared cross-adapter ordering log
        self.enrich_calls: list[dict[str, Any]] = []

    async def enrich(self, contact: dict[str, Any], *, dry_run: bool = False) -> EnrichResult:
        self.enrich_calls.append({"contact": contact, "dry_run": dry_run})
        if self._call_log is not None:
            self._call_log.append(self.name)
        if self._raises:
            raise self._raises
        return self._result


class FakeBudgetTracker:
    """In-memory budget tracker.

    Starts with `initial_cents` for every (client_id, tier) pair unless
    overridden via per_tier. Debits on record_spend(). Raises on
    remaining_cents() only when `raise_on_remaining` is set (for tests
    that exercise budget-tracker failures)."""

    def __init__(
        self,
        initial_cents: int = 100,
        per_tier: dict[str, int] | None = None,
        raise_on_remaining: Exception | None = None,
        raise_on_record: Exception | None = None,
    ) -> None:
        self._initial = initial_cents
        self._balances: dict[tuple[str, str], int] = {}
        if per_tier:
            for tier, cents in per_tier.items():
                self._balances[("client-1", tier)] = cents
        self._raise_on_remaining = raise_on_remaining
        self._raise_on_record = raise_on_record
        self.remaining_calls: list[tuple[str, str]] = []
        self.record_calls: list[tuple[str, str, int]] = []

    async def remaining_cents(self, client_id: str, tier: str) -> int:
        self.remaining_calls.append((client_id, tier))
        if self._raise_on_remaining:
            raise self._raise_on_remaining
        return self._balances.setdefault((client_id, tier), self._initial)

    async def record_spend(self, client_id: str, tier: str, cents: int) -> None:
        self.record_calls.append((client_id, tier, cents))
        if self._raise_on_record:
            raise self._raise_on_record
        self._balances[(client_id, tier)] = (
            self._balances.get((client_id, tier), self._initial) - cents
        )


class FakeLogger:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    async def log_decision(self, **kwargs) -> str:
        self.entries.append(kwargs)
        return "fake-decision-id"


class ExplodingLogger:
    """Logger whose log_decision always raises — tests fan-out resilience."""

    async def log_decision(self, **kwargs) -> str:
        raise RuntimeError("logger exploded")


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _contact(contact_id: str = "c-1") -> dict[str, Any]:
    return {"contact_id": contact_id, "email": "jane@acme.com"}


def _make_tier_a_adapters(call_log: list[str] | None = None) -> list[FakeEnrichAdapter]:
    """Build fakes for every tier-A adapter name with realistic cost costs."""
    costs = {
        "zerobounce": 1,
        "trigify": 0,
        "claude_web_triggers": 5,
        "apollo_enrich": 1,
        "claude_deep_research": 3,
    }
    return [
        FakeEnrichAdapter(name=name, cost_cents_per_call=cost, call_log=call_log)
        for name, cost in costs.items()
    ]


# --------------------------------------------------------------------------- #
# 1. Happy path, tier A — all 5 adapters run                                    #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_tier_a_runs_all_five_adapters_and_merges_results():
    adapters = _make_tier_a_adapters()
    budget = FakeBudgetTracker(initial_cents=100)
    log = FakeLogger()

    orch = EnrichOrchestrator(adapters=adapters, budget_tracker=budget, decision_logger=log)
    result = await orch.enrich_contact("client-1", _contact(), tier="A")

    assert isinstance(result, EnrichOrchestratorResult)
    assert result.tier == "A"
    assert result.contact_id == "c-1"
    assert set(result.adapter_results.keys()) == {
        "zerobounce", "trigify", "claude_web_triggers", "apollo_enrich", "claude_deep_research",
    }
    # total = 1 + 0 + 5 + 1 + 3 = 10
    assert result.total_cost_cents == 10
    assert result.budget_exhausted is False
    assert result.skipped == {}


# --------------------------------------------------------------------------- #
# 2. Tier D — only zerobounce + claude_research run                             #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_tier_d_runs_only_zerobounce_and_claude_research():
    zb = FakeEnrichAdapter("zerobounce", cost_cents_per_call=1)
    cr = FakeEnrichAdapter("claude_research", cost_cents_per_call=1)
    trigify = FakeEnrichAdapter("trigify", cost_cents_per_call=0)
    apollo = FakeEnrichAdapter("apollo_enrich", cost_cents_per_call=1)
    deep = FakeEnrichAdapter("claude_deep_research", cost_cents_per_call=3)
    web = FakeEnrichAdapter("claude_web_triggers", cost_cents_per_call=5)

    orch = EnrichOrchestrator(
        adapters=[zb, cr, trigify, apollo, deep, web],
        budget_tracker=FakeBudgetTracker(initial_cents=100),
    )
    result = await orch.enrich_contact("client-1", _contact(), tier="D")

    assert set(result.adapter_results.keys()) == {"zerobounce", "claude_research"}
    assert len(zb.enrich_calls) == 1
    assert len(cr.enrich_calls) == 1
    assert len(trigify.enrich_calls) == 0
    assert len(apollo.enrich_calls) == 0
    assert len(deep.enrich_calls) == 0
    assert len(web.enrich_calls) == 0


# --------------------------------------------------------------------------- #
# 3. Unknown tier — empty results + unknown_tier skip + single log entry        #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_unknown_tier_skips_all_adapters_and_logs_once():
    adapters = _make_tier_a_adapters()
    budget = FakeBudgetTracker(initial_cents=100)
    log = FakeLogger()

    orch = EnrichOrchestrator(adapters=adapters, budget_tracker=budget, decision_logger=log)
    result = await orch.enrich_contact("client-1", _contact(), tier="Z")

    assert result.adapter_results == {}
    assert result.total_cost_cents == 0
    assert result.budget_exhausted is False
    # Every supplied adapter is marked skipped with unknown_tier reason.
    assert set(result.skipped.keys()) == {a.name for a in adapters}
    assert all(reason == "unknown_tier" for reason in result.skipped.values())

    # No adapter was ever called.
    for a in adapters:
        assert a.enrich_calls == []

    # Exactly one decision_log entry — unknown_tier notice.
    assert len(log.entries) == 1
    assert log.entries[0]["decision"] == "enrich_contact:unknown_tier"
    assert log.entries[0]["decision_type"] == "enrichment_choice"


# --------------------------------------------------------------------------- #
# 4. Budget exhausted mid-dispatch — 2 run, 3rd hits cap, remaining skipped     #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_budget_exhausted_mid_dispatch_skips_remaining_with_single_log():
    # Tier-A order: zerobounce(1) → trigify(0) → claude_web_triggers(5) →
    # apollo_enrich(1) → claude_deep_research(3)
    #
    # Give budget = 2. zerobounce(1) spends → remaining=1. trigify(0) runs → 1.
    # claude_web_triggers costs 5 > 1 → budget_exhausted; remaining 2 skipped.
    adapters = _make_tier_a_adapters()
    budget = FakeBudgetTracker(per_tier={"A": 2})
    log = FakeLogger()

    orch = EnrichOrchestrator(adapters=adapters, budget_tracker=budget, decision_logger=log)
    result = await orch.enrich_contact("client-1", _contact(), tier="A")

    assert result.budget_exhausted is True
    assert set(result.adapter_results.keys()) == {"zerobounce", "trigify"}
    # The remaining 3 adapters are all marked budget_exhausted.
    assert result.skipped == {
        "claude_web_triggers": "budget_exhausted",
        "apollo_enrich": "budget_exhausted",
        "claude_deep_research": "budget_exhausted",
    }
    # Cost tally: 1 (zerobounce) + 0 (trigify) = 1.
    assert result.total_cost_cents == 1

    # Exactly ONE budget_exhausted log entry, plus per-adapter logs for the
    # two that ran.
    budget_exhausted_entries = [
        e for e in log.entries if e["decision"].endswith(":budget_exhausted")
    ]
    assert len(budget_exhausted_entries) == 1
    assert budget_exhausted_entries[0]["decision"] == "enrich_contact:A:budget_exhausted"
    assert budget_exhausted_entries[0]["context"]["first_skipped_adapter"] == "claude_web_triggers"


# --------------------------------------------------------------------------- #
# 5. Zero-cost adapter keeps running when budget exhausted                      #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_zero_cost_adapter_runs_even_when_budget_is_zero():
    # Custom tier order: trigify (cost=0) first, then zerobounce (cost=1).
    # Budget = 0. Trigify should run (0 < 0 is False). Zerobounce should be
    # skipped (0 < 1 is True).
    trigify = FakeEnrichAdapter("trigify", cost_cents_per_call=0)
    zb = FakeEnrichAdapter("zerobounce", cost_cents_per_call=1)
    budget = FakeBudgetTracker(per_tier={"TEST": 0})
    log = FakeLogger()

    orch = EnrichOrchestrator(
        adapters=[trigify, zb],
        budget_tracker=budget,
        decision_logger=log,
        tier_adapters={"TEST": ["trigify", "zerobounce"]},
    )
    result = await orch.enrich_contact("client-1", _contact(), tier="TEST")

    assert "trigify" in result.adapter_results
    assert "zerobounce" not in result.adapter_results
    assert result.skipped == {"zerobounce": "budget_exhausted"}
    assert result.budget_exhausted is True
    assert len(trigify.enrich_calls) == 1
    assert len(zb.enrich_calls) == 0


# --------------------------------------------------------------------------- #
# 6. Adapter raises — fan-out continues, failed adapter logged & skipped        #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_adapter_exception_does_not_abort_fan_out():
    import httpx

    zb = FakeEnrichAdapter("zerobounce", cost_cents_per_call=1)
    trigify = FakeEnrichAdapter(
        "trigify", cost_cents_per_call=0, raises=httpx.HTTPError("boom")
    )
    web = FakeEnrichAdapter("claude_web_triggers", cost_cents_per_call=5)
    apollo = FakeEnrichAdapter("apollo_enrich", cost_cents_per_call=1)
    deep = FakeEnrichAdapter("claude_deep_research", cost_cents_per_call=3)

    budget = FakeBudgetTracker(initial_cents=100)
    log = FakeLogger()

    orch = EnrichOrchestrator(
        adapters=[zb, trigify, web, apollo, deep],
        budget_tracker=budget,
        decision_logger=log,
    )
    result = await orch.enrich_contact("client-1", _contact(), tier="A")

    # Trigify is not in adapter_results and is skipped with adapter_error reason.
    assert "trigify" not in result.adapter_results
    assert result.skipped == {"trigify": "adapter_error:HTTPError"}
    # Others still ran.
    assert {"zerobounce", "claude_web_triggers", "apollo_enrich", "claude_deep_research"} <= \
        set(result.adapter_results.keys())

    # Trigify exception was logged.
    failure_entries = [
        e for e in log.entries if e["decision"] == "enrich_contact:trigify:adapter_error:HTTPError"
    ]
    assert len(failure_entries) == 1


# --------------------------------------------------------------------------- #
# 7. Exploding logger — orchestrator still returns a valid result               #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_exploding_logger_does_not_break_orchestrator():
    import httpx

    # Cover every code path that writes to the logger: adapter call (tier-A has
    # multiple successful adapters), adapter error, and budget exhaustion.
    # Tier A. Budget 2 so claude_web_triggers triggers budget_exhausted.
    zb = FakeEnrichAdapter("zerobounce", cost_cents_per_call=1)
    trigify = FakeEnrichAdapter(
        "trigify", cost_cents_per_call=0, raises=httpx.HTTPError("boom")
    )
    web = FakeEnrichAdapter("claude_web_triggers", cost_cents_per_call=5)
    apollo = FakeEnrichAdapter("apollo_enrich", cost_cents_per_call=1)
    deep = FakeEnrichAdapter("claude_deep_research", cost_cents_per_call=3)
    budget = FakeBudgetTracker(per_tier={"A": 2})

    orch = EnrichOrchestrator(
        adapters=[zb, trigify, web, apollo, deep],
        budget_tracker=budget,
        decision_logger=ExplodingLogger(),
    )
    result = await orch.enrich_contact("client-1", _contact(), tier="A")

    # Despite every log call exploding, the orchestrator returned a coherent result.
    assert "zerobounce" in result.adapter_results
    assert "trigify" in result.skipped
    assert result.skipped["trigify"] == "adapter_error:HTTPError"
    assert result.budget_exhausted is True

    # Also test unknown_tier path with exploding logger.
    orch2 = EnrichOrchestrator(
        adapters=[zb],
        budget_tracker=FakeBudgetTracker(initial_cents=100),
        decision_logger=ExplodingLogger(),
    )
    result2 = await orch2.enrich_contact("client-1", _contact(), tier="Z")
    assert result2.skipped == {"zerobounce": "unknown_tier"}


# --------------------------------------------------------------------------- #
# 8. Order respected — call log verifies tier-A adapter ordering                #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_adapter_dispatch_order_matches_tier_adapters_ordering():
    call_log: list[str] = []
    adapters = _make_tier_a_adapters(call_log=call_log)

    orch = EnrichOrchestrator(
        adapters=adapters,
        budget_tracker=FakeBudgetTracker(initial_cents=100),
    )
    await orch.enrich_contact("client-1", _contact(), tier="A")

    assert call_log == TIER_ADAPTERS["A"]
    # signal adapters (trigify, claude_web_triggers) before heavy research
    assert call_log.index("trigify") < call_log.index("claude_deep_research")
    assert call_log.index("claude_web_triggers") < call_log.index("claude_deep_research")


# --------------------------------------------------------------------------- #
# 9. dry_run propagated to every adapter call                                   #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_dry_run_flag_propagated_to_all_adapters():
    adapters = _make_tier_a_adapters()
    orch = EnrichOrchestrator(
        adapters=adapters,
        budget_tracker=FakeBudgetTracker(initial_cents=100),
    )
    await orch.enrich_contact("client-1", _contact(), tier="A", dry_run=True)

    for a in adapters:
        assert len(a.enrich_calls) == 1
        assert a.enrich_calls[0]["dry_run"] is True


# --------------------------------------------------------------------------- #
# 10. record_spend called only on successful calls, for the exact cost          #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_record_spend_called_only_on_successful_calls_with_exact_cost():
    # Zerobounce succeeds (cost 1), trigify raises (cost 0), claude_web_triggers
    # succeeds (cost 5). apollo_enrich + claude_deep_research also succeed.
    zb = FakeEnrichAdapter("zerobounce", cost_cents_per_call=1)
    trigify = FakeEnrichAdapter(
        "trigify", cost_cents_per_call=0, raises=RuntimeError("nope")
    )
    web = FakeEnrichAdapter("claude_web_triggers", cost_cents_per_call=5)
    apollo = FakeEnrichAdapter("apollo_enrich", cost_cents_per_call=1)
    deep = FakeEnrichAdapter("claude_deep_research", cost_cents_per_call=3)
    budget = FakeBudgetTracker(initial_cents=100)

    orch = EnrichOrchestrator(
        adapters=[zb, trigify, web, apollo, deep],
        budget_tracker=budget,
    )
    await orch.enrich_contact("client-1", _contact(), tier="A")

    # record_spend calls: zb (1), web (5), apollo (1), deep (3). No trigify entry
    # because it raised. Also no entry for any cost=0 successful call (trigify
    # didn't succeed anyway, but the rule is enforced in the orchestrator too).
    spend_by_adapter = [(t, c) for (_, t, c) in budget.record_calls]
    # All recorded spends were against tier A.
    assert all(t == "A" for t, _ in spend_by_adapter)
    spent_amounts = sorted(c for _, c in spend_by_adapter)
    assert spent_amounts == [1, 1, 3, 5]


# --------------------------------------------------------------------------- #
# Extra edge: zero-cost successful adapter does NOT trigger record_spend         #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_zero_cost_successful_adapter_does_not_call_record_spend():
    trigify = FakeEnrichAdapter("trigify", cost_cents_per_call=0)
    budget = FakeBudgetTracker(initial_cents=100)

    orch = EnrichOrchestrator(
        adapters=[trigify],
        budget_tracker=budget,
        tier_adapters={"X": ["trigify"]},
    )
    result = await orch.enrich_contact("client-1", _contact(), tier="X")

    assert "trigify" in result.adapter_results
    # record_spend was NOT called for the zero-cost success.
    assert budget.record_calls == []


# --------------------------------------------------------------------------- #
# Extra edge: adapter listed in tier but not supplied is marked not_supplied    #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_tier_adapter_missing_from_supplied_list_marked_not_supplied():
    # Tier A expects five adapters; only supply two.
    zb = FakeEnrichAdapter("zerobounce", cost_cents_per_call=1)
    trigify = FakeEnrichAdapter("trigify", cost_cents_per_call=0)
    log = FakeLogger()

    orch = EnrichOrchestrator(
        adapters=[zb, trigify],
        budget_tracker=FakeBudgetTracker(initial_cents=100),
        decision_logger=log,
    )
    result = await orch.enrich_contact("client-1", _contact(), tier="A")

    assert set(result.adapter_results.keys()) == {"zerobounce", "trigify"}
    assert result.skipped == {
        "claude_web_triggers": "not_supplied",
        "apollo_enrich": "not_supplied",
        "claude_deep_research": "not_supplied",
    }
    # No log entries for not_supplied — config mismatch is the stage layer's
    # responsibility to surface. Only the two successful adapter calls are
    # logged.
    not_supplied_entries = [
        e for e in log.entries if "not_supplied" in e["decision"]
    ]
    assert not_supplied_entries == []
