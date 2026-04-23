# SOP: Foundation Wiring
Version: 1.0
Last reviewed: 2026-04-23
Owner: Kirsten / AIOS operator

## Purpose

Explain the foundation layer, how it is wired via [SystemRegistry](../../../aios/foundation/registry.py), and how it is injected into every system through [api/deps.py](../../../api/deps.py). Use this SOP when onboarding a developer or diagnosing a foundation-loop failure (decisions not logged, pattern search returning nothing, context empty).

The foundation layer is what makes every system context-aware, autonomy-gated, and self-improving. Every system dispatch MUST run the full foundation loop before touching business logic.

## Trigger

- First-time developer setup on this repo.
- Diagnosing: decision rows missing from `decision_log`, `memory_store` returning empty context, CHECK-constraint violations on `decision_type`, `MemoryStore not injected` errors, Voyage API failures.
- Reviewing a new BaseSystem subclass for compliance with the foundation contract.

## Inputs

- A running Supabase instance with migrations `001_foundation.sql` through `009_trigify_discovery_config.sql` applied.
- `.env` with `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `VOYAGE_API_KEY`.
- Python 3.13 + `uv` installed; `uv sync` has been run at least once.

## Outputs

- A single process-wide [SystemRegistry](../../../aios/foundation/registry.py) holding six foundation modules + ten Supabase backends.
- A process-singleton [ScoutSystem](../../../systems/scout/skill.py) wired from the registry.
- Verified foundation loop: one `decision_log` row per stage per contact after a live run.

---

## The six foundation modules

| Module | File | Role |
|---|---|---|
| `VoyageEmbedder` | [aios/foundation/embedder.py](../../../aios/foundation/embedder.py) | 1024-dim `voyage-3` embeddings. Shared across every module that writes or searches vectors. |
| `DecisionLogger` | [aios/foundation/decision_logger.py](../../../aios/foundation/decision_logger.py) | Writes `decision_log` rows with full context + embedding. Needs embedder. |
| `PatternMatcher` | [aios/foundation/pattern_matcher.py](../../../aios/foundation/pattern_matcher.py) | pgvector similarity over past decisions. Needs embedder. |
| `KnowledgeStore` | [aios/foundation/knowledge.py](../../../aios/foundation/knowledge.py) | Expert framework retrieval. Needs embedder. |
| `AutonomyGate` | [aios/foundation/autonomy.py](../../../aios/foundation/autonomy.py) | Returns `suggest | draft | act_notify | autonomous` per action type. No embedder. |
| `MemoryStore` | [aios/memory/store.py](../../../aios/memory/store.py) | Loads `business_context + client_facts + knowledge + past_decisions` via `load_full_context`. Aggregates the four above. |

---

## The mandatory foundation loop

Every BaseSystem stage dispatch runs this loop before the stage does real work. Source of truth: [BaseSystem](../../../systems/base.py) + [ScoutSystem._prime_foundation](../../../systems/scout/skill.py).

```python
# 1. Load everything the system needs to act
await self.load_foundation(client_id, task_query="...stage-specific query...")
#    → memory_store.load_full_context
#    → populates self.foundation_context with:
#        business_context, client_facts, relevant_knowledge,
#        past_decisions, context_registry

# 2. Check autonomy BEFORE acting
level = await self.check_autonomy(client_id, action_type="source_selection")
#    → returns 'suggest' | 'draft' | 'act_notify' | 'autonomous'

# 3. Query past similar decisions
past = await self.find_similar_decisions(
    client_id,
    decision_type="source_selection",
    current_context="pull stage run",
    limit=5,
)
#    → pgvector similarity over decision_log embeddings

# 4. Stage logic runs here
result = await stage.run(client_id, ...)

# 5. Log the decision (done by the INNER orchestrator, not the Scout wrapper)
await self.log_decision(
    client_id=client_id,
    decision_type="source_selection",
    context={...},
    decision="...",
    reasoning="...",
)
```

Scout groups steps 1-3 into [`_prime_foundation`](../../../systems/scout/skill.py), called at the top of every `run_<stage>` method. Inner orchestrators own step 5. The Scout wrapper does NOT double-log at stage level.

---

## Dependency boot order

Construction flows bottom-up. [build_registry](../../../aios/foundation/registry.py) enforces it.

```
Supabase client  (api/deps.py::get_supabase_client)
      │
      ▼
VoyageEmbedder   (needs VOYAGE_API_KEY)
      │
      ├─► DecisionLogger   (needs embedder)
      ├─► PatternMatcher   (needs embedder)
      ├─► KnowledgeStore   (needs embedder)
      └─► MemoryStore      (needs embedder; internally calls the three above)
      │
AutonomyGate     (db only, no embedder)
      │
      ▼
SystemRegistry   (bundles all 6 foundation modules + 10 Supabase backends)
      │
      ▼
