"""Tests for ``aios.foundation.pattern_matcher.PatternMatcher``.

PatternMatcher goes ``embedder(text) -> embedding`` then calls
``db.rpc('match_decisions', {...}).execute()``. Exceptions are swallowed
and return [] — so tests must verify both the RPC args and the
fail-soft behaviour.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aios.foundation.pattern_matcher import PatternMatcher


def _make_rpc_db(rpc_return: Any) -> tuple[MagicMock, MagicMock]:
    resp = MagicMock()
    resp.data = rpc_return
    chain = MagicMock()
    chain.execute = AsyncMock(return_value=resp)
    db = MagicMock()
    db.rpc.return_value = chain
    return db, chain


async def test_find_similar_without_embedder_returns_empty() -> None:
    db, _ = _make_rpc_db([])
    matcher = PatternMatcher(db=db, embedder=None)

    result = await matcher.find_similar(
        client_id="c1", decision_type="copy_variant", current_context="ctx",
    )

    assert result == []
    # RPC was NEVER called — short-circuited before embed
    db.rpc.assert_not_called()


async def test_find_similar_happy_path_calls_pgvector_rpc() -> None:
    rows = [
        {
            "id": "d1",
            "decision": "Used AIDA",
            "reasoning": "signal present",
            "outcome": "positive",
            "outcome_data": {"replied": True},
            "confidence": 0.85,
            "similarity": 0.92,
        },
    ]
    db, _ = _make_rpc_db(rows)
    embedder = AsyncMock(return_value=[0.5] * 1024)

    matcher = PatternMatcher(db=db, embedder=embedder)
    result = await matcher.find_similar(
        client_id="c1",
        decision_type="copy_variant",
        current_context="agency_founder CRO niche",
        limit=10,
    )

    embedder.assert_awaited_once_with("agency_founder CRO niche")
    db.rpc.assert_called_once()
    rpc_name, rpc_args = db.rpc.call_args.args
    assert rpc_name == "match_decisions"
    assert rpc_args == {
        "query_embedding": [0.5] * 1024,
        "client_id_filter": "c1",
        "decision_type_filter": "copy_variant",
        "match_count": 10,
    }
    assert len(result) == 1
    assert result[0]["id"] == "d1"
    assert result[0]["decision"] == "Used AIDA"
    assert result[0]["similarity"] == 0.92


async def test_find_similar_empty_rpc_returns_empty_list() -> None:
    db, _ = _make_rpc_db([])
    embedder = AsyncMock(return_value=[0.0] * 1024)

    matcher = PatternMatcher(db=db, embedder=embedder)
    result = await matcher.find_similar(
        client_id="c1", decision_type="t", current_context="ctx",
    )

    assert result == []


async def test_find_similar_embedder_failure_fails_soft() -> None:
    """Embedder exception must not propagate — returns []."""
    db, _ = _make_rpc_db([])
    embedder = AsyncMock(side_effect=RuntimeError("voyage down"))

    matcher = PatternMatcher(db=db, embedder=embedder)
    result = await matcher.find_similar(
        client_id="c1", decision_type="t", current_context="ctx",
    )

    assert result == []
    db.rpc.assert_not_called()  # never reached


async def test_find_similar_rpc_failure_fails_soft() -> None:
    """RPC raising is swallowed and [] returned."""
    chain = MagicMock()
    chain.execute = AsyncMock(side_effect=RuntimeError("pgvector boom"))
    db = MagicMock()
    db.rpc.return_value = chain
    embedder = AsyncMock(return_value=[0.0] * 1024)

    matcher = PatternMatcher(db=db, embedder=embedder)
    result = await matcher.find_similar(
        client_id="c1", decision_type="t", current_context="ctx",
    )

    assert result == []


def test_format_for_prompt_empty_returns_empty_string() -> None:
    matcher = PatternMatcher(db=MagicMock(), embedder=None)
    assert matcher.format_for_prompt([]) == ""


def test_format_for_prompt_renders_decisions_and_outcomes() -> None:
    matcher = PatternMatcher(db=MagicMock(), embedder=None)
    decisions = [
        {
            "decision": "Used AIDA",
            "reasoning": "signal present",
            "outcome": "positive",
            "confidence": 0.85,
            "outcome_data": {"replied": True, "opened": True},
        },
    ]

    out = matcher.format_for_prompt(decisions)

    assert "Used AIDA" in out
    assert "signal present" in out
    assert "positive" in out
    assert "85%" in out  # confidence formatted as percentage
