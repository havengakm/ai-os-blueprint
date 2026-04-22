"""Tests for ``aios.foundation.autonomy.AutonomyGate``.

Behaviours:
  - Returns the level from ``autonomy_rules`` when a rule exists
  - Returns 'suggest' + creates a default rule when none exists
  - Caches lookups (second call bypasses the DB)
  - Fails safe to 'suggest' on any query exception
  - Supports all four levels: suggest / draft / act_notify / autonomous
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from aios.foundation.autonomy import AUTONOMY_ORDER, AutonomyGate


def _select_db(rows: list[dict[str, Any]]) -> tuple[MagicMock, MagicMock]:
    """Build a db where table().select().eq().eq().limit().execute() yields rows
    and table().upsert().execute() succeeds."""
    resp = MagicMock()
    resp.data = rows

    select_chain = MagicMock()
    select_chain.select.return_value = select_chain
    select_chain.eq.return_value = select_chain
    select_chain.limit.return_value = select_chain
    select_chain.execute = AsyncMock(return_value=resp)

    # upsert terminates with its own execute
    select_chain.upsert.return_value = select_chain

    db = MagicMock()
    db.table.return_value = select_chain
    return db, select_chain


@pytest.mark.parametrize("level", AUTONOMY_ORDER)
async def test_check_returns_configured_level(level: str) -> None:
    db, _ = _select_db([{"autonomy_level": level}])
    gate = AutonomyGate(db=db)

    result = await gate.check("c1", "copy_variant")

    assert result == level


async def test_check_no_rule_returns_suggest_and_creates_default() -> None:
    db, chain = _select_db([])  # no rule found
    gate = AutonomyGate(db=db)

    result = await gate.check("c1", "new_action")

    assert result == "suggest"
    # A default rule was upserted
    chain.upsert.assert_called_once()
    payload = chain.upsert.call_args.args[0]
    assert payload == {
        "client_id": "c1",
        "action_type": "new_action",
        "autonomy_level": "suggest",
    }


async def test_check_caches_result_across_calls() -> None:
    db, chain = _select_db([{"autonomy_level": "act_notify"}])
    gate = AutonomyGate(db=db)

    first = await gate.check("c1", "copy_variant")
    second = await gate.check("c1", "copy_variant")

    assert first == "act_notify" == second
    # Only ONE execute call despite two .check() calls — cache hit
    assert chain.execute.await_count == 1


async def test_check_distinct_keys_are_cached_separately() -> None:
    db, chain = _select_db([{"autonomy_level": "draft"}])
    gate = AutonomyGate(db=db)

    await gate.check("c1", "action_a")
    await gate.check("c1", "action_b")
    await gate.check("c2", "action_a")

    # Three distinct cache keys -> three executes
    assert chain.execute.await_count == 3


async def test_check_query_failure_fails_safe_to_suggest() -> None:
    """Any DB exception must return 'suggest' — never raise."""
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute = AsyncMock(side_effect=RuntimeError("db down"))
    db = MagicMock()
    db.table.return_value = chain

    gate = AutonomyGate(db=db)
    result = await gate.check("c1", "copy_variant")

    assert result == "suggest"


async def test_check_default_rule_creation_failure_is_non_critical() -> None:
    """If upsert of the default rule fails, check() still returns 'suggest'."""
    # select returns empty (no existing rule); upsert raises
    resp = MagicMock()
    resp.data = []
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.upsert.return_value = chain

    # execute should succeed the first time (select) and fail the second (upsert)
    chain.execute = AsyncMock(side_effect=[resp, RuntimeError("upsert boom")])

    db = MagicMock()
    db.table.return_value = chain

    gate = AutonomyGate(db=db)
    # Must not raise
    result = await gate.check("c1", "new_action")
    assert result == "suggest"


# --------------------------------------------------------------------------- #
# check_promotion_eligibility                                                 #
# --------------------------------------------------------------------------- #


async def test_promotion_eligibility_no_rule_ineligible() -> None:
    db, _ = _select_db([])
    gate = AutonomyGate(db=db)

    result = await gate.check_promotion_eligibility("c1", "copy_variant")

    assert result["eligible"] is False
    assert "No rule" in result["reason"]


async def test_promotion_eligibility_already_autonomous_ineligible() -> None:
    db, _ = _select_db([{
        "autonomy_level": "autonomous",
        "conditions": {},
        "decisions_at_level": 100,
        "success_rate": 0.95,
    }])
    gate = AutonomyGate(db=db)

    result = await gate.check_promotion_eligibility("c1", "copy_variant")

    assert result["eligible"] is False
    assert "autonomous" in result["reason"]


async def test_promotion_eligibility_insufficient_decisions_ineligible() -> None:
    db, _ = _select_db([{
        "autonomy_level": "suggest",
        "conditions": {"min_sample_size": 50, "min_success_rate": 0.80},
        "decisions_at_level": 10,
        "success_rate": 0.90,
    }])
    gate = AutonomyGate(db=db)

    result = await gate.check_promotion_eligibility("c1", "copy_variant")

    assert result["eligible"] is False
    assert "50" in result["reason"]
    assert result["current_level"] == "suggest"
    assert result["decisions"] == 10


async def test_promotion_eligibility_all_conditions_met_eligible() -> None:
    db, _ = _select_db([{
        "autonomy_level": "suggest",
        "conditions": {"min_sample_size": 50, "min_success_rate": 0.80},
        "decisions_at_level": 60,
        "success_rate": 0.90,
    }])
    gate = AutonomyGate(db=db)

    result = await gate.check_promotion_eligibility("c1", "copy_variant")

    assert result["eligible"] is True
    assert result["current_level"] == "suggest"
    assert result["next_level"] == "draft"
    assert "60" in result["message"]
