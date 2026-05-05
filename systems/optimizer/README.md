# Optimizer

**Plain-name label (operator-facing):** Operations Director (weekly recap + daily dispatch).

**Climbing-name (code path):** `systems/optimizer/`. Per the agent-naming decision (2026-05-04), code paths keep climbing names; plain names are display-only. See `docs/architecture/agent-deployment-lifecycle.md`.

## What Optimizer does

Weekly review of every other agent's performance + recommendations to operator. Read-only against the hub for reasoning; writes to `optimizer_recommendation` for operator-approval.

Specifically:

- Reads `decision_log` + `outreach_send_log` + `outreach_reply` + `agent_kpis` + `business_objectives` over rolling 7-day window
- Identifies campaigns to scale (>3% reply rate), kill (<1%), rewrite (1-3%)
- Surfaces variant-level performance via the bandit + grader feedback loop
- Generates `optimizer_recommendation` rows; operator approves/rejects via `/api/optimizer/recommendations`
- Once approved, recommendations apply to client_config / sequence variants / autonomy promotions

## Layout

```
systems/optimizer/
├── recommendations.py     : RecommendationEngine (logic for surfacing recs)
├── weekly_review.py       : the weekly run flow
├── storage/               : SupabaseRecommendationStore
└── __init__.py
```

## How Optimizer talks to the hub

Per the connected-system pattern:

- **Reads from Supabase**: `decision_log`, `outreach_send_log`, `outreach_reply`, `agent_kpis`, `business_objectives`, `outreach_drafts.predicted_grade` (grader-feedback calibration), `client_config`
- **Writes to Supabase**: `optimizer_recommendation` (one row per recommendation), `decision_log` (every recommendation logged with reasoning + KPI tag), `agent_kpis` (its own metric: recommendations approved / rejected ratio)
- **API connections**: Anthropic API (Sonnet for reasoning over performance data)
- **Subscribes to** (via `employee_subscriptions`): every agent's `learning_events` (Optimizer is the team-wide listener)
- **Subscribed by**: Auditor (audits Optimizer's own decision quality)

## CLI entry points (in `scripts/`)

- `scripts/run_optimizer_weekly.py`: Monday cron, runs the weekly review
- `scripts/run_expire_stale_recommendations.py`: daily cron, expires recommendations not actioned within window

## Tests

- `tests/test_optimizer/`: unit + integration tests for RecommendationEngine + weekly review + storage backend

## Owning skills (per `agent_skills` Supabase rows, Phase 2)

When the schema lands, Optimizer's row-set will activate skills under:
- `skills/operations/grade-cold-email-copy.md` (variant grading)
- `skills/operations/filter-icp-list.md` (ICP recommendation)
- `skills/operations/audit-aios-health.md` (cross-agent KPI rollup)
- `skills/data-analytics/` (when populated; performance attribution)

Universal library, per-agent activation. Skills don't live in this folder.

## Companion daemon job

`grader_calibration.py` (Plan 2 Phase 5 Task 2.5.5, deferred until 30 days of `predicted_grade` pairs) compares predicted vs actual reply rates and surfaces calibration drift in the weekly Optimizer report.

## Migrations that brought Optimizer online

- `020`: cost rollup view + `get_contact_cost` RPC
- `021`: enrichment coverage rollup view
- `022`: `optimizer_recommendation` table
- `023`: `outreach_drafts.predicted_grade` column

## Cloud-execution model

Optimizer's weekly review is the canonical Routines fit:

- **Weekly cadence** → Claude Routines (perfect)
- **Stateless run** → Routines (every run is fresh; output committed to a `reports/` folder via the routine)
- **Sonnet reasoning** → consumes Max plan or API per workload-tier rule

`clymb-optimizer` private routine repo will be created alongside `clymb-audit` once Phase 4 proves the pattern. Same shape: tiny CLAUDE.md, entrypoint that loads context from Supabase, commits report.
