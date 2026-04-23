# SOP: Voyage Embedder Setup
Version: 1.0
Last reviewed: 2026-04-23
Owner: Kirsten / AIOS operator

## Purpose

Set up and verify the Voyage AI embedder that powers pgvector similarity search across memory, knowledge, and decision history. Every similarity search in the foundation loop (past decisions, relevant knowledge, business context) rides on this embedder.

Implementation: [aios/foundation/embedder.py](../../../aios/foundation/embedder.py).

## Trigger

- First-time deploy (new client, new environment).
- `VOYAGE_API_KEY` rotates (monthly, or after any suspected leak).
- Embedding-dependent features degrade (empty similarity results, high `embedding IS NULL` count on new writes).
- Dimension or model change proposed (requires matching migration).

## Inputs

- `VOYAGE_API_KEY` from the Voyage dashboard: https://www.voyageai.com/.
- **REQUIRED: payment method on the Voyage account.** The free tier is 3 RPM, which cascades into 429s as soon as an enrich-stage batch touches 5+ contacts. Symptom: the Claude Deep Research prompt gets through but every call that follows it in the same minute fails, the daemon logs a wall of `429 rate limit`, and icebreaker_content stays empty. Add a payment method before the first real run; $10 of credit covers thousands of contacts.
- Model name. Default: `voyage-3` (1024-dim). MUST match the `VECTOR(1024)` columns defined across migrations 001 and 005 (see [scripts/sql/005_foundation_completion.sql](../../../scripts/sql/005_foundation_completion.sql)).
- Optional: `VOYAGE_MODEL` environment override (only when intentionally changing models alongside a vector-column migration).

## Outputs

- A working [VoyageEmbedder](../../../aios/foundation/embedder.py) instance attached to every foundation module via [SystemRegistry](../../../aios/foundation/registry.py).
- Vectors in `decision_log.embedding`, `knowledge_base.embedding`, `business_context.embedding`, `client_facts.embedding` with shape `VECTOR(1024)`.

---

## Model + contract

[VoyageEmbedder](../../../aios/foundation/embedder.py) ships the following contract:

| Attribute | Value | Notes |
|---|---|---|
| `MODEL_DEFAULT` | `voyage-3` | 1024-dim output. |
| `DIMENSIONS` | `1024` | Matches `VECTOR(1024)` pgvector columns across migrations. |
| `MAX_BATCH_SIZE` | `128` | Voyage API per-call limit. `embed_batch` auto-chunks. |
| `COST_PER_1M_TOKENS_CENTS` | `6.0` | $0.06 / 1M input tokens. |
| `cost_cap_cents_per_call` | `500` (= $5) | Per-call cap. Raises `EmbedderCostExceeded` BEFORE calling Voyage when the estimate breaches cap. |

Async contract used by KnowledgeStore / MemoryStore:

```python
async def __call__(self, text: str) -> list[float]: ...
async def embed_one(self, text: str) -> list[float]: ...
async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
```

Single-text convenience is `embed_one`. Batch embedding is `embed_batch` (auto-chunks > 128 into multiple Voyage calls).

---

## Environment setup

Add to `.env`:

```bash
VOYAGE_API_KEY=pa-...         # required
VOYAGE_MODEL=voyage-3         # optional override; default is voyage-3
```

[api/deps.py::get_registry](../../../api/deps.py) raises on startup if `VOYAGE_API_KEY` is missing:

```
RuntimeError: Missing required environment variable: VOYAGE_API_KEY.
Required for the foundation embedder. Check .env or environment config.
```

The registry is an lru_cached singleton. After rotating the key, restart the process; do not hot-reload.

---

## Verification

One-liner after setting the env var:

```bash
uv run python -c "
import asyncio, os
from aios.foundation.embedder import VoyageEmbedder

async def _check():
    emb = VoyageEmbedder(api_key=os.environ['VOYAGE_API_KEY'])
    vec = await emb.embed_one('foundation embedder smoke test')
    print(f'dimensions={len(vec)}  cost_cents={emb.total_cost_cents:.6f}')

asyncio.run(_check())
"
```

Expected output:

```
dimensions=1024  cost_cents=0.000...
```

