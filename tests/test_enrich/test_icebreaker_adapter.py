"""Tests for IcebreakerAdapter (Task D — Real-Copy MVP).

Injected FakeAnthropic + FakeBudgetTracker — no real network, no real
Anthropic SDK. Mirrors the FakeAnthropic pattern from
test_claude_deep_research.py.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from systems.scout.enrich.icebreaker_adapter import (
    IcebreakerAdapter,
    IcebreakerResult,
)


# --------------------------------------------------------------------------- #
# Fake Claude client                                                            #
# --------------------------------------------------------------------------- #

class _FakeAnthropic:
    """Mock Anthropic client. Returns scripted responses in order.

    Pass a list of strings — one per expected create() call. If the
    adapter exceeds the script, the last entry repeats (so single-response
    tests can pass one string).
    """

    def __init__(self, responses: list[str] | str):
        if isinstance(responses, str):
            responses = [responses]
        self._responses = list(responses)
        self.messages = self
        self.close = AsyncMock()
        self.create_calls: list[dict[str, Any]] = []

    async def create(self, **kwargs):
        idx = min(len(self.create_calls), len(self._responses) - 1)
        payload = self._responses[idx]
        self.create_calls.append(kwargs)
        resp = MagicMock()
        resp.content = [MagicMock(text=payload)]
        return resp


def _ib_json(text: str) -> str:
    return json.dumps({"icebreaker": text})


# --------------------------------------------------------------------------- #
# Fake budget tracker                                                           #
# --------------------------------------------------------------------------- #

class _FakeBudgetTracker:
    """Controllable remaining_cents + recorded spend calls."""

    def __init__(self, remaining: int = 100) -> None:
        self._remaining = remaining
        self.spend_calls: list[tuple[str, str, int]] = []

    async def remaining_cents(self, client_id: str, tier: str) -> int:
        return self._remaining

    async def record_spend(self, client_id: str, tier: str, cents: int) -> None:
        self.spend_calls.append((client_id, tier, cents))
        self._remaining -= cents


# --------------------------------------------------------------------------- #
# Shared fixtures                                                               #
# --------------------------------------------------------------------------- #

@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-sonnet-key")


_CONTACT = {
    "contact_id": "c-ib-001",
    "first_name": "Jordan",
    "company": "Acme Consulting",
    "company_domain": "acme-consulting.com",
    "industry": "Business Consulting",
}


def _merged(
    *,
    trigger_events: list[dict[str, Any]] | None = None,
    structural_signals: list[dict[str, Any]] | None = None,
    citable_details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "trigger_events": trigger_events or [],
        "structural_signals": structural_signals or [],
        "citable_details": citable_details or [],
    }


def _adapter(responses: list[str] | str, *, remaining: int = 100):
    fake = _FakeAnthropic(responses)
    tracker = _FakeBudgetTracker(remaining=remaining)
    return (
        IcebreakerAdapter(budget_tracker=tracker, anthropic_client=fake),
        fake,
        tracker,
    )


# --------------------------------------------------------------------------- #
# 1. Tier selection                                                             #
# --------------------------------------------------------------------------- #

async def test_tier_1_frustrated_trigger(_env):
    """Recent (<=14d) trigger_event with a frustration keyword → Tier 1."""
    adapter, fake, tracker = _adapter(_ib_json("Saw the rant about Salesforce, that whole mess hits home."))
    merged = _merged(
        trigger_events=[
            {"type": "behavioral_signal", "detail": "so tired of Salesforce crashing mid-demo", "recency_days": 3},
        ],
    )

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=merged,
        client_id="c-A",
        tier_budget="A",
    )

    assert result.ok is True
    assert result.tier == 1
    assert result.reason == "tier_1_generated"
    assert result.cost_cents == 1
    assert result.icebreaker_content.startswith("Saw")
    assert fake.create_calls, "Claude should have been called"


async def test_tier_2_neutral_trigger(_env):
    """Recent neutral trigger_event (no frustration keyword) → Tier 2."""
    adapter, fake, _ = _adapter(_ib_json("Liked the take on founder-led sales, matches what we're seeing."))
    merged = _merged(
        trigger_events=[
            {"type": "behavioral_signal", "detail": "great article on founder-led sales", "recency_days": 5},
        ],
    )

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=merged,
        client_id="c-A",
        tier_budget="A",
    )

    assert result.ok is True
    assert result.tier == 2
    assert result.reason == "tier_2_generated"


async def test_tier_3_structural_signal(_env):
    """No triggers but structural_signals present → Tier 3."""
    adapter, fake, _ = _adapter(_ib_json("Noticed the Series B announcement, that usually means ops gets messy."))
    merged = _merged(
        structural_signals=[
            {
                "category": "financial_growth",
                "type": "funding_round",
                "evidence_url": "https://acme.com/about",
                "summary": "Closed Series B in Q1 2026",
            },
        ],
    )

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=merged,
        client_id="c-A",
        tier_budget="A",
    )

    assert result.ok is True
    assert result.tier == 3
    assert result.reason == "tier_3_generated"


async def test_tier_4_citable_fallback(_env):
    """No triggers, no structural signals, but citable_details → Tier 4."""
    adapter, fake, _ = _adapter(_ib_json("Read the piece on the Ravenna engagement, that one jumped out."))
    merged = _merged(
        citable_details=[
            {"type": "case_study", "detail": "Ravenna AI 3x pipeline in 90 days", "source": "case_studies"},
        ],
    )

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=merged,
        client_id="c-A",
        tier_budget="A",
    )

    assert result.ok is True
    assert result.tier == 4
    assert result.reason == "tier_4_generated"


async def test_no_source_material(_env):
    """Nothing to work with → tier=0, no Claude call, reason=no_source_material."""
    adapter, fake, tracker = _adapter(_ib_json("should not be used"))
    merged = _merged()  # all empty

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=merged,
        client_id="c-A",
        tier_budget="A",
    )

    assert result.ok is True
    assert result.tier == 0
    assert result.reason == "no_source_material"
    assert result.cost_cents == 0
    assert result.icebreaker_content == ""
    assert fake.create_calls == []
    assert tracker.spend_calls == []


# --------------------------------------------------------------------------- #
# 2. Retry loop — banned-word                                                   #
# --------------------------------------------------------------------------- #

async def test_banned_word_retry_success(_env):
    """First response contains 'leverage'; second is clean → tier set, cost = 2c."""
    bad = _ib_json("Saw the post and want to leverage that angle.")
    good = _ib_json("Saw the post, that angle lands for most of the founders we work with.")
    adapter, fake, tracker = _adapter([bad, good])

    merged = _merged(
        structural_signals=[
            {"category": "financial_growth", "type": "funding_round", "evidence_url": "u", "summary": "Series B"},
        ],
    )

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=merged,
        client_id="c-A",
        tier_budget="A",
    )

    assert result.ok is True
    assert result.tier == 3
    assert result.reason == "tier_3_generated"
    assert result.cost_cents == 2
    assert len(fake.create_calls) == 2
    # record_spend once, but for the cumulative 2c.
    assert tracker.spend_calls == [("c-A", "A", 2)]


async def test_banned_word_retry_exhausted(_env):
    """Both responses contain a banned word → ok=True, empty content, reason='banned_word_retry_exhausted'."""
    bad1 = _ib_json("Saw the workflow stuff you're pushing, love it.")
    bad2 = _ib_json("Noticed the pipeline question, we get that.")
    adapter, fake, _ = _adapter([bad1, bad2])

    merged = _merged(
        structural_signals=[
            {"category": "financial_growth", "type": "funding_round", "evidence_url": "u", "summary": "Series B"},
        ],
    )

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=merged,
        client_id="c-A",
        tier_budget="A",
    )

    assert result.ok is True
    assert result.tier == 3
    assert result.reason == "banned_word_retry_exhausted"
    assert result.cost_cents == 2
    assert result.icebreaker_content == ""
    assert len(fake.create_calls) == 2


# --------------------------------------------------------------------------- #
# 3. Anti-stalker — applies to tiers 1-2 only                                   #
# --------------------------------------------------------------------------- #

async def test_anti_stalker_tier_1_retry_success(_env):
    """Tier 1 response contains 'you liked' → retry; if clean, pass."""
    bad = _ib_json("Saw you liked the rant about Salesforce.")
    good = _ib_json("Saw the rant about Salesforce crashing mid-demo.")
    adapter, fake, _ = _adapter([bad, good])

    merged = _merged(
        trigger_events=[
            {"type": "behavioral_signal", "detail": "so tired of Salesforce", "recency_days": 2},
        ],
    )

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=merged,
        client_id="c-A",
        tier_budget="A",
    )

    assert result.ok is True
    assert result.tier == 1
    assert result.reason == "tier_1_generated"
    assert result.cost_cents == 2


async def test_anti_stalker_not_applied_to_tier_3(_env):
    """Tier 3 response containing 'you liked' passes validation (anti-stalker
    only fires for social-engagement tiers 1-2)."""
    # "you liked" ONLY triggers anti-stalker; it contains no banned word.
    suspicious = _ib_json("Saw the Series B, you liked that round to fund US ops.")
    adapter, fake, _ = _adapter([suspicious])

    merged = _merged(
        structural_signals=[
            {"category": "financial_growth", "type": "funding_round", "evidence_url": "u", "summary": "Series B"},
        ],
    )

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=merged,
        client_id="c-A",
        tier_budget="A",
    )

    assert result.ok is True
    assert result.tier == 3
    assert result.reason == "tier_3_generated"
    assert result.cost_cents == 1
    assert len(fake.create_calls) == 1


async def test_anti_stalker_retry_exhausted_tier_2(_env):
    """Tier 2 both attempts contain 'your post' → anti_stalker_retry_exhausted."""
    bad1 = _ib_json("Saw your post on founder-led sales, good read.")
    bad2 = _ib_json("Noticed your post about that topic.")
    adapter, fake, _ = _adapter([bad1, bad2])

    merged = _merged(
        trigger_events=[
            {"type": "behavioral_signal", "detail": "good article on founder-led sales", "recency_days": 5},
        ],
    )

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=merged,
        client_id="c-A",
        tier_budget="A",
    )

    assert result.ok is True
    assert result.tier == 2
    assert result.reason == "anti_stalker_retry_exhausted"
    assert result.cost_cents == 2
    assert result.icebreaker_content == ""


# --------------------------------------------------------------------------- #
# 4. Skip paths                                                                  #
# --------------------------------------------------------------------------- #

async def test_dry_run_skipped(_env):
    """dry_run=True → tier=0, reason='dry_run_skipped', no Claude call."""
    adapter, fake, tracker = _adapter(_ib_json("must not run"))

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=_merged(
            structural_signals=[{"category": "financial_growth", "type": "funding_round",
                                 "evidence_url": "u", "summary": "s"}],
        ),
        client_id="c-A",
        tier_budget="A",
        dry_run=True,
    )

    assert result.ok is True
    assert result.tier == 0
    assert result.reason == "dry_run_skipped"
    assert result.cost_cents == 0
    assert fake.create_calls == []
    assert tracker.spend_calls == []


async def test_no_api_key(monkeypatch):
    """ANTHROPIC_API_KEY unset → ok=False, no Claude call."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    adapter, fake, tracker = _adapter(_ib_json("must not run"))

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=_merged(
            structural_signals=[{"category": "financial_growth", "type": "funding_round",
                                 "evidence_url": "u", "summary": "s"}],
        ),
        client_id="c-A",
        tier_budget="A",
    )

    assert result.ok is False
    assert result.reason == "no_api_key"
    assert result.cost_cents == 0
    assert fake.create_calls == []
    assert tracker.spend_calls == []


