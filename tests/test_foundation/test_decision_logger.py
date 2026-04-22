"""Tests for ``aios.foundation.decision_logger.DecisionLogger``.

The foundation modules use the async Supabase client pattern
``await self.db.table(...).select(...).eq(...).execute()``, so tests build
MagicMock chains whose terminal ``.execute()`` returns an ``AsyncMock`` —
the whole chain is synchronous (builder) until execute is awaited.

Covers: happy path insert, embedder wiring, empty-result return, error
handling in get_success_rate, and parameter plumbing into the Supabase
builder (what got written to which table with which values).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aios.foundation.decision_logger import DecisionLogger


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _make_execute(data: Any) -> AsyncMock:
    """Terminal .execute() returns an awaitable response with .data."""
    resp = MagicMock()
    resp.data = data
    return AsyncMock(return_value=resp)


def _make_chain_db(exec_return: Any) -> tuple[MagicMock, MagicMock, AsyncMock]:
    """Builder chain where every intermediate call returns self and
    .execute() is an AsyncMock yielding a fake response. Returns the
    (db, chain, execute_mock) triple so tests can assert on any link."""
    chain = MagicMock()
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.upsert.return_value = chain
    chain.eq.return_value = chain
    chain.gte.return_value = chain
    chain.is_.return_value = chain
    chain.limit.return_value = chain
    chain.order.return_value = chain
    not_chain = MagicMock()
    not_chain.is_.return_value = chain
    not_chain.in_.return_value = chain
    chain.not_ = not_chain
    exec_mock = _make_execute(exec_return)
    chain.execute = exec_mock

    db = MagicMock()
    db.table.return_value = chain
    return db, chain, exec_mock


# --------------------------------------------------------------------------- #
# log_decision                                                                #
# --------------------------------------------------------------------------- #


async def test_log_decision_returns_id_on_success() -> None:
    db, chain, _ = _make_chain_db([{"id": "dec-123"}])
    logger = DecisionLogger(db=db)

    result_id = await logger.log_decision(
        client_id="c1",
        decision_type="copy_variant",
        context={"avatar": "agency_founder"},
        decision="Used AIDA framework",
        reasoning="Signal-based",
        confidence=0.82,
    )

    assert result_id == "dec-123"
    db.table.assert_called_once_with("decision_log")
    # Insert payload is serialised: context gets json.dumps'd
    insert_payload = chain.insert.call_args.args[0]
    assert insert_payload["client_id"] == "c1"
    assert insert_payload["decision_type"] == "copy_variant"
    assert insert_payload["decision"] == "Used AIDA framework"
    assert insert_payload["reasoning"] == "Signal-based"
    assert insert_payload["confidence"] == 0.82
    assert insert_payload["source"] == "system"
    # context is JSON-stringified (module line 72)
    assert '"avatar"' in insert_payload["context"]


async def test_log_decision_empty_result_returns_empty_string() -> None:
    """When Supabase returns no data, module returns '' (not None)."""
    db, _, _ = _make_chain_db([])
    logger = DecisionLogger(db=db)

    result_id = await logger.log_decision(
        client_id="c1",
        decision_type="t",
        context={},
        decision="d",
    )

    assert result_id == ""


async def test_log_decision_embeds_when_embedder_configured() -> None:
    db, chain, _ = _make_chain_db([{"id": "dec-1"}])
    embedder = AsyncMock(return_value=[0.1] * 1024)

    logger = DecisionLogger(db=db, embedder=embedder)
    await logger.log_decision(
        client_id="c1",
        decision_type="copy_variant",
        context={"key": "value"},
        decision="chose AIDA",
    )

    embedder.assert_awaited_once()
    # The insert payload must include the embedding
    payload = chain.insert.call_args.args[0]
    assert payload["embedding"] == [0.1] * 1024


async def test_log_decision_tolerates_embedder_failure() -> None:
    """Embedder error must not break the insert — the decision still logs."""
    db, chain, _ = _make_chain_db([{"id": "dec-1"}])
    embedder = AsyncMock(side_effect=RuntimeError("voyage down"))

    logger = DecisionLogger(db=db, embedder=embedder)
    result = await logger.log_decision(
        client_id="c1",
        decision_type="t",
        context={},
        decision="d",
    )

    assert result == "dec-1"
    payload = chain.insert.call_args.args[0]
    assert "embedding" not in payload


# --------------------------------------------------------------------------- #
# get_success_rate                                                            #
# --------------------------------------------------------------------------- #


async def test_get_success_rate_computes_rate_over_outcomes() -> None:
    rows = [
        {"outcome": "positive"}, {"outcome": "positive"},
        {"outcome": "negative"}, {"outcome": "neutral"},
    ]
    db, _, _ = _make_chain_db(rows)
    logger = DecisionLogger(db=db)

    stats = await logger.get_success_rate("c1", "copy_variant")

    assert stats["total"] == 4
    assert stats["positive"] == 2
    assert stats["negative"] == 1
    assert stats["neutral"] == 1
    assert stats["rate"] == 0.5


async def test_get_success_rate_empty_returns_zero_rate() -> None:
    db, _, _ = _make_chain_db([])
    logger = DecisionLogger(db=db)

    stats = await logger.get_success_rate("c1", "copy_variant")

    assert stats == {"total": 0, "positive": 0, "negative": 0, "neutral": 0, "rate": 0.0}


# --------------------------------------------------------------------------- #
# get_pending_outcomes                                                        #
# --------------------------------------------------------------------------- #


async def test_get_pending_outcomes_returns_rows() -> None:
    rows = [{"id": "1", "decision_type": "t", "decision": "d", "context": "{}", "created_at": "x"}]
    db, _, _ = _make_chain_db(rows)
    logger = DecisionLogger(db=db)

    result = await logger.get_pending_outcomes("c1")

    assert result == rows


async def test_get_pending_outcomes_empty_returns_empty_list() -> None:
    db, _, _ = _make_chain_db(None)  # simulate Supabase returning data=None
    logger = DecisionLogger(db=db)

    result = await logger.get_pending_outcomes("c1")

    assert result == []
