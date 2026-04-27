"""Plan 2 Phase 5 Task 2.5.7: UncertainZoneJudge tests.

When a contact's rule-based icp_score lands in the uncertain zone
(default 40-60, configurable per client_config.icp.uncertain_zone),
the judge invokes a Haiku-tier LLM judge that returns a nudge ∈
{-15, -5, 0, +5, +15} to apply to the rule score.

Skip paths (no Anthropic call):
- dry_run=True            → reason='dry_run_skipped', nudge=0
- ANTHROPIC_API_KEY unset → reason='no_api_key', nudge=0

Failure paths return ok=False with nudge=0 (safe default — the
rule score stands on its own when the judge can't add value):
- 'parse_failed' — body wasn't parseable JSON
- 'invalid_nudge_value' — model returned a value outside {-15,-5,0,+5,+15}
"""
from __future__ import annotations

import json

import pytest

from systems.scout.score.uncertain_zone_judge import (
    DEFAULT_UNCERTAIN_ZONE_HIGH,
    DEFAULT_UNCERTAIN_ZONE_LOW,
    NudgeResult,
    UncertainZoneJudge,
    is_in_uncertain_zone,
)


# --------------------------------------------------------------------------- #
# Stub Anthropic client                                                       #
# --------------------------------------------------------------------------- #


class _StubMessage:
    def __init__(self, text: str) -> None:
        self.content = [type("Block", (), {"text": text, "type": "text"})()]
        self.stop_reason = "end_turn"


class StubAnthropicClient:
    def __init__(self, response: dict | str | Exception) -> None:
        self._response = response
        self.messages = self
        self.create_calls: list[dict] = []

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        text = (
            json.dumps(self._response)
            if isinstance(self._response, dict)
            else self._response
        )
        return _StubMessage(text)


def _make_judge(response, *, with_api_key: bool = True, monkeypatch=None):
    if monkeypatch is not None:
        if with_api_key:
            monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        else:
            monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    stub = StubAnthropicClient(response)
    return UncertainZoneJudge(anthropic_client=stub), stub


# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #


def test_default_uncertain_zone_is_40_to_60():
    """Per Plan 2 doc: 'default 40-60, configurable per client_config'."""
    assert DEFAULT_UNCERTAIN_ZONE_LOW == 40
    assert DEFAULT_UNCERTAIN_ZONE_HIGH == 60


# --------------------------------------------------------------------------- #
# is_in_uncertain_zone helper                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "score,expected",
    [
        (20, False),  # clearly archive — below low
        (39, False),  # just below low
        (40, True),   # at low boundary (inclusive)
        (50, True),   # mid
        (60, True),   # at high boundary (inclusive)
        (61, False),  # just above high
        (85, False),  # clearly Tier A
    ],
)
def test_is_in_uncertain_zone_uses_default_bounds(score, expected):
    assert is_in_uncertain_zone(score) == expected


def test_is_in_uncertain_zone_respects_custom_bounds():
    assert is_in_uncertain_zone(45, low=50, high=70) is False
    assert is_in_uncertain_zone(60, low=50, high=70) is True


# --------------------------------------------------------------------------- #
# Happy path — each valid nudge value                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("nudge_value", [-15, -5, 0, 5, 15])
async def test_judge_returns_each_valid_nudge(nudge_value, monkeypatch):
    judge, stub = _make_judge(
        {
            "nudge": nudge_value,
            "reasoning": "test verdict",
        },
        monkeypatch=monkeypatch,
    )
    result = await judge.judge(
        contact={
            "company": "Acme",
            "title": "VP Marketing",
            "industry": "SaaS",
            "employees": 80,
        },
        client_icp={
            "titles": ["VP Marketing"],
            "industries": ["SaaS"],
            "employee_min": 50,
            "employee_max": 200,
        },
    )
    assert isinstance(result, NudgeResult)
    assert result.ok
    assert result.nudge == nudge_value
    assert result.reasoning == "test verdict"
    assert result.reason == "ok"
    assert len(stub.create_calls) == 1


# --------------------------------------------------------------------------- #
# Skip paths                                                                  #
# --------------------------------------------------------------------------- #


async def test_dry_run_skips_call_and_returns_zero_nudge(monkeypatch):
    judge, stub = _make_judge({"nudge": 5, "reasoning": "x"}, monkeypatch=monkeypatch)
    result = await judge.judge(
        contact={"company": "x"}, client_icp={}, dry_run=True,
    )
    assert not result.ok
    assert result.reason == "dry_run_skipped"
    assert result.nudge == 0
    assert stub.create_calls == []


async def test_no_api_key_skips_call(monkeypatch):
    judge, stub = _make_judge(
        {"nudge": 5, "reasoning": "x"},
        with_api_key=False,
        monkeypatch=monkeypatch,
    )
    result = await judge.judge(contact={"company": "x"}, client_icp={})
    assert not result.ok
    assert result.reason == "no_api_key"
    assert result.nudge == 0
    assert stub.create_calls == []


# --------------------------------------------------------------------------- #
# Failure paths                                                               #
# --------------------------------------------------------------------------- #


async def test_parse_failure_when_response_not_json(monkeypatch):
    judge, _ = _make_judge("not valid json at all", monkeypatch=monkeypatch)
    result = await judge.judge(contact={"company": "x"}, client_icp={})
    assert not result.ok
    assert result.reason == "parse_failed"
    assert result.nudge == 0


async def test_invalid_nudge_value_returns_zero(monkeypatch):
    """Model hallucinated a value outside the canonical set
    {-15, -5, 0, +5, +15} — fall back to nudge=0 (rule score stands)."""
    judge, _ = _make_judge(
        {"nudge": 7, "reasoning": "weird"},
        monkeypatch=monkeypatch,
    )
    result = await judge.judge(contact={"company": "x"}, client_icp={})
    assert not result.ok
    assert result.reason == "invalid_nudge_value"
    assert result.nudge == 0


async def test_code_fence_wrapped_response_parses(monkeypatch):
    response = (
        "```json\n"
        '{"nudge": -5, "reasoning": "soft fit"}\n'
        "```"
    )
    judge, _ = _make_judge(response, monkeypatch=monkeypatch)
    result = await judge.judge(contact={"company": "x"}, client_icp={})
    assert result.ok
    assert result.nudge == -5


# --------------------------------------------------------------------------- #
# Prompt assembly                                                             #
# --------------------------------------------------------------------------- #


async def test_prompt_includes_contact_and_icp_context(monkeypatch):
    judge, stub = _make_judge(
        {"nudge": 5, "reasoning": "x"}, monkeypatch=monkeypatch,
    )
    await judge.judge(
        contact={
            "company": "Acme",
            "title": "VP Marketing",
            "industry": "Edtech",
            "employees": 75,
            "company_description": "Online tutoring platform",
        },
        client_icp={
            "titles": ["VP Marketing"],
            "industries": ["SaaS", "Edtech"],
            "employee_min": 50,
            "employee_max": 200,
            "geographies": ["US"],
        },
    )
    user = stub.create_calls[0]["messages"][0]["content"]
    assert "Acme" in user
    assert "VP Marketing" in user
    assert "Edtech" in user
    assert "50" in user  # employee_min


async def test_judge_uses_haiku_4_5_model(monkeypatch):
    judge, stub = _make_judge(
        {"nudge": 5, "reasoning": "x"}, monkeypatch=monkeypatch,
    )
    await judge.judge(contact={"company": "x"}, client_icp={})
    assert stub.create_calls[0]["model"] == "claude-haiku-4-5-20251001"