async def test_budget_exhausted(_env):
    """Budget < cost_cents_per_call → no Claude call, reason='budget_exhausted'."""
    adapter, fake, tracker = _adapter(_ib_json("must not run"), remaining=0)

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=_merged(
            structural_signals=[{"category": "financial_growth", "type": "funding_round",
                                 "evidence_url": "u", "summary": "s"}],
        ),
        client_id="c-A",
        tier_budget="A",
    )

    assert result.ok is True
    assert result.tier == 3  # tier still communicated
    assert result.reason == "budget_exhausted"
    assert result.cost_cents == 0
    assert fake.create_calls == []
    assert tracker.spend_calls == []


async def test_budget_record_spend_called_with_correct_amount(_env):
    """Successful first-shot generation → record_spend called once with 1c."""
    adapter, fake, tracker = _adapter(_ib_json(
        "Noticed the Series B, that usually kicks ops into chaos for a quarter."
    ))

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=_merged(
            structural_signals=[{"category": "financial_growth", "type": "funding_round",
                                 "evidence_url": "u", "summary": "Series B"}],
        ),
        client_id="c-A",
        tier_budget="A",
    )

    assert result.reason == "tier_3_generated"
    assert result.cost_cents == 1
    assert tracker.spend_calls == [("c-A", "A", 1)]


