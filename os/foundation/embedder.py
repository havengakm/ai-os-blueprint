"""Voyage AI embedder — produces 1024-dim vectors for pgvector.

Wraps the voyageai SDK with:
  - Model selection (default voyage-3, outputs 1024 dims matching our migrations)
  - Batch support (Voyage API accepts up to 128 texts per call)
  - Cost tracking (total + per-call, exposed via .total_cost_cents / .call_count)
  - Cost guard (reject a call when a configured cap would be exceeded)
  - Async HTTP via voyageai's async client

Contract matches the embedder callable used by KnowledgeStore + MemoryStore:
    async callable(text: str) -> list[float]

Single-text convenience is just .embed_one(text); batch is .embed_batch(texts).

Cost math: voyage-3 = $0.06 / 1M tokens. For the AIOS use case (<=200-char
context chunks), average ~50 tokens per text -> ~$0.000003 / embed. A batch
of 128 = ~$0.000384. Cost guard defaults to $5/call (generous) to catch
runaway prompts, not to rate-limit normal use.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class EmbedderCostExceeded(Exception):
    """Raised when a single call would exceed the configured cost cap."""


def _estimate_tokens(texts: list[str]) -> int:
    """Rough token estimate: ~4 chars per token. Voyage's own tokenizer is
    more accurate, but a conservative estimate is fine for cost gating.
    We over-estimate slightly so the cost guard triggers BEFORE the call."""
    total_chars = sum(len(t) for t in texts)
    # Ceiling division by 4, guaranteed >= 1 per non-empty text.
    return max(1, (total_chars + 3) // 4)


class VoyageEmbedder:
    """Async wrapper around voyageai.AsyncClient with batching + cost tracking."""

    MODEL_DEFAULT: str = "voyage-3"
    DIMENSIONS: int = 1024           # matches VECTOR(1024) across migrations 001 + 005
    MAX_BATCH_SIZE: int = 128        # Voyage API limit
    COST_PER_1M_TOKENS_CENTS: float = 6.0  # $0.06/1M = 6 cents per 1M tokens

    def __init__(
        self,
        api_key: str,
        *,
        model: str = MODEL_DEFAULT,
        cost_cap_cents_per_call: int = 500,  # $5 per call
        client: Any = None,                  # for test injection
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._cost_cap = cost_cap_cents_per_call
        self._client = client  # if None, constructed lazily in _get_client()
        self.total_cost_cents: float = 0.0
        self.call_count: int = 0

    def _get_client(self) -> Any:
        """Lazily construct the Voyage async client. Kept lazy so the
        embedder can be imported without a live API key (tests)."""
        if self._client is None:
            import voyageai
            self._client = voyageai.AsyncClient(api_key=self._api_key)
        return self._client

    async def embed_one(self, text: str) -> list[float]:
        """Embed a single text. Returns a 1024-dim list[float]."""
        vectors = await self.embed_batch([text])
        return vectors[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Auto-chunks into MAX_BATCH_SIZE subcalls.

        Raises EmbedderCostExceeded if an individual Voyage call's estimated
        cost would breach cost_cap_cents_per_call.

        Returns one list[float] per input text, in the same order.
        """
        if not texts:
            return []

        out: list[list[float]] = []
        client = self._get_client()

        for start in range(0, len(texts), self.MAX_BATCH_SIZE):
            chunk = texts[start:start + self.MAX_BATCH_SIZE]

            # Estimate + cost-gate BEFORE making the API call.
            est_tokens = _estimate_tokens(chunk)
            est_cost_cents = (est_tokens / 1_000_000.0) * self.COST_PER_1M_TOKENS_CENTS
            if est_cost_cents > self._cost_cap:
                raise EmbedderCostExceeded(
                    f"Estimated call cost {est_cost_cents:.4f} cents exceeds cap "
                    f"{self._cost_cap} cents (texts={len(chunk)}, est_tokens={est_tokens})"
                )

            result = await client.embed(
                chunk,
                model=self._model,
                input_type="document",
            )

            # voyageai returns an EmbeddingsObject with .embeddings (list[list[float]])
            # and .total_tokens (int). Our fake client mirrors that shape.
            embeddings = result.embeddings
            actual_tokens = getattr(result, "total_tokens", est_tokens)
            actual_cost_cents = (actual_tokens / 1_000_000.0) * self.COST_PER_1M_TOKENS_CENTS

            self.total_cost_cents += actual_cost_cents
            self.call_count += 1

            logger.debug(
                "EMBED: %d texts, %d tokens, %.4f cents (total: %.4f cents over %d calls)",
                len(chunk), actual_tokens, actual_cost_cents,
                self.total_cost_cents, self.call_count,
            )

            out.extend(embeddings)

        return out

    async def __call__(self, text: str) -> list[float]:
        """Async forwarder for KnowledgeStore / MemoryStore callable contract."""
        return await self.embed_one(text)
