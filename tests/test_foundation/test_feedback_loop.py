"""Tests for ``aios.foundation.feedback_loop.FeedbackLoop``.

Covers both publish() and record_outcome(). FeedbackLoop fans out to:
  - employee_memory.remember (publish only)
  - decision_logger.record_outcome (record_outcome only)
  - direct learning_events insert (both)

Failures in any branch are logged but never raised. Each test injects
fakes for the three dependencies + an optional embedder.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aios.foundation.feedback_loop import FeedbackLoop


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #


def _make_execute(data: Any) -> AsyncMock:
    resp = MagicMock()
    resp.data = data
    return AsyncMock(return_value=resp)


def _make_db(exec_return: Any) -> tuple[MagicMock, MagicMock]:
    chain = MagicMock()
    chain.insert.return_value = chain
    chain.execute = _make_execute(exec_return)
    db = MagicMock()
    db.table.return_value = chain
    return db, chain


def _make_loop(
    *,
    insert_data: Any = None,
    embedder: Any = None,
) -> tuple[FeedbackLoop, MagicMock, MagicMock, MagicMock, MagicMock]:
    """Return (loop, db, chain, decision_logger_mock, employee_memory_mock)."""
    if insert_data is None:
        insert_data = [{"id": "evt-123"}]
    db, chain = _make_db(insert_data)
    decision_logger = MagicMock()
    decision_logger.record_outcome = AsyncMock(return_value=None)
    employee_memory = MagicMock()
    employee_memory.remember = AsyncMock(return_value="mem-id-1")
    loop = FeedbackLoop(
        db=db,
        decision_logger=decision_logger,
        employee_memory=employee_memory,
        embedder=embedder,
    )
    return loop, db, chain, decision_logger, employee_memory


# --------------------------------------------------------------------------- #
# publish                                                                      #
# --------------------------------------------------------------------------- #


async def test_publish_writes_memory_and_event_returns_id() -> None:
    loop, db, chain, _, mem = _make_loop()

    event_id = await loop.publish(
        client_id="kirsten-client-zero",
        source_employee_id="prospect-researcher",
        kind="job_completion",
        content="Found 18 agencies last week. 11 scored 70+.",
        metadata={"playbook": "lead_generation", "scored_count": 11},
    )

    assert event_id == "evt-123"
    # Wrote to source employee's memory.
    mem.remember.assert_awaited_once()
    mem_call = mem.remember.call_args.kwargs
    assert mem_call["client_id"] == "kirsten-client-zero"
    assert mem_call["employee_id"] == "prospect-researcher"
    assert mem_call["kind"] == "job_completion"
    # Wrote a learning_events row.
    db.table.assert_called_once_with("learning_events")
    insert_payload = chain.insert.call_args.args[0]
    assert insert_payload["source_employee_id"] == "prospect-researcher"
    assert insert_payload["kind"] == "job_completion"
    assert insert_payload["content"].startswith("Found 18")


async def test_publish_drops_unknown_kind() -> None:
    """Invalid kind logs + returns None, no DB writes."""
    loop, db, _, _, mem = _make_loop()

    event_id = await loop.publish(
        client_id="c1",
        source_employee_id="prospect-researcher",
        kind="weird_kind",  # not in _VALID_LEARNING_KINDS
        content="x",
    )

    assert event_id is None
    mem.remember.assert_not_called()
    db.table.assert_not_called()


async def test_publish_includes_embedding_when_embedder_wired() -> None:
    embedder = AsyncMock(return_value=[0.5] * 1024)
    loop, _, chain, _, _ = _make_loop(embedder=embedder)

    await loop.publish(
        client_id="c1",
        source_employee_id="content-writer",
        kind="job_completion",
        content="Wrote a LinkedIn post about agency growth.",
    )

    embedder.assert_awaited_once_with(
        "Wrote a LinkedIn post about agency growth."
    )
    insert_payload = chain.insert.call_args.args[0]
    assert insert_payload["embedding"] == [0.5] * 1024


async def test_publish_tolerates_memory_failure_still_emits_event() -> None:
    """If employee_memory.remember crashes, the learning_event still fires."""
    loop, db, chain, _, mem = _make_loop()
    mem.remember.side_effect = RuntimeError("memory store down")

    event_id = await loop.publish(
        client_id="c1",
        source_employee_id="prospect-researcher",
        kind="job_completion",
        content="x",
    )

    assert event_id == "evt-123"
    db.table.assert_called_once_with("learning_events")


async def test_publish_returns_none_on_event_insert_failure() -> None:
    """If the learning_events insert returns no rows, log + return None.
    Don't raise — never break the writing employee."""
    loop, _, _, _, _ = _make_loop(insert_data=[])

    event_id = await loop.publish(
        client_id="c1",
        source_employee_id="prospect-researcher",
        kind="job_completion",
        content="x",
    )

    assert event_id is None