# --------------------------------------------------------------------------- #
# 5. Parse failure                                                              #
# --------------------------------------------------------------------------- #

async def test_parse_failure(_env):
    """Claude returns malformed JSON → reason='parse_failed', cost=1c."""
    adapter, fake, tracker = _adapter("{not valid json")

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=_merged(
            structural_signals=[{"category": "financial_growth", "type": "funding_round",
                                 "evidence_url": "u", "summary": "Series B"}],
        ),
        client_id="c-A",
        tier_budget="A",
    )

    assert result.ok is True
    assert result.reason == "parse_failed"
    assert result.cost_cents == 1
    assert result.icebreaker_content == ""
    assert tracker.spend_calls == [("c-A", "A", 1)]


# --------------------------------------------------------------------------- #
# 6. Recency filter                                                             #
# --------------------------------------------------------------------------- #

async def test_stale_trigger_falls_through_to_structural(_env):
    """Trigger with recency_days=20 is outside the 14-day window → Tier 3 fires."""
    adapter, fake, _ = _adapter(_ib_json(
        "Noticed the Series B, that usually kicks ops into chaos for a quarter."
    ))
    merged = _merged(
        trigger_events=[
            {"type": "behavioral_signal", "detail": "so tired of it all", "recency_days": 20},
        ],
        structural_signals=[
            {"category": "financial_growth", "type": "funding_round",
             "evidence_url": "u", "summary": "Series B"},
        ],
    )

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=merged,
        client_id="c-A",
        tier_budget="A",
    )

    assert result.tier == 3
    assert result.reason == "tier_3_generated"


