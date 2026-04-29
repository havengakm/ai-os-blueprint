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
    # Verify the Tier 1 prompt fired, not a sibling tier's
    prompt_sent = fake.create_calls[0]["messages"][0]["content"]
    # Slice 21 (2026-04-29) widened tier-1 trigger language from "frustrated"
    # to "frustration, opinion, announcement, observation" to allow the
    # neutral-post tier-1 case Trigify will surface. Probe stays on the
    # tier-1 marker via "(MUST reference verbatim content from here)" + "post".
    assert "post" in prompt_sent.lower()
    assert "verbatim content" in prompt_sent


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
    prompt_sent = fake.create_calls[0]["messages"][0]["content"]
    assert "engaged with relevant content neutrally" in prompt_sent


async def test_tier_3_structural_signal(_env):
    """No triggers but structural_signals present → Tier 3."""
    adapter, fake, _ = _adapter(_ib_json("Saw the Series B announcement land last week. That's a big one."))
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
    prompt_sent = fake.create_calls[0]["messages"][0]["content"]
    assert "structural event just hit" in prompt_sent
    # Humanized slug check: 'funding_round' → 'funding round' before prompt injection.
    # The literal string 'funding_round' appears in the truth-gating rule ("Signal
    # type MUST be one of: major_contract_win, new_leadership, funding_round"),
    # so we only assert the humanized form surfaces in the signal-summary section.
    assert "funding round" in prompt_sent


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
    prompt_sent = fake.create_calls[0]["messages"][0]["content"]
    assert "Fall back to the company website" in prompt_sent


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


# --------------------------------------------------------------------------- #
# 10. v2 truth-gating — Claude returns "" when source material is thin        #
# --------------------------------------------------------------------------- #