async def test_publish_carries_decision_log_id_when_provided() -> None:
    loop, _, chain, _, _ = _make_loop()

    await loop.publish(
        client_id="c1",
        source_employee_id="outreach-manager",
        kind="job_completion",
        content="Sent 50 emails today.",
        decision_log_id="dec-abc-123",
    )

    insert_payload = chain.insert.call_args.args[0]
    assert insert_payload["decision_log_id"] == "dec-abc-123"


# --------------------------------------------------------------------------- #
# record_outcome                                                               #
# --------------------------------------------------------------------------- #


async def test_record_outcome_backfills_decision_log_and_emits_event() -> None:
    loop, db, chain, dec_logger, _ = _make_loop()

    await loop.record_outcome(
        client_id="kirsten-client-zero",
        decision_id="dec-456",
        outcome="positive",
        source_employee_id="outreach-manager",
        outcome_data={"replied": True, "meeting_booked": True},
    )

    # Backfilled decision_log.outcome
    dec_logger.record_outcome.assert_awaited_once()
    rec_call = dec_logger.record_outcome.call_args.kwargs
    assert rec_call["decision_id"] == "dec-456"
    assert rec_call["outcome"] == "positive"
    assert rec_call["outcome_data"] == {"replied": True, "meeting_booked": True}

    # Emitted learning_event with kind='outcome'
    db.table.assert_called_once_with("learning_events")
    insert_payload = chain.insert.call_args.args[0]
    assert insert_payload["kind"] == "outcome"
    assert insert_payload["source_employee_id"] == "outreach-manager"
    assert insert_payload["decision_log_id"] == "dec-456"
    assert "Outcome=positive" in insert_payload["content"]


async def test_record_outcome_drops_invalid_outcome() -> None:
    loop, db, _, dec_logger, _ = _make_loop()

    await loop.record_outcome(
        client_id="c1",
        decision_id="dec-1",
        outcome="amazing",  # not valid
        source_employee_id="outreach-manager",
    )

    dec_logger.record_outcome.assert_not_called()
    db.table.assert_not_called()


async def test_record_outcome_emits_event_even_if_decision_logger_fails() -> None:
    loop, db, _, dec_logger, _ = _make_loop()
    dec_logger.record_outcome.side_effect = RuntimeError("supabase unavail")

    await loop.record_outcome(
        client_id="c1",
        decision_id="dec-1",
        outcome="positive",
        source_employee_id="outreach-manager",
    )

    # decision_logger backfill failed
    dec_logger.record_outcome.assert_awaited_once()
    # But learning_event still emitted
    db.table.assert_called_once_with("learning_events")


async def test_record_outcome_swallows_event_failure() -> None:
    """Both branches can fail without raising — the loop never breaks the caller."""
    loop, _, _, _, _ = _make_loop(insert_data=[])

    # Should not raise
    await loop.record_outcome(
        client_id="c1",
        decision_id="dec-1",
        outcome="positive",
        source_employee_id="outreach-manager",
    )