async def test_stale_trigger_with_no_other_sources_yields_no_material(_env):
    """Stale trigger + nothing else → no_source_material."""
    adapter, fake, _ = _adapter(_ib_json("should not be used"))
    merged = _merged(
        trigger_events=[
            {"type": "behavioral_signal", "detail": "so tired of it all", "recency_days": 40},
        ],
    )

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=merged,
        client_id="c-A",
        tier_budget="A",
    )

    assert result.tier == 0
    assert result.reason == "no_source_material"
    assert fake.create_calls == []


# --------------------------------------------------------------------------- #
# 7. Frustration keyword coverage                                               #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("phrase", ["sick of", "tired of", "burnt out", "fed up", "had enough"])
async def test_frustration_keywords_trigger_tier_1(_env, phrase):
    """Multiple frustration keywords all route to Tier 1."""
    adapter, fake, _ = _adapter(_ib_json(
        "Saw the rant about that mess, totally hear you."
    ))
    merged = _merged(
        trigger_events=[
            {"type": "behavioral_signal", "detail": f"we are {phrase} broken tooling", "recency_days": 1},
        ],
    )

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=merged,
        client_id="c-A",
        tier_budget="A",
    )

    assert result.tier == 1


# --------------------------------------------------------------------------- #
# 8. aclose() hygiene                                                           #
# --------------------------------------------------------------------------- #

async def test_aclose_does_not_close_injected_client(_env):
    """aclose() leaves an injected anthropic_client alone."""
    injected = MagicMock()
    injected.close = AsyncMock()
    tracker = _FakeBudgetTracker()

    adapter = IcebreakerAdapter(budget_tracker=tracker, anthropic_client=injected)
    await adapter.aclose()

    injected.close.assert_not_called()


async def test_aclose_closes_lazy_client(_env):
    """aclose() closes a lazily-created anthropic client exactly once."""
    tracker = _FakeBudgetTracker()
    adapter = IcebreakerAdapter(budget_tracker=tracker)

    lazy = MagicMock()
    lazy.close = AsyncMock()
    adapter._anthropic_client = lazy
    # _anthropic_provided is False (no inject at __init__)

    await adapter.aclose()
    lazy.close.assert_awaited_once()

    # Second call is a no-op.
    await adapter.aclose()
    lazy.close.assert_awaited_once()


# --------------------------------------------------------------------------- #
# 9. IcebreakerResult shape sanity                                              #
# --------------------------------------------------------------------------- #

def test_icebreaker_result_dataclass_default_construction():
    r = IcebreakerResult(
        ok=True, icebreaker_content="", tier=0, cost_cents=0, reason="x"
    )
    assert r.ok is True
    assert r.tier == 0
