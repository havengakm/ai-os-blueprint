"""Tests for aios.foundation.embedder.VoyageEmbedder.

Uses a FakeVoyageClient for deterministic vectors + token counts.
No real API calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from aios.foundation.embedder import EmbedderCostExceeded, VoyageEmbedder


@dataclass
class FakeEmbeddingsObject:
    embeddings: list[list[float]]
    total_tokens: int


@dataclass
class FakeVoyageClient:
    """Mirrors voyageai.AsyncClient.embed(texts, model, ...) -> EmbeddingsObject."""
    dims: int = 1024
    tokens_per_text: int = 50
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def embed(
        self,
        texts: list[str],
        model: str | None = None,
        input_type: str | None = None,
        **kwargs: Any,
    ) -> FakeEmbeddingsObject:
        self.calls.append({"texts": list(texts), "model": model, "input_type": input_type})
        # Deterministic vectors: value = len(text) / 100 in every dim (easy to assert on).
        embeddings = [[len(t) / 100.0] * self.dims for t in texts]
        total_tokens = self.tokens_per_text * len(texts)
        return FakeEmbeddingsObject(embeddings=embeddings, total_tokens=total_tokens)


async def test_embed_one_returns_1024_dim_vector() -> None:
    fake = FakeVoyageClient()
    e = VoyageEmbedder(api_key="fake", client=fake)

    vec = await e.embed_one("hello")

    assert isinstance(vec, list)
    assert len(vec) == 1024
    assert all(isinstance(v, float) for v in vec)
    assert len(fake.calls) == 1
    assert fake.calls[0]["texts"] == ["hello"]


async def test_embed_batch_autochunks_at_128() -> None:
    """200 texts should produce exactly 2 Voyage calls (128 + 72)."""
    fake = FakeVoyageClient()
    e = VoyageEmbedder(api_key="fake", client=fake)

    texts = [f"text {i}" for i in range(200)]
    vectors = await e.embed_batch(texts)

    assert len(vectors) == 200
    assert all(len(v) == 1024 for v in vectors)
    assert len(fake.calls) == 2
    assert len(fake.calls[0]["texts"]) == 128
    assert len(fake.calls[1]["texts"]) == 72
    assert e.call_count == 2


async def test_cost_accumulates_across_calls() -> None:
    fake = FakeVoyageClient(tokens_per_text=100)
    e = VoyageEmbedder(api_key="fake", client=fake)

    assert e.total_cost_cents == 0.0
    assert e.call_count == 0

    await e.embed_one("one")
    cost_after_1 = e.total_cost_cents
    calls_after_1 = e.call_count

    await e.embed_batch(["a", "b", "c"])
    cost_after_2 = e.total_cost_cents
    calls_after_2 = e.call_count

    assert cost_after_1 > 0
    assert cost_after_2 > cost_after_1  # monotonic
    assert calls_after_2 == calls_after_1 + 1
    # Cost math: voyage-3 = 6 cents/1M tokens. 100 tokens = 0.0006 cents.
    assert cost_after_1 == pytest.approx(0.0006, rel=1e-3)


async def test_cost_cap_triggers_before_api_call() -> None:
    """Oversized input should raise EmbedderCostExceeded BEFORE Voyage is called."""
    fake = FakeVoyageClient()
    # Tight cap — $0.00001. Any real batch exceeds this.
    e = VoyageEmbedder(api_key="fake", client=fake, cost_cap_cents_per_call=0)

    huge_text = "x" * 10_000  # ~2500 tokens
    with pytest.raises(EmbedderCostExceeded):
        await e.embed_one(huge_text)

    # Critical: the guard triggers BEFORE the client is called.
    assert len(fake.calls) == 0
    assert e.call_count == 0
    assert e.total_cost_cents == 0.0


async def test_call_shortcut_matches_knowledgestore_contract() -> None:
    """KnowledgeStore and MemoryStore expect `async callable(text) -> list[float]`."""
    fake = FakeVoyageClient()
    e = VoyageEmbedder(api_key="fake", client=fake)

    vec = await e("some query text")

    assert isinstance(vec, list)
    assert len(vec) == 1024


async def test_embed_batch_empty_input() -> None:
    """Empty input -> no calls, no cost."""
    fake = FakeVoyageClient()
    e = VoyageEmbedder(api_key="fake", client=fake)

    result = await e.embed_batch([])

    assert result == []
    assert len(fake.calls) == 0
    assert e.call_count == 0


async def test_embed_batch_preserves_order() -> None:
    fake = FakeVoyageClient()
    e = VoyageEmbedder(api_key="fake", client=fake)

    texts = ["a", "bb", "ccc", "dddd"]
    vectors = await e.embed_batch(texts)

    # Fake client returns [len(text) / 100] * 1024, so checking first dim preserves order.
    assert vectors[0][0] == pytest.approx(0.01)
    assert vectors[1][0] == pytest.approx(0.02)
    assert vectors[2][0] == pytest.approx(0.03)
    assert vectors[3][0] == pytest.approx(0.04)
