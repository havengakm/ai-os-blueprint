# Optimizer

The Optimizer reviews how the AIOS performed last week and surfaces read-only recommendations the operator approves before any change applies.

## Identity

- **Type**: scheduled agent (cron, e.g. Monday 6am operator-local).
- **Posture**: read-only. v1 produces recommendations and a markdown report; v2 (Plan 4 / autoresearch) auto-applies approved ones.
- **Cost discipline**: zero LLM calls in v1. All analyses are deterministic SQL aggregations against `decision_log` + `outreach_send_log` + `outreach_reply` + `escalations` + `optimizer_recommendation` + `contacts`.

## Capabilities

`systems/optimizer/weekly_review.py::WeeklyReview.run(client_id, days=7)` produces a `WeeklyReviewReport` with five sections:

1. **Cost analysis** — reuses `scripts/cost_dashboard.fetch_cost_report`. Cost-per-active-contact vs $0.002 target, per-tier + per-adapter breakdown, top-N expensive contacts.
2. **Reply rate** — replies / sends in window.
3. **Pending recommendations** — count of `optimizer_recommendation` rows with `status='pending'`.
4. **Open escalations** — count of `escalations` rows with `status='open'`.
5. **Cool-off queue** — contacts in `status='cooling_off'`; subset whose `cool_off_until` has elapsed (ready to re-enter).

## How to invoke

```bash
uv run python scripts/run_optimizer_weekly.py --client-id=<client_id> [--days=7]
```

Outputs:
- Markdown report committed to `data/captures/optimizer/<YYYY-MM-DD>-<client_id>.md`.
- Slack notification with the summary + link to the markdown (if `SLACK_WEBHOOK_URL` is set; silent no-op otherwise).
- Stdout summary for the cron-job log tail.

## Where recommendations come from

For v1 the weekly review reports counts only — recommendations are seeded by other paths (Phase 5 Task 2.5.3 applicators when bandit data accumulates; manual `RecommendationEngine.create()` calls today). The weekly job's job is to make the queue visible, not generate from scratch.

When v2 lands (Plan 4 autoresearch), the Optimizer will:
- Compute calibration drift on the cold-email copy grader (`outreach_drafts.predicted_grade` vs actual `outreach_reply` outcomes).
- Compare bandit variant win-rates and emit `bandit_weight_adjustment` recommendations.
- Compute adapter ROI (Trigify-sourced reply rate vs Apollo-only) and emit `adapter_score_weight` recommendations.

## What this agent does NOT do

- Does NOT auto-apply any recommendation. Operator approves via the inbox API per CLAUDE.md guardrails.
- Does NOT make per-contact decisions. The runtime is per-client / per-week.
- Does NOT call any LLM in v1. Full deterministic SQL.

## Source files

- `systems/optimizer/__init__.py`
- `systems/optimizer/recommendations.py` — RecommendationEngine + RecommendationRow
- `systems/optimizer/storage/recommendation_supabase_store.py` — real backend
- `systems/optimizer/weekly_review.py` — the analyses + markdown renderer
- `scripts/run_optimizer_weekly.py` — CLI entrypoint
- `api/routers/optimizer.py` — operator approve / reject / list endpoints

## Plan trail

Plan 2 Phase 5 Task 2.5.1 (this agent) + Task 2.5.2 (recommendation persistence + API). Plan 4 will extend this with autoresearch loops + auto-apply for high-confidence categories.
