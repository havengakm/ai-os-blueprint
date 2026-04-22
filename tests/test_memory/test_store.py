"""Tests for ``aios.memory.store.MemoryStore``.

MemoryStore is the unified retrieval layer every system calls via
``load_full_context(client_id, task_query=...)``. It fans out in parallel:
  - ``retrieve_business_context`` (RPC if query + embedder else table)
  - ``retrieve_context_registry`` (table)
  - ``retrieve_facts`` (table)
  - ``retrieve_history`` (table, only when user_id given)
  - ``retrieve_knowledge`` (RPC, only when task_query given + embedder)
  - ``retrieve_past_decisions`` (RPC, only when task_query given + embedder)

Individual retrieval failures must not break the aggregate — load_full_context
catches per-task exceptions via ``asyncio.gather(..., return_exceptions=True)``
and substitutes ``[]``.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aios.memory.store import MemoryStore


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _build_db(*, rpc_returns: dict[str, Any] | None = None,
              table_returns: dict[str, Any] | None = None) -> MagicMock:
    """Build a MagicMock db whose rpc() and table() behaviours are driven
    by name -> data dicts.

    For table(): every chained builder method returns self, and execute()
    is an AsyncMock yielding whatever table_returns maps for that table.
    """
    rpc_returns = rpc_returns or {}
    table_returns = table_returns or {}

    db = MagicMock()

    def _rpc(name: str, _args: dict[str, Any]) -> MagicMock:
        resp = MagicMock()
        resp.data = rpc_returns.get(name, [])
        chain = MagicMock()
        chain.execute = AsyncMock(return_value=resp)
        return chain

    db.rpc.side_effect = _rpc

    def _table(name: str) -> MagicMock:
        resp = MagicMock()
        resp.data = table_returns.get(name, [])
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
        chain.execute = AsyncMock(return_value=resp)
        return chain

    db.table.side_effect = _table
    return db


# --------------------------------------------------------------------------- #
# retrieve_business_context                                                   #
# --------------------------------------------------------------------------- #


async def test_retrieve_business_context_without_query_hits_table() -> None:
    bc_rows = [{"section": "brand", "content": "We help CRO agencies"}]
    db = _build_db(table_returns={"business_context": bc_rows})
    store = MemoryStore(db=db)

    result = await store.retrieve_business_context("c1")

    assert result == bc_rows
    db.table.assert_called_once_with("business_context")
    db.rpc.assert_not_called()


async def test_retrieve_business_context_with_query_and_embedder_uses_rpc() -> None:
    db = _build_db(rpc_returns={"match_business_context": [{"section": "s", "content": "c"}]})
    embedder = AsyncMock(return_value=[0.0] * 1024)

    store = MemoryStore(db=db, embedder=embedder)
    result = await store.retrieve_business_context("c1", query="CRO niche", limit=5)

    embedder.assert_awaited_once_with("CRO niche")
    db.rpc.assert_called_once()
    rpc_name, rpc_args = db.rpc.call_args.args
    assert rpc_name == "match_business_context"
    assert rpc_args["client_id_filter"] == "c1"
    assert rpc_args["match_count"] == 5
    assert len(result) == 1


async def test_retrieve_business_context_rpc_failure_falls_back_to_table() -> None:
    """If the RPC raises, module falls back to the plain table query."""
    bc_rows = [{"section": "brand", "content": "fallback"}]

    chain_table = MagicMock()
    chain_table.select.return_value = chain_table
    chain_table.eq.return_value = chain_table
    resp_table = MagicMock()
    resp_table.data = bc_rows
    chain_table.execute = AsyncMock(return_value=resp_table)

    chain_rpc = MagicMock()
    chain_rpc.execute = AsyncMock(side_effect=RuntimeError("rpc down"))

    db = MagicMock()
    db.rpc.return_value = chain_rpc
    db.table.return_value = chain_table

    embedder = AsyncMock(return_value=[0.0] * 1024)
    store = MemoryStore(db=db, embedder=embedder)
    result = await store.retrieve_business_context("c1", query="q")

    assert result == bc_rows


# --------------------------------------------------------------------------- #
# retrieve_facts                                                              #
# --------------------------------------------------------------------------- #


async def test_retrieve_facts_returns_rows() -> None:
    facts = [{"key": "tz", "value": "UTC", "source": "conversation"}]
    db = _build_db(table_returns={"client_facts": facts})
    store = MemoryStore(db=db)

    result = await store.retrieve_facts("c1")

    assert result == facts


async def test_retrieve_facts_empty_returns_empty_list() -> None:
    db = _build_db(table_returns={"client_facts": []})
    store = MemoryStore(db=db)
    result = await store.retrieve_facts("c1")
    assert result == []


# --------------------------------------------------------------------------- #
# retrieve_knowledge                                                          #
# --------------------------------------------------------------------------- #


async def test_retrieve_knowledge_without_embedder_returns_empty() -> None:
    db = _build_db()
    store = MemoryStore(db=db, embedder=None)

    result = await store.retrieve_knowledge("c1", "query")

    assert result == []
    db.rpc.assert_not_called()


async def test_retrieve_knowledge_with_embedder_calls_rpc() -> None:
    rows = [{"source": "nick", "title": "AIDA", "content": "...", "similarity": 0.9}]
    db = _build_db(rpc_returns={"match_knowledge_base": rows})
    embedder = AsyncMock(return_value=[0.1] * 1024)

    store = MemoryStore(db=db, embedder=embedder)
    result = await store.retrieve_knowledge("c1", "cold email", source="nick", limit=3)

    assert result == rows
    rpc_name, rpc_args = db.rpc.call_args.args
    assert rpc_name == "match_knowledge_base"
    assert rpc_args["client_id_filter"] == "c1"
    assert rpc_args["source_filter"] == "nick"


# --------------------------------------------------------------------------- #
# retrieve_past_decisions                                                     #
# --------------------------------------------------------------------------- #


async def test_retrieve_past_decisions_with_embedder_calls_rpc() -> None:
    rows = [{"id": "d1", "decision": "Used AIDA", "outcome": "positive"}]
    db = _build_db(rpc_returns={"match_decisions": rows})
    embedder = AsyncMock(return_value=[0.1] * 1024)

    store = MemoryStore(db=db, embedder=embedder)
    result = await store.retrieve_past_decisions("c1", "copy_variant", "ctx")

    assert result == rows
    rpc_name, _ = db.rpc.call_args.args
    assert rpc_name == "match_decisions"


async def test_retrieve_past_decisions_without_embedder_empty() -> None:
    db = _build_db()
    store = MemoryStore(db=db, embedder=None)
    result = await store.retrieve_past_decisions("c1", "copy_variant", "ctx")
    assert result == []


# --------------------------------------------------------------------------- #
# load_full_context                                                           #
# --------------------------------------------------------------------------- #


async def test_load_full_context_aggregates_all_sources() -> None:
    bc_rows = [{"section": "brand", "content": "CRO agency"}]
    registry_rows = [{"context_type": "person", "key": "founder", "value": "Kirsten", "summary": "s"}]
    facts = [{"key": "tz", "value": "UTC", "source": "conv"}]
    knowledge = [{"source": "nick", "title": "AIDA", "content": "c", "similarity": 0.9}]
    decisions = [{"id": "d1", "decision": "used AIDA", "outcome": "positive"}]

    db = _build_db(
        rpc_returns={
            # task_query + embedder = business_context also goes via RPC
            "match_business_context": bc_rows,
            "match_knowledge_base": knowledge,
            "match_decisions": decisions,
        },
        table_returns={
            "context_registry": registry_rows,
            "client_facts": facts,
        },
    )
    embedder = AsyncMock(return_value=[0.0] * 1024)

    store = MemoryStore(db=db, embedder=embedder)
    ctx = await store.load_full_context(
        client_id="c1", task_query="cold email copywriting",
    )

    assert ctx["business_context"] == bc_rows
    assert ctx["context_registry"] == registry_rows
    assert ctx["client_facts"] == facts
    assert ctx["relevant_knowledge"] == knowledge
    assert ctx["past_decisions"] == decisions
    assert "conversation_history" not in ctx  # user_id not provided


async def test_load_full_context_skips_knowledge_without_task_query() -> None:
    db = _build_db(table_returns={"business_context": [], "context_registry": [], "client_facts": []})
    store = MemoryStore(db=db, embedder=AsyncMock(return_value=[0.0] * 1024))

    ctx = await store.load_full_context(client_id="c1")

    # No task_query = no knowledge/past_decisions keys
    assert "relevant_knowledge" not in ctx
    assert "past_decisions" not in ctx
    assert "conversation_history" not in ctx
    assert ctx["business_context"] == []
    assert ctx["client_facts"] == []


async def test_load_full_context_includes_history_when_user_id_given() -> None:
    history = [{"role": "user", "content": "hi", "created_at": "2025-01-01"}]
    db = _build_db(
        table_returns={
            "business_context": [], "context_registry": [], "client_facts": [],
            "conversation_history": history,
        },
    )
    store = MemoryStore(db=db)

    ctx = await store.load_full_context(client_id="c1", user_id="u1")

    assert ctx["conversation_history"] == history


async def test_load_full_context_survives_per_task_failure() -> None:
    """If one fetch raises, that key maps to [] and others still populate."""
    bc_rows = [{"section": "s", "content": "c"}]
    facts = [{"key": "tz", "value": "UTC", "source": "conv"}]

    # business_context and client_facts succeed; context_registry raises
    def _table(name: str) -> MagicMock:
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.limit.return_value = chain
        chain.order.return_value = chain

        if name == "business_context":
            resp = MagicMock()
            resp.data = bc_rows
            chain.execute = AsyncMock(return_value=resp)
        elif name == "client_facts":
            resp = MagicMock()
            resp.data = facts
            chain.execute = AsyncMock(return_value=resp)
        elif name == "context_registry":
            chain.execute = AsyncMock(side_effect=RuntimeError("registry down"))
        else:
            resp = MagicMock()
            resp.data = []
            chain.execute = AsyncMock(return_value=resp)
        return chain

    db = MagicMock()
    db.table.side_effect = _table
    store = MemoryStore(db=db)

    ctx = await store.load_full_context(client_id="c1")

    assert ctx["business_context"] == bc_rows
    assert ctx["client_facts"] == facts
    # Failed fetch maps to []
    assert ctx["context_registry"] == []


# --------------------------------------------------------------------------- #
# save_fact / save_turn                                                       #
# --------------------------------------------------------------------------- #


async def test_save_fact_upserts_to_client_facts() -> None:
    db = _build_db()
    store = MemoryStore(db=db)

    await store.save_fact("c1", "tz", "Europe/London", source="conversation")

    db.table.assert_called_once_with("client_facts")


async def test_save_turn_inserts_to_conversation_history() -> None:
    db = _build_db()
    store = MemoryStore(db=db)

    await store.save_turn("c1", "u1", "user", "hello")

    db.table.assert_called_once_with("conversation_history")


# --------------------------------------------------------------------------- #
# format_context_for_prompt                                                   #
# --------------------------------------------------------------------------- #


def test_format_context_for_prompt_renders_sections() -> None:
    db = _build_db()
    store = MemoryStore(db=db)
    ctx = {
        "business_context": [{"section": "brand", "content": "CRO agency"}],
        "context_registry": [{"context_type": "t", "key": "k", "summary": "s"}],
        "client_facts": [{"key": "tz", "value": "UTC"}],
        "relevant_knowledge": [{"title": "AIDA", "source": "nick", "content": "c"}],
        "past_decisions": [{"decision": "Used AIDA", "outcome": "positive"}],
    }

    out = store.format_context_for_prompt(ctx)

    assert "Business Context" in out
    assert "CRO agency" in out
    assert "Structured Context" in out
    assert "Known Facts" in out
    assert "Relevant Expert Knowledge" in out
    assert "Similar Past Decisions" in out


def test_format_context_for_prompt_empty_context_returns_empty() -> None:
    db = _build_db()
    store = MemoryStore(db=db)
    out = store.format_context_for_prompt({})
    assert out == ""