ScoutSystem.from_registry   (lru_cached singleton via _scout_system_singleton)
```

Every backend shares the same `supabase_client`. Every foundation module shares the same `embedder`. The registry is built ONCE per process (lru_cache on `get_registry`).

## Stage dispatch vocabulary (autonomy + decision_type)

Each pipeline stage has a fixed `decision_type` string. It MUST match the CHECK constraint in [005_foundation_completion.sql](../../../scripts/sql/005_foundation_completion.sql); adding a new one requires a migration.

| Stage | `decision_type` | `task_query` (sample) |
|---|---|---|
| pull | `source_selection` | "pull stage, discover new contacts" |
| score (v1) | `score_contact` | "score stage phase=v1" |
| screen | `screen_contact` | "screen stage, hard-gate eligibility" |
| identity | `identity_lookup` | "identity stage, resolve decision-maker" |
| enrich | `enrich_contact` | "enrich stage, augment identified contacts" |
| score (v2) | `score_contact` | "score stage phase=v2" |
| compose | `render_draft` | "cold outbound copywriting frameworks" |

Full allow-list lives in `decision_log_decision_type_check` (migration 005). Adding a new `decision_type` without extending the CHECK = insert fails.

---

## QA

After a seeded run on a real client:

```bash
# 1. Each stage logged exactly once per contact
psql "$SUPABASE_URL" -c "
  SELECT decision_type, COUNT(*)
  FROM decision_log
  WHERE client_id = '<client-id>'
  GROUP BY 1 ORDER BY 1;
"

# 2. Expect 7 rows for a full pipeline pass: one per stage
#    (score_contact shows count=2 because v1 and v2 both log under it)

# 3. Context retrieval is happening
psql "$SUPABASE_URL" -c "
  SELECT COUNT(*) FROM business_context WHERE client_id = '<client-id>';
  SELECT COUNT(*) FROM client_facts WHERE client_id = '<client-id>';
  SELECT COUNT(*) FROM knowledge_base;
"
```

Contract tests:

```bash
uv run pytest tests/test_foundation/ tests/test_e2e/ -q
```

- [tests/test_foundation/](../../../tests/test_foundation/) covers each module in isolation (autonomy, decision_logger, embedder, knowledge, pattern_matcher).
- [tests/test_e2e/test_foundation_loop.py](../../../tests/test_e2e/test_foundation_loop.py) asserts the 7-stage order + the load-before-run invariant.

---

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `MemoryStore not injected` / `AttributeError: NoneType has no attribute 'load_full_context'` | BaseSystem constructed without foundation modules (test path leaked into prod, or a subclass forgot to call `super().__init__`). | Wire via [`ScoutSystem.from_registry(registry)`](../../../systems/scout/skill.py). Never construct directly in prod code. |
| `RuntimeError: Missing required environment variable: VOYAGE_API_KEY` | `.env` not loaded or var missing. | Set `VOYAGE_API_KEY` in `.env`; confirm `os.environ.get('VOYAGE_API_KEY')` returns a value before calling `get_registry()`. |
| `decision_log_decision_type_check violation` on insert | `decision_type` not in the CHECK allow-list. | Add it to the CHECK in [scripts/sql/005_foundation_completion.sql](../../../scripts/sql/005_foundation_completion.sql), write a new migration, run it. Do NOT edit past migrations in place. |
| `ivfflat: dimension mismatch (1536 vs 1024)` | Embedder swapped models without updating the pgvector columns. | Keep model on `voyage-3` (1024-dim). If swapping models, write a migration that recreates the vector columns + indexes at the new dim. |
| `pattern_matcher.find_similar` returns `[]` even when data exists | `embedding` column NULL (embedder failed silently during a write). | Backfill: re-embed rows where `embedding IS NULL`. Check `DecisionLogger` logs for embed failures. |
| `load_foundation` returns all zero counts | Client has no `business_context` / `client_facts` yet. | Run [scripts/load_context.py](../../../scripts/load_context.py) for the client before dispatching stages. |

## Escalation

- Three consecutive foundation-loop failures for the same `client_id` + `decision_type`: escalate to human per CLAUDE.md's three-failure rule. Do NOT retry a fourth time.
- Schema drift (a CHECK constraint violation no migration explains): stop, do not patch the DB by hand. Produce a migration.
- Embedder cost spike (see `total_cost_cents` on the embedder instance): investigate before raising `cost_cap_cents_per_call`.

## Automation notes

- **Fully automated:** registry construction, foundation-loop dispatch, decision logging, autonomy check, similarity search.
- **Operator-driven:** client onboarding (context loading, autonomy-rule seeding) runs once per client via scripts; the foundation does not seed itself.
- **Not automated:** adding a new `decision_type` (migration required); promoting autonomy level (explicit human approval per CLAUDE.md).

## Change log

- v1.0, 2026-04-23, initial (Task 18).
