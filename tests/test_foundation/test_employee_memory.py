"""Tests for ``aios.foundation.employee_memory.EmployeeMemoryPgVector``.

Same async-Supabase mock pattern as ``test_decision_logger`` — every
intermediate builder call returns self; ``.execute()`` is an AsyncMock
yielding a fake response with ``.data``. The RPC call also goes through
the same builder.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from aios.foundation.employee_memory import EmployeeMemoryPgVector, Memory


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #


def _make_execute(data: Any) -> AsyncMock:
    resp = MagicMock()
    resp.data = data
    return AsyncMock(return_value=resp)


def _make_db(exec_return: Any) -> tuple[MagicMock, MagicMock, AsyncMock]:
    chain = MagicMock()
    chain.insert.return_value = chain
    chain.upsert.return_value = chain
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    exec_mock = _make_execute(exec_return)
    chain.execute = exec_mock

    db = MagicMock()
    db.table.return_value = chain
    db.rpc.return_value = chain
    return db, chain, exec_mock


# --------------------------------------------------------------------------- #
# remember                                                                     #
# --------------------------------------------------------------------------- #


async def test_remember_returns_id_on_success() -> None:
    db, chain, _ = _make_db([{"id": "mem-123"}])
    memory = EmployeeMemoryPgVector(db=db)

    row_id = await memory.remember(
        client_id="kirsten-client-zero",
        employee_id="prospect-researcher",
        content="Found 18 new agencies on /branding last week.",
        kind="job_completion",
        metadata={"playbook": "lead_generation", "scored_count": 11},
    )

    assert row_id == "mem-123"
    db.table.assert_called_once_with("employee_memory")
    insert_payload = chain.insert.call_args.args[0]
    assert insert_payload["client_id"] == "kirsten-client-zero"
    assert insert_payload["employee_id"] == "prospect-researcher"
    assert insert_payload["kind"] == "job_completion"
    assert insert_payload["content"].startswith("Found 18")
    assert "metadata" in insert_payload
    # No embedder wired; embedding key absent.
    assert "embedding" not in insert_payload


async def test_remember_includes_embedding_when_embedder_wired() -> None:
    """If an embedder is passed, content gets embedded and stored."""
    db, chain, _ = _make_db([{"id": "mem-456"}])
    embedder = AsyncMock(return_value=[0.1] * 1024)
    memory = EmployeeMemoryPgVector(db=db, embedder=embedder)

    await memory.remember(
        client_id="c1",
        employee_id="content-writer",
        content="Wrote 5 LinkedIn posts about agency growth pain.",
        kind="job_completion",
    )

    embedder.assert_awaited_once_with(
        "Wrote 5 LinkedIn posts about agency growth pain."
    )
    insert_payload = chain.insert.call_args.args[0]
    assert insert_payload["embedding"] == [0.1] * 1024


async def test_remember_tolerates_embedder_failure() -> None:
    """Embedder failure is non-fatal — row stored without embedding."""
    db, chain, _ = _make_db([{"id": "mem-789"}])
    embedder = AsyncMock(side_effect=RuntimeError("embedder down"))
    memory = EmployeeMemoryPgVector(db=db, embedder=embedder)

    row_id = await memory.remember(
        client_id="c1",
        employee_id="prospect-researcher",
        content="Sample memory.",
        kind="observation",
    )

    assert row_id == "mem-789"
    insert_payload = chain.insert.call_args.args[0]
    assert "embedding" not in insert_payload


async def test_remember_raises_on_empty_response() -> None:
    """Insert returning no rows is a real failure (DB constraint, RLS, etc)."""
    db, _, _ = _make_db([])
    memory = EmployeeMemoryPgVector(db=db)

    with pytest.raises(RuntimeError, match="returned no rows"):
        await memory.remember(
            client_id="c1",
            employee_id="prospect-researcher",
            content="x",
            kind="observation",
        )


# --------------------------------------------------------------------------- #
# recall                                                                       #
# --------------------------------------------------------------------------- #


async def test_recall_without_embedder_returns_empty() -> None:
    """No embedder = no semantic search. Returns []."""
    db, _, _ = _make_db([])
    memory = EmployeeMemoryPgVector(db=db)

    matches = await memory.recall(
        client_id="c1",
        employee_id="prospect-researcher",
        query="What did I find on Clutch?",
    )

    assert matches == []
    db.rpc.assert_not_called()


async def test_recall_calls_match_employee_memory_rpc() -> None:
    rows = [
        {
            "id": "mem-1",
            "employee_id": "prospect-researcher",
            "kind": "job_completion",
            "content": "Found 18 agencies last week.",
            "metadata": {"playbook": "lead_generation"},
            "created_at": "2026-04-29T10:00:00Z",
            "similarity": 0.91,
        }
    ]
    db, _, _ = _make_db(rows)
    embedder = AsyncMock(return_value=[0.2] * 1024)
    memory = EmployeeMemoryPgVector(db=db, embedder=embedder)

    matches = await memory.recall(
        client_id="kirsten-client-zero",
        employee_id="prospect-researcher",
        query="What did I find on Clutch?",
        k=5,
    )

    assert len(matches) == 1
    assert isinstance(matches[0], Memory)
    assert matches[0].id == "mem-1"
    assert matches[0].similarity == 0.91
    assert matches[0].metadata["playbook"] == "lead_generation"

    # Verify the RPC was called with the right args.
    rpc_call = db.rpc.call_args
    assert rpc_call.args[0] == "match_employee_memory"
    rpc_args = rpc_call.args[1]
    assert rpc_args["p_client_id"] == "kirsten-client-zero"
    assert rpc_args["p_employee_id"] == "prospect-researcher"
    assert rpc_args["p_query_embedding"] == [0.2] * 1024
    assert rpc_args["p_match_count"] == 5


async def test_recall_passes_kind_filter_through() -> None:
    db, _, _ = _make_db([])
    embedder = AsyncMock(return_value=[0.3] * 1024)
    memory = EmployeeMemoryPgVector(db=db, embedder=embedder)

    await memory.recall(
        client_id="c1",
        employee_id="content-writer",
        query="x",
        kind_filter={"job_completion", "outcome"},
    )

    rpc_args = db.rpc.call_args.args[1]
    assert set(rpc_args["p_kind_filter"]) == {"job_completion", "outcome"}


async def test_recall_returns_empty_on_embedder_failure() -> None:
    db, _, _ = _make_db([])
    embedder = AsyncMock(side_effect=RuntimeError("embedder down"))
    memory = EmployeeMemoryPgVector(db=db, embedder=embedder)

    matches = await memory.recall(
        client_id="c1",
        employee_id="prospect-researcher",
        query="x",
    )

    assert matches == []
    db.rpc.assert_not_called()


async def test_recall_handles_string_metadata_in_row() -> None:
    """Older rows might have stringified-JSON metadata. Parse it."""
    rows = [
        {
            "id": "mem-1",
            "employee_id": "prospect-researcher",
            "kind": "job_completion",
            "content": "x",
            "metadata": '{"playbook": "lead_generation", "n": 3}',
            "created_at": "2026-04-29T10:00:00Z",
            "similarity": 0.5,
        }
    ]
    db, _, _ = _make_db(rows)
    embedder = AsyncMock(return_value=[0.1] * 1024)
    memory = EmployeeMemoryPgVector(db=db, embedder=embedder)

    matches = await memory.recall(
        client_id="c1",
        employee_id="prospect-researcher",
        query="x",
    )

    assert matches[0].metadata == {"playbook": "lead_generation", "n": 3}


# --------------------------------------------------------------------------- #
# subscribe                                                                    #
# --------------------------------------------------------------------------- #


async def test_subscribe_writes_upsert_with_default_filter() -> None:
    db, chain, _ = _make_db([{"client_id": "c1"}])
    memory = EmployeeMemoryPgVector(db=db)

    await memory.subscribe(
        client_id="kirsten-client-zero",
        employee_id="content-writer",
        source_employee_id="outreach-manager",
    )

    db.table.assert_called_once_with("employee_subscriptions")
    upsert_payload = chain.upsert.call_args.args[0]
    assert upsert_payload["client_id"] == "kirsten-client-zero"
    assert upsert_payload["employee_id"] == "content-writer"
    assert upsert_payload["source_employee_id"] == "outreach-manager"
    # Default filter
    assert set(upsert_payload["kind_filter"]) == {"job_completion", "learning"}
    # on_conflict kwarg passed correctly
    assert chain.upsert.call_args.kwargs.get("on_conflict") == (
        "client_id,employee_id,source_employee_id"
    )


async def test_subscribe_respects_explicit_kind_filter() -> None:
    db, chain, _ = _make_db([{"client_id": "c1"}])
    memory = EmployeeMemoryPgVector(db=db)

    await memory.subscribe(
        client_id="c1",
        employee_id="prospect-researcher",
        source_employee_id="outreach-manager",
        kind_filter={"outcome", "observation"},
    )

    upsert_payload = chain.upsert.call_args.args[0]
    assert set(upsert_payload["kind_filter"]) == {"outcome", "observation"}
