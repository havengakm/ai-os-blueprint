"""Tests for ``aios.foundation.knowledge.KnowledgeStore``.

Two retrieval paths:
  - similarity-search via ``db.rpc('match_knowledge_base', ...)`` when an
    embedder is configured
  - keyword fallback via ``db.table('knowledge_base').select(...)`` when
    no embedder is available

Both paths must fail soft (return []) on exceptions.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aios.foundation.knowledge import KnowledgeStore


def _rpc_db(rpc_return: Any) -> MagicMock:
    resp = MagicMock()
    resp.data = rpc_return
    chain = MagicMock()
    chain.execute = AsyncMock(return_value=resp)
    db = MagicMock()
    db.rpc.return_value = chain
    return db


def _table_db(select_return: Any) -> tuple[MagicMock, MagicMock]:
    """Chain for the keyword fallback path: table().select().or_().eq().limit().execute()."""
    resp = MagicMock()
    resp.data = select_return
    chain = MagicMock()
    chain.select.return_value = chain
    chain.or_.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute = AsyncMock(return_value=resp)

    db = MagicMock()
    db.table.return_value = chain
    return db, chain


# --------------------------------------------------------------------------- #
# Similarity-search path                                                      #
# --------------------------------------------------------------------------- #


async def test_retrieve_happy_path_calls_match_knowledge_base_rpc() -> None:
    rows = [
        {
            "source": "nick_saraev",
            "category": "copywriting",
            "title": "AIDA Framework",
            "content": "Attention, Interest, Desire, Action...",
            "similarity": 0.88,
        },
    ]
    db = _rpc_db(rows)
    embedder = AsyncMock(return_value=[0.25] * 1024)

    store = KnowledgeStore(db=db, embedder=embedder)
    result = await store.retrieve(
        client_id="c1",
        query="cold email for agency founder",
        source="nick_saraev",
        limit=5,
    )

    embedder.assert_awaited_once_with("cold email for agency founder")
    db.rpc.assert_called_once()
    rpc_name, rpc_args = db.rpc.call_args.args
    assert rpc_name == "match_knowledge_base"
    assert rpc_args == {
        "query_embedding": [0.25] * 1024,
        "client_id_filter": "c1",
        "source_filter": "nick_saraev",
        "match_count": 5,
    }
    assert len(result) == 1
    assert result[0]["title"] == "AIDA Framework"
    assert result[0]["similarity"] == 0.88


async def test_retrieve_empty_rpc_returns_empty_list() -> None:
    db = _rpc_db([])
    embedder = AsyncMock(return_value=[0.0] * 1024)

    store = KnowledgeStore(db=db, embedder=embedder)
    result = await store.retrieve("c1", "query")

    assert result == []


async def test_retrieve_rpc_failure_fails_soft() -> None:
    chain = MagicMock()
    chain.execute = AsyncMock(side_effect=RuntimeError("rpc boom"))
    db = MagicMock()
    db.rpc.return_value = chain
    embedder = AsyncMock(return_value=[0.0] * 1024)

    store = KnowledgeStore(db=db, embedder=embedder)
    result = await store.retrieve("c1", "query")

    assert result == []


# --------------------------------------------------------------------------- #
# Keyword-fallback path                                                       #
# --------------------------------------------------------------------------- #


async def test_retrieve_without_embedder_falls_back_to_keyword_search() -> None:
    rows = [
        {
            "source": "nick_saraev",
            "category": "copywriting",
            "title": "AIDA",
            "content": "...",
        },
    ]
    db, chain = _table_db(rows)

    store = KnowledgeStore(db=db, embedder=None)
    result = await store.retrieve("c1", "query", source="nick_saraev", limit=3)

    # RPC NEVER called — we went down the table path
    db.rpc.assert_not_called()
    db.table.assert_called_once_with("knowledge_base")
    chain.or_.assert_called_once()
    # Two eq calls: active=True + source=nick_saraev
    assert chain.eq.call_count >= 1
    chain.limit.assert_called_once_with(3)
    assert len(result) == 1
    assert result[0]["title"] == "AIDA"
    assert result[0]["similarity"] is None  # keyword search has no sim score


async def test_keyword_fallback_empty_returns_empty_list() -> None:
    db, _ = _table_db([])
    store = KnowledgeStore(db=db, embedder=None)
    result = await store.retrieve("c1", "query")
    assert result == []


async def test_keyword_fallback_exception_returns_empty_list() -> None:
    chain = MagicMock()
    chain.select.return_value = chain
    chain.or_.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute = AsyncMock(side_effect=RuntimeError("boom"))
    db = MagicMock()
    db.table.return_value = chain

    store = KnowledgeStore(db=db, embedder=None)
    result = await store.retrieve("c1", "query")
    assert result == []


# --------------------------------------------------------------------------- #
# format_for_prompt                                                           #
# --------------------------------------------------------------------------- #


def test_format_for_prompt_empty_returns_empty_string() -> None:
    store = KnowledgeStore(db=MagicMock(), embedder=None)
    assert store.format_for_prompt([]) == ""


def test_format_for_prompt_renders_chunks() -> None:
    store = KnowledgeStore(db=MagicMock(), embedder=None)
    chunks = [
        {
            "title": "AIDA Framework",
            "source": "nick_saraev",
            "content": "Attention. Interest. Desire. Action.",
        },
    ]

    out = store.format_for_prompt(chunks)

    assert "AIDA Framework" in out
    assert "nick_saraev" in out
    assert "Attention" in out