async def test_truth_gated_empty_string_resolves_to_no_source_material(_env):
    """Claude returns {"icebreaker": ""} per v2 truth-gating rule → the
    adapter treats it as no_source_material (tier=0), bills once, does NOT
    retry. The composer's IcebreakerAdapter fill path then routes to the
    tier-0 fallback instead of shipping the empty string as copy."""
    adapter, fake, tracker = _adapter(_ib_json(""))
    merged = _merged(
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

    assert result.ok is True
    assert result.tier == 0  # demoted to tier=0 because no content
    assert result.reason == "no_source_material"
    assert result.icebreaker_content == ""
    assert result.cost_cents == 1  # billed once, no retry
    assert len(fake.create_calls) == 1
    assert tracker.spend_calls == [("c-A", "A", 1)]


# --------------------------------------------------------------------------- #
# 11. v2 banned words — new creative_branding additions                       #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("banned_phrase", [
    "love your headcount planning",
    "happy to talk BD strategy",
    "impressive business development",
    "you've got capacity to spare",
    "your inbound is strong",
    "need to outrun the market",
    "the runway question is real",
    "growth metrics look solid",
    "the gap is obvious here",
    "your mood-board vibes",
    "the craft is undeniable",
])
async def test_v2_banned_words_trigger_retry(_env, banned_phrase: str):
    """New v2 bans from Kirsten: headcount, BD, business development,
    capacity, inbound, outrun, runway, growth metrics, gap, mood-board,
    craft. Each must fail validation on first attempt and retry."""
    bad = _ib_json(f"Saw the Series B. {banned_phrase}.")
    good = _ib_json("Saw the Series B announcement, that's a big one.")
    adapter, fake, _ = _adapter([bad, good])

    merged = _merged(
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

    assert result.reason == "tier_3_generated"
    assert len(fake.create_calls) == 2  # retry fired
    assert result.icebreaker_content.endswith("that's a big one.")


# --------------------------------------------------------------------------- #
# 12. v2 diagnostic-phrase rejection                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("diagnostic_phrase", [
    "that usually means a rough quarter",
    "which suggests a messy transition",
    "it points to ops strain",
    "feels like a stretch",
    "the gap between delivery and sales",
    "this tells me something is off",
    "which means more pressure",
])
async def test_v2_diagnostic_phrases_trigger_retry(_env, diagnostic_phrase: str):
    """v2 voice-rule: NEVER write consultant-style diagnosis. The
    validator treats these substrings as a rule violation and retries."""
    bad = _ib_json(f"Saw the Series B. {diagnostic_phrase}.")
    good = _ib_json("Saw the Series B announcement, that's a big one.")
    adapter, fake, _ = _adapter([bad, good])

    merged = _merged(
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

    assert result.reason == "tier_3_generated"
    assert len(fake.create_calls) == 2


# --------------------------------------------------------------------------- #
# 13. Em-dash is BANNED — global writing guardrail rule 2.1                   #
# --------------------------------------------------------------------------- #

async def test_em_dash_triggers_banned_char_retry(_env):
    """Em-dash is banned per ``rules/global-writing-guardrails.md`` (no em
    dashes). The validator must treat em-dash as a banned-character violation,
    forcing one retry. If the retry returns a clean version (using a comma
    or period instead), the call succeeds with cost = 2c.

    Reverses the prior v2 behaviour where em-dash was allowed as a clause
    joiner — operator decision 2026-04-25 after the PR Worx live draft
    rendered with ``"South African PR — that's"``.
    """
    # Use a U+2014 EM DASH explicitly so this test isn't affected by future
    # global string sweeps that remove em-dashes from other test fixtures.
    em_dash = "—"
    bad = _ib_json(f"Saw the Series B announcement {em_dash} that's a big one.")
    good = _ib_json("Saw the Series B announcement, that's a big one.")
    adapter, fake, tracker = _adapter([bad, good])
    merged = _merged(
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

    assert result.reason == "tier_3_generated"
    assert em_dash not in result.icebreaker_content
    assert len(fake.create_calls) == 2  # retry happened
    assert tracker.spend_calls == [("c-A", "A", 2)]


async def test_em_dash_retry_exhausted_when_both_attempts_use_em_dash(_env):
    """When both attempts return an em-dash, the adapter records a
    ``banned_word_retry_exhausted`` skip (cost 2c) and returns empty
    icebreaker_content. The downstream composer's empty-component skip
    drops the section cleanly so the prospect never sees a stub."""
    # Explicit U+2014 codepoints to survive any future global sweep.
    em_dash = "—"
    bad_a = _ib_json(f"Saw the Series B {em_dash} that's a big one.")
    bad_b = _ib_json(f"Saw the Series B announcement {em_dash} congrats.")
    adapter, fake, tracker = _adapter([bad_a, bad_b])
    merged = _merged(
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

    assert result.reason == "banned_word_retry_exhausted"
    assert result.icebreaker_content == ""
    assert len(fake.create_calls) == 2
    assert tracker.spend_calls == [("c-A", "A", 2)]


# --------------------------------------------------------------------------- #
# 14. v2 prompts mention the core voice rules                                  #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("tier_setup", [
    # (merged_research_data kwargs, response, expected_tier)
    (
        {"trigger_events": [
            {"type": "behavioral_signal", "detail": "so tired of it all", "recency_days": 3},
        ]},
        "Ngl your post last week, that feeling is genuine.",
        1,
    ),
    (
        {"trigger_events": [
            {"type": "behavioral_signal", "detail": "good read on founder-led sales", "recency_days": 5},
        ]},
        "Saw the podcast take last week. Genuinely stuck with me.",
        2,
    ),
    (
        {"structural_signals": [
            {"category": "financial_growth", "type": "funding_round",
             "evidence_url": "u", "summary": "Series B"},
        ]},
        "Saw the Series B announcement, that's a big one.",
        3,
    ),
    (
        {"citable_details": [
            {"type": "case_study", "detail": "MiBlok rebrand", "source": "portfolio"},
        ]},
        "Spent time on the MiBlok rebrand this morning and had to reach out.",
        4,
    ),
])
async def test_v2_prompts_contain_truth_gating_rule(_env, tier_setup):
    """Every v2 prompt (all 4 tiers) must carry the truth-gating rule +
    the banned-word list. Probes the rendered prompt directly."""
    merged_kwargs, response, expected_tier = tier_setup
    adapter, fake, _ = _adapter(_ib_json(response))

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=_merged(**merged_kwargs),
        client_id="c-A",
        tier_budget="A",
    )

    assert result.tier == expected_tier
    prompt_sent = fake.create_calls[0]["messages"][0]["content"]
    assert "Truth-gating rule" in prompt_sent, f"tier {expected_tier}"
    assert "Banned words" in prompt_sent, f"tier {expected_tier}"
    # The v2 bans appear in the list.
    assert "headcount" in prompt_sent, f"tier {expected_tier}"
    assert "mood-board" in prompt_sent, f"tier {expected_tier}"
    # v3: the "lead gen" ban must be present in every tier's prompt.
    assert "lead gen" in prompt_sent, f"tier {expected_tier}"
    # v3: every tier output spec must announce multi-line 2-3 sentence format.
    # Slice 21 (2026-04-29) tightened from 2-3 sentences down to 1
    # observation + optional reaction (15-45 words). Probe shifted to the
    # word-count target, which both old and new prompts mention.
    assert "15-45 words" in prompt_sent or "2-3 sentences" in prompt_sent, (
        f"tier {expected_tier}"
    )
    # Slice 21 (2026-04-29) tightened to 15-45 words (single observation).
    assert (
        "15-45 words" in prompt_sent
        or "40-70 words" in prompt_sent
    ), f"tier {expected_tier}"


