"""Plan 2 Phase 4 Task 2.4.1: signal-gated Deep Research tests.

Per ``feedback_plan15_cost_optimizations``: ``claude_deep_research``
runs ONLY when prior adapters did not surface a buying signal.

Signal sources (any non-empty matches):
- ``trigger_events`` in any prior adapter result's ``data`` (Trigify)
- ``structural_signals`` in any prior adapter result's ``data``
  (claude_web_triggers, apollo_enrich)

When a signal IS present:
  - skip ``claude_deep_research``
  - skipped[name] = "signal_gated_skip"
  - decision_log entry: signal_gated_skip with the matching field

When NO signal is present:
  - run ``claude_deep_research`` as before (Tier 4 fallback path)

Other adapters in the tier list (zerobounce, trigify, web_triggers,
apollo_enrich) are NOT signal-gated — only deep_research is.
"""
from __future__ import annotations

from typing import Any

import pytest

from systems.scout.enrich.base import EnrichResult
from systems.scout.enrich.orchestrator import EnrichOrchestrator


# Use a fresh dict per test to avoid mutation bleed.
def _tier_a_with_dr() -> dict[str, list[str]]:
    return {
        "A": [
            "zerobounce",
            "trigify",
            "claude_web_triggers",
            "apollo_enrich",
            "claude_deep_research",
        ],
    }


# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #


class FakeAdapter:
    def __init__(
        self,
        name: str,
        data: dict[str, Any] | None = None,
        cost_cents_per_call: int = 1,
    ) -> None:
        self.name = name
        self.cost_cents_per_call = cost_cents_per_call
        self._data = data or {}
        self.enrich_calls = 0

    async def enrich(self, contact, *, dry_run=False):
        self.enrich_calls += 1
        return EnrichResult(
            adapter_name=self.name,
            ok=True,
            data=self._data,
            cost_cents=self.cost_cents_per_call,
            reason="ok",
        )


class FakeBudget:
    async def remaining_cents(self, client_id, tier):
        return 9999

    async def record_spend(self, client_id, tier, cents):
        pass


class FakeLogger:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def log_decision(self, *args, **kwargs):
        # Existing orchestrator helpers pass kwargs we don't care about
        # — capture the lot for assertion.
        self.calls.append({"args": args, "kwargs": kwargs})


def _make_orch(adapters):
    return EnrichOrchestrator(
        adapters=adapters,
        budget_tracker=FakeBudget(),
        decision_logger=FakeLogger(),
        tier_adapters=_tier_a_with_dr(),
    )


# --------------------------------------------------------------------------- #
# Skip when signals present                                                   #
# --------------------------------------------------------------------------- #


async def test_dr_skipped_when_trigger_events_present_from_trigify():
    zb = FakeAdapter("zerobounce", data={})
    trigify = FakeAdapter(
        "trigify",
        data={"trigger_events": [{"type": "funding_round", "summary": "raised $10m"}]},
    )
    web_triggers = FakeAdapter("claude_web_triggers", data={})
    apollo = FakeAdapter("apollo_enrich", data={})
    dr = FakeAdapter("claude_deep_research", data={})

    orch = _make_orch([zb, trigify, web_triggers, apollo, dr])
    result = await orch.enrich_contact(
        client_id="c1", contact={"contact_id": "u1"}, tier="A",
    )

    assert dr.enrich_calls == 0
    assert "claude_deep_research" not in result.adapter_results
    assert result.skipped.get("claude_deep_research") == "signal_gated_skip"
    # Other adapters DID run.
    assert "trigify" in result.adapter_results
    assert "zerobounce" in result.adapter_results


async def test_dr_skipped_when_structural_signals_present_from_web_triggers():
    zb = FakeAdapter("zerobounce", data={})
    trigify = FakeAdapter("trigify", data={})
    web_triggers = FakeAdapter(
        "claude_web_triggers",
        data={"structural_signals": [{"type": "expansion", "evidence": "new HQ"}]},
    )
    apollo = FakeAdapter("apollo_enrich", data={})
    dr = FakeAdapter("claude_deep_research", data={})

    orch = _make_orch([zb, trigify, web_triggers, apollo, dr])
    result = await orch.enrich_contact(
        client_id="c1", contact={"contact_id": "u1"}, tier="A",
    )

    assert dr.enrich_calls == 0
    assert result.skipped.get("claude_deep_research") == "signal_gated_skip"


async def test_dr_skipped_when_structural_signals_present_from_apollo():
    zb = FakeAdapter("zerobounce", data={})
    trigify = FakeAdapter("trigify", data={})
    web_triggers = FakeAdapter("claude_web_triggers", data={})
    apollo = FakeAdapter(
        "apollo_enrich",
        data={"structural_signals": [{"type": "hiring_burst"}]},
    )
    dr = FakeAdapter("claude_deep_research", data={})

    orch = _make_orch([zb, trigify, web_triggers, apollo, dr])
    result = await orch.enrich_contact(
        client_id="c1", contact={"contact_id": "u1"}, tier="A",
    )
    assert dr.enrich_calls == 0