Full unit suite:

```bash
uv run pytest tests/test_foundation/test_embedder.py -q
```

Confirm vectors are landing in Postgres:

```sql
-- Non-null embedding count on a recent write
SELECT COUNT(*) FROM decision_log
WHERE client_id = '<client-id>'
  AND embedding IS NOT NULL
  AND created_at > now() - interval '1 day';
```

---

## Cost guards

Voyage `voyage-3` at $0.06 / 1M tokens.

| Operation | Typical size | Est. cost |
|---|---|---|
| Single embed (500 tokens) | 500 tok | ~$0.00003 |
| Batch of 128 (~50 tok each) | 6,400 tok | ~$0.000384 |
| Full foundation prime (5 searches × 1 query embed each) | ~250 tok | ~$0.000015 |

Guards in place:

1. **Per-call cap:** `cost_cap_cents_per_call` (default 500 cents = $5) rejects any single call whose estimate breaches cap. Raises `EmbedderCostExceeded`.
2. **Batching:** `embed_batch` chunks up to `MAX_BATCH_SIZE=128` per Voyage call; larger inputs paid per-chunk, not per-item.
3. **Monthly budget:** log embedder spend via `decision_log` + weekly `/prime` review. Per `feedback_cost_management.md`: soft alert at 70%, hard alert at 90%, auto-pause at 100% of the client's tier budget.

Do NOT raise `cost_cap_cents_per_call` without measured evidence of a legitimate spike. The cap catches runaway prompts, not normal traffic.

Track cumulative spend via the embedder's own counters:

```python
emb.total_cost_cents   # float, total since process start
emb.call_count         # int, calls made since process start
```

Plan 2 wires these into the `budget_tracker` for tier-level enforcement.

---

## Dimension lock: do NOT change silently

The 1024-dim choice is baked into every `VECTOR(1024)` pgvector column in migrations 001 and 005. Changing model or dim requires:

1. A new migration that recreates each embedding column at the new dimension AND recreates every ivfflat index (ivfflat indexes carry dimension in their metadata).
2. A backfill pass that re-embeds every row under the new model.
3. A cutover: old model rows with old-dim vectors coexist with new ones only if similarity searches filter by a generation column. Simplest path is backfill-then-swap with downtime.

If you are here reading this because dimensions mismatch, you probably swapped models without the migration. Roll back to the model that matches the DB columns.

---

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `401 unauthorized` from Voyage | Missing or invalid `VOYAGE_API_KEY`. | Rotate key in the Voyage dashboard; update `.env`; restart process. |
| `EmbedderCostExceeded: Estimated call cost X cents exceeds cap Y` | Prompt too large for cap. | Usually a bug (runaway text input). Inspect the call site; do NOT raise cap without measured evidence. |
| `dimension mismatch (1536 vs 1024)` on pgvector write | Model was swapped but vector columns were not migrated. | Switch back to `voyage-3`, or run a migration that recreates the vector columns at the new dim + backfill. |
| `429 rate limit` | Spike in concurrent embed calls. | Voyage SDK handles backoff; if persistent, batch harder (fewer calls, more items per call). Do NOT add retry loops on top of the SDK's backoff. |
| `embedding IS NULL` on fresh rows | Embedder raised during write and the insert proceeded without a vector. | Check process logs for embedder errors; backfill with `embed_batch` over affected rows; fix the underlying failure. |
| `ImportError: No module named 'voyageai'` | Dependency not installed. | `uv sync` or `uv pip install voyageai`. |

## Escalation

- Three consecutive `EmbedderCostExceeded` on the same code path: escalate per CLAUDE.md; do NOT patch by raising the cap.
- Sustained `429` after batching: escalate to Voyage support with a sample timestamp window.
- Dimension mismatch in production: halt writes to the affected table; plan the migration before resuming.

## Automation notes

- **Fully automated:** embedding, batching, cost gate per call, cost counter.
- **Operator-driven:** API key rotation, model selection, monthly budget review.
- **Not automated:** dim-change migration (intentional: high-risk, requires backfill).

## Change log

- v1.0, 2026-04-23, initial (Task 18).