# --------------------------------------------------------------------------- #
# 15. v3 "lead gen" ban triggers retry                                          #
# --------------------------------------------------------------------------- #

async def test_v3_lead_gen_ban_triggers_retry(_env):
    """v3 bans "lead gen" (prefer "growth systems"). First response uses the
    banned phrase → retry; second is clean → passes."""
    bad = _ib_json("Saw the Series B announcement land. Love seeing lead gen get its moment.")
    good = _ib_json("Saw the Series B announcement, that's a big one.")
    adapter, fake, _ = _adapter([bad, good])

    merged = _merged(
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

    assert result.reason == "tier_3_generated"
    assert len(fake.create_calls) == 2  # retry fired
    assert "lead gen" not in result.icebreaker_content.lower()


# --------------------------------------------------------------------------- #
# 16. v3 Tier 4 multi-line icebreaker passes validation                         #
# --------------------------------------------------------------------------- #

async def test_v3_tier_4_multiline_icebreaker_passes(_env):
    """v3 output format allows multi-line content. The adapter must accept
    it and surface verbatim. Slice 21 (2026-04-29) tightened the shape to
    a single observation + optional reaction (no "Two things jumped out"
    formulaic structure, no "Spent the morning with" / "Really sharp work"
    AI-cliches). This test now uses the clean shape."""
    multiline = (
        "Saw the Iroko work. The modular icon for organised structure "
        "instead of the usual sustainability visuals is a nice call."
    )
    adapter, fake, tracker = _adapter(_ib_json(multiline))

    merged = _merged(
        citable_details=[
            {"type": "case_study", "detail": "Iroko infrastructure-grade nature restoration",
             "source": "case_studies"},
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
    assert "Iroko" in result.icebreaker_content
    assert len(fake.create_calls) == 1  # no retry
    assert tracker.spend_calls == [("c-A", "A", 1)]


# --------------------------------------------------------------------------- #
# 17. v3.1 corporate-jargon bans — regression guards for live-run failures     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("corporate_phrase", [
    # From the Jonathan/Inkblot Tier 4 live-run failure
    "signalling formal local ecosystem engagement",
    "member profile active this month",
    # From the Madelain/PR Worx Tier 3 live-run failure
    "pursuing expansion into high-growth markets",
    "explicitly cited as driver behind the move",
    "the new MD appointment is cited as a catalyst",
    # Additional consultant-paraphrase patterns
    "uniquely positioned for growth",
    "on a transformation journey",
    "preparing for market entry abroad",
    "ready for market expansion",
    "signaling a new direction",
])
async def test_v3_1_corporate_jargon_triggers_retry(_env, corporate_phrase: str):
    """Regression guard for the Jonathan/Inkblot + Madelain/PR Worx live
    drafts that leaked consultant-voice jargon past the v3 banned list.
    Every one of these phrases must fail validation on first attempt."""
    bad = _ib_json(f"Saw the announcement. {corporate_phrase}.")
    good = _ib_json("Saw the announcement land last week. That's a big one.")
    adapter, fake, _ = _adapter([bad, good])

    merged = _merged(
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

    assert result.reason == "tier_3_generated", corporate_phrase
    assert len(fake.create_calls) == 2, corporate_phrase  # retry fired


# --------------------------------------------------------------------------- #
# 18. v3.1 prompts carry the opening-verb whitelist + BANNED/ALLOWED block     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("tier_setup", [
    (
        {"trigger_events": [
            {"type": "behavioral_signal", "detail": "so tired of it all", "recency_days": 3},
        ]},
        "Saw the rant. That one lands.",
        1,
    ),
    (
        {"trigger_events": [
            {"type": "behavioral_signal", "detail": "good read on founder-led sales", "recency_days": 5},
        ]},
        "Saw the podcast take. Genuinely stuck with me.",
        2,
    ),
    (
        {"structural_signals": [
            {"category": "financial_growth", "type": "funding_round",
             "evidence_url": "u", "summary": "Series B"},
        ]},
        "Saw the Series B announcement, that's a big one.",
        3,
    ),
    (
        {"citable_details": [
            {"type": "case_study", "detail": "MiBlok rebrand", "source": "portfolio"},
        ]},
        "Spent time on the MiBlok rebrand this morning.",
        4,
    ),
])
async def test_v3_1_prompts_contain_opener_whitelist_and_examples(_env, tier_setup):
    """Every v3.1 tier prompt must carry the opening-verb whitelist and
    the BANNED vs ALLOWED concrete-examples block. Probes the rendered
    prompt directly."""
    merged_kwargs, response, expected_tier = tier_setup
    adapter, fake, _ = _adapter(_ib_json(response))

    result = await adapter.generate(
        contact=_CONTACT,
        merged_research_data=_merged(**merged_kwargs),
        client_id="c-A",
        tier_budget="A",
    )

    assert result.tier == expected_tier
    prompt_sent = fake.create_calls[0]["messages"][0]["content"]
    # Opener whitelist markers
    assert "Opening verb" in prompt_sent, f"tier {expected_tier}"
    assert "Spent the morning with" in prompt_sent, f"tier {expected_tier}"
    # BANNED vs ALLOWED block markers
    assert "BANNED vs ALLOWED" in prompt_sent, f"tier {expected_tier}"
    # Slice 21 (2026-04-29) tightened the voice marker to "casual, warm,
    # non-transactional. Like an email to a friend you met once."
    assert (
        "warm observational voice" in prompt_sent
        or ("casual" in prompt_sent and "warm" in prompt_sent)
    ), f"tier {expected_tier}"
    # New v3.1 single-word bans appear in every tier's prompt
    assert "signalling" in prompt_sent, f"tier {expected_tier}"
    assert "ecosystem" in prompt_sent, f"tier {expected_tier}"
    assert "high-growth" in prompt_sent, f"tier {expected_tier}"
    # Slice 21 (2026-04-29) folded the "no analyze" rule into the Voice
    # rules block. Probe for the substantive content (DON'T interpret /
    # diagnose) which both old and new prompts include.
    assert (
        "no analyze" in prompt_sent.lower()
        or "don't interpret" in prompt_sent.lower()
    ), f"tier {expected_tier}"