async def test_dr_skipped_when_both_signal_types_present():
    trigify = FakeAdapter(
        "trigify", data={"trigger_events": [{"type": "exec_change"}]},
    )
    web_triggers = FakeAdapter(
        "claude_web_triggers",
        data={"structural_signals": [{"type": "expansion"}]},
    )
    zb = FakeAdapter("zerobounce", data={})
    apollo = FakeAdapter("apollo_enrich", data={})
    dr = FakeAdapter("claude_deep_research", data={})

    orch = _make_orch([zb, trigify, web_triggers, apollo, dr])
    result = await orch.enrich_contact(
        client_id="c1", contact={"contact_id": "u1"}, tier="A",
    )
    assert dr.enrich_calls == 0


# --------------------------------------------------------------------------- #
# Run when no signals present                                                 #
# --------------------------------------------------------------------------- #


async def test_dr_runs_when_no_signals_anywhere():
    """All prior adapters return empty data → DR fires (Tier 4 fallback path)."""
    zb = FakeAdapter("zerobounce", data={})
    trigify = FakeAdapter("trigify", data={})
    web_triggers = FakeAdapter("claude_web_triggers", data={})
    apollo = FakeAdapter("apollo_enrich", data={})
    dr = FakeAdapter("claude_deep_research", data={"website_summary": "..."})

    orch = _make_orch([zb, trigify, web_triggers, apollo, dr])
    result = await orch.enrich_contact(
        client_id="c1", contact={"contact_id": "u1"}, tier="A",
    )
    assert dr.enrich_calls == 1
    assert "claude_deep_research" in result.adapter_results
    assert "claude_deep_research" not in result.skipped


async def test_dr_runs_when_signal_fields_present_but_empty():
    """Empty list / empty dict for trigger_events doesn't count as signal —
    DR still runs."""
    trigify = FakeAdapter("trigify", data={"trigger_events": []})
    web_triggers = FakeAdapter("claude_web_triggers", data={"structural_signals": []})
    zb = FakeAdapter("zerobounce", data={})
    apollo = FakeAdapter("apollo_enrich", data={})
    dr = FakeAdapter("claude_deep_research", data={"website_summary": "..."})

    orch = _make_orch([zb, trigify, web_triggers, apollo, dr])
    result = await orch.enrich_contact(
        client_id="c1", contact={"contact_id": "u1"}, tier="A",
    )
    assert dr.enrich_calls == 1
    assert "claude_deep_research" in result.adapter_results


# --------------------------------------------------------------------------- #
# Other adapters NOT signal-gated                                              #
# --------------------------------------------------------------------------- #


async def test_other_adapters_not_signal_gated():
    """Only ``claude_deep_research`` is signal-gated. zerobounce + trigify +
    web_triggers + apollo always run regardless of signal state."""
    trigify = FakeAdapter(
        "trigify",
        data={"trigger_events": [{"type": "funding_round"}]},
    )
    zb = FakeAdapter("zerobounce", data={})
    web_triggers = FakeAdapter("claude_web_triggers", data={})
    apollo = FakeAdapter("apollo_enrich", data={})
    dr = FakeAdapter("claude_deep_research", data={})

    orch = _make_orch([zb, trigify, web_triggers, apollo, dr])
    await orch.enrich_contact(
        client_id="c1", contact={"contact_id": "u1"}, tier="A",
    )
    # Trigify ran (it produces the signal), then web_triggers + apollo
    # also ran. DR was the only one gated out.
    assert zb.enrich_calls == 1
    assert trigify.enrich_calls == 1
    assert web_triggers.enrich_calls == 1
    assert apollo.enrich_calls == 1
    assert dr.enrich_calls == 0


# --------------------------------------------------------------------------- #
# Cost accounting                                                              #
# --------------------------------------------------------------------------- #


async def test_signal_gated_skip_does_not_charge_cost():
    """When DR is gated out, total_cost_cents must not include its
    cost_cents_per_call."""
    trigify = FakeAdapter(
        "trigify",
        data={"trigger_events": [{"type": "x"}]},
        cost_cents_per_call=0,
    )
    zb = FakeAdapter("zerobounce", cost_cents_per_call=1)
    web_triggers = FakeAdapter("claude_web_triggers", cost_cents_per_call=1)
    apollo = FakeAdapter("apollo_enrich", cost_cents_per_call=1)
    dr = FakeAdapter("claude_deep_research", cost_cents_per_call=99)

    orch = _make_orch([zb, trigify, web_triggers, apollo, dr])
    result = await orch.enrich_contact(
        client_id="c1", contact={"contact_id": "u1"}, tier="A",
    )
    # Only zb + trigify + web + apollo charged: 1 + 0 + 1 + 1 = 3c. DR=99c skipped.
    assert result.total_cost_cents == 3
