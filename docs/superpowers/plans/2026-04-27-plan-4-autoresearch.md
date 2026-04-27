# Plan 4: Autoresearch — autonomous experimentation framework (Karpathy / Saraev pattern)

## Context

Plan 4 implements the autonomous-experimentation pattern Karpathy released in [karpathy/autoresearch](https://github.com/karpathy/autoresearch) for LLM training, adapted to cold-email optimisation following Nick Saraev's email-optimizer pattern (24-min YouTube walkthrough captured in `memory/sessions/2026-04-27.md`).

The core idea:
- An orchestrator runs experiments autonomously in a tight loop.
- A single objective metric is the only feedback signal — no human judges quality.
- The agent **modifies** a baseline file, **deploys** the modification alongside the current baseline as a head-to-head A/B test, **measures** the metric on both, and **promotes** the winner OR **reverts** to baseline.
- Operator wakes up to a log of experiments + (hopefully) better outputs.

For LLM training (Karpathy): metric = `val_bpb`, mutate = `train.py`, time budget = 5min/experiment, ~100 experiments overnight.

For cold email (Saraev): metric = positive reply rate, mutate = email copy, cycle = 4hr cron with 48hr measurement window, ~12 experiments concurrent in steady state, ~6 deployed/day.

For AIOS (this plan): same pattern across **multiple optimisation surfaces** — subject lines, icebreakers, body templates, offer frames, list filters. Each surface gets its own orchestrator with its own `baseline.md / resource.md / results.log` trio.

## Hard dependencies on Plan 2

Plan 4 **cannot run** without:
- **Plan 2 Phase 2 (Beacon send)** — to actually deploy experiments via Smartlead/Instantly/PlusVibe.
- **Plan 2 Phase 3 (reply ingest)** — to harvest positive_reply_rate as the metric.
- **Plan 2 Phase 5 (Optimizer v1)** — recommends bandit-weight adjustments on EXISTING variants. Plan 4 takes the next step: autonomously generates NEW variant content and auto-promotes winners. Plan 4 reuses the Optimizer's weekly-review infrastructure.

Plan 4 implementation **starts** when Plan 2 Phase 3 is shipped + has 30+ days of reply data on at least 2-3 active variants. Plan 4 plan **doc** lands now (this file) so the architecture is captured + the team is aligned.

## Scope

### In scope

- **Per-surface orchestrators** — one each for subject_line, icebreaker, body_template, offer_frame, and list_filter (`client_config.icp` rules). Each operates independently.
- **3-file pattern per surface** — `baseline.md` (current best, agent-mutated), `resource.md` (best practices, operator-curated), `results.log` (append-only experiment history).
- **Loop**: HARVEST → GENERATE → DEPLOY → MEASURE → PROMOTE/REVERT → loop.
- **Cron-driven** via GitHub Actions (or Trigger.dev if Plan 2 wired it). 4-hour default cycle; 48-hour measurement window.
- **Volume-bounded** — concurrent-experiment cap per surface, max-leads-per-experiment cap per cycle. Caps are per-client config.
- **Slack notifications** on harvest events (winner promoted / loser reverted / experiment deployed).
- **Operator-interactive GENERATE step (v1)** — challenger generation runs as a Claude Code skill (Sonnet via Max credits). Operator triggers; orchestrator presents the challenger; orchestrator deploys it. v2 promotes GENERATE to daemon-autonomous (Anthropic API) once calibration is proven over 30+ days.
- **Atomic PROMOTE/REVERT** — winner becomes the new `baseline.md`; previous baseline archived to `results.log`. Database state for the affected variant flips atomically.

### Out of scope (deferred)

- **Cross-surface optimization** — orchestrator decides which surface to mutate next based on diminishing returns. v3 territory.
- **Multi-objective optimization** — combining reply rate + meeting-booked rate + revenue. v2.
- **Custom resource.md per niche** — start with a single resource.md per surface, expand if niches diverge.
- **Auto-applying recommendations from Plan 2 Phase 5 Optimizer** — Plan 4 doesn't auto-apply Optimizer recs (that's a separate path); it generates fresh content. Phase 5 stays operator-approved.
- **Beyond cold email** — no LinkedIn / SMS / WhatsApp surfaces in v1. Those plug in once Plan 3 ships.

## Architecture

### Per-surface orchestrator file layout

```
systems/autoresearch/
  __init__.py
  orchestrator.py              ← shared loop logic
  generate.py                  ← challenger-generation sub-agent invocation
  harvest.py                   ← queries outreach_reply for past experiments
  deploy.py                    ← creates Beacon campaign with baseline + challenger arms
  measure.py                   ← computes per-arm reply rates
  promote.py                   ← atomic flip of baseline.md + variant DB row
  storage.py                   ← persists experiments table

  orchestrators/
    subject_line/
      baseline.md
      resource.md
      results.log
    icebreaker/
      baseline.md
      resource.md
      results.log
    body_template/
      baseline.md
      resource.md
      results.log
    offer_frame/
      baseline.md
      resource.md
      results.log
    list_filter/
      baseline.md
      resource.md
      results.log

scripts/
  run_autoresearch_cycle.py    ← CLI entry, target of cron
  promote_baseline.py          ← operator manual-override: promote a specific challenger

skills/operations/
  generate-challenger.md       ← operator-interactive challenger generation (v1)
  review-experiment.md         ← operator pre-deploy review of a challenger

.github/workflows/
  autoresearch.yml             ← 4hr cron triggers run_autoresearch_cycle.py
```

### Loop steps

For each surface, every cycle:

1. **HARVEST** — query `outreach_reply` for experiments deployed `harvest_after_hours` (default 48) ago for this surface. For each completed experiment, compute reply rate per arm (baseline vs challenger). Update the `experiments` table row with the verdict.

2. **GENERATE** (v1 operator-interactive) — operator runs `skill: generate-challenger.md` via Claude Code. Skill reads `baseline.md` + `resource.md` + last 5 entries from `results.log`, returns a proposed challenger variant. Operator approves; orchestrator persists challenger as a new `component_variants` row (status = `experimental`).

3. **DEPLOY** — orchestrator launches a Beacon experiment campaign:
   - Splits the next `experiment_volume` leads (default 250) 50/50 across arms (baseline / challenger).
   - Each arm uses the same niche + offer + send-account pool but the surface variant under test diverges.
   - Inserts `experiments` row tracking arm composition + start_at + expected_harvest_at.

4. **MEASURE** — passive. Replies arrive via the Plan 2 Phase 3 webhook ingest. `outreach_reply` rows accumulate per-arm.

5. **PROMOTE / REVERT** — at HARVEST time (next cycle, ~48hrs after deploy):
   - If challenger reply rate > baseline + significance threshold (default: +0.5pp absolute or 30% relative, whichever is larger): challenger wins. Atomically: write new `baseline.md` = challenger content; flip `component_variants.status` for old baseline → `retired_by_autoresearch`; for challenger → `approved`. Append winner row to `results.log`.
   - Else: challenger loses. Flip challenger `component_variants.status` → `rejected_by_autoresearch`. Append loser row to `results.log`. baseline.md unchanged.
   - Slack notification sent either way.

### Schema additions

```sql
-- 020_autoresearch_experiments.sql (Plan 4 Phase 1 migration)

CREATE TABLE experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id text REFERENCES clients(id),
    surface text NOT NULL,           -- 'subject_line' | 'icebreaker' | etc.
    baseline_variant_id UUID REFERENCES component_variants(id),
    challenger_variant_id UUID REFERENCES component_variants(id),
    deployed_at timestamptz NOT NULL DEFAULT now(),
    expected_harvest_at timestamptz NOT NULL,
    harvested_at timestamptz,
    baseline_arm_size int,
    challenger_arm_size int,
    baseline_reply_rate numeric,
    challenger_reply_rate numeric,
    verdict text,                    -- 'pending' | 'challenger_wins' | 'baseline_wins' | 'no_signal'
    significance_threshold numeric DEFAULT 0.005,
    notes text
);

CREATE INDEX idx_experiments_pending ON experiments (client_id, surface, expected_harvest_at)
    WHERE verdict = 'pending';
CREATE INDEX idx_experiments_recent ON experiments (client_id, surface, deployed_at DESC);
```

Plus extend `component_variants.status` CHECK to include `experimental`, `retired_by_autoresearch`, `rejected_by_autoresearch`.

## Phases

### Phase 0: Pre-Plan-4 alignment

- [ ] Plan 2 Phase 2 (Beacon send) shipped + tagged.
- [ ] Plan 2 Phase 3 (reply ingest + classification) shipped + tagged.
- [ ] At least 30 days of `outreach_reply` data accumulated.
- [ ] Plan 2 Phase 5 (Optimizer v1) shipped — operator has used recommendations and trusts the calibration.

### Phase 1: Schema + persistence

**Tasks:**
- Migration `scripts/sql/020_autoresearch_experiments.sql`.
- Extend `component_variants.status` CHECK constraint.
- New module `systems/autoresearch/storage.py` — CRUD on `experiments` table.

**Acceptance:**
- Migration runs clean.
- `storage.persist_experiment(...)` callable from Python with tests against an in-memory backend.

### Phase 2: HARVEST step

**Files:** `systems/autoresearch/harvest.py`, `tests/test_autoresearch/test_harvest.py`.

**Tasks:**
- Query `outreach_reply` joined with `outreach_send_log` and `experiments` for pending experiments past their `expected_harvest_at`.
- Compute per-arm reply rate.
- Update `experiments.verdict` based on significance threshold.

**Acceptance:**
- Fixture experiments with mocked reply data produce correct verdicts (challenger wins / baseline wins / no_signal).
- Edge cases: arm with zero replies, tie, both arms zero replies.
- 6+ tests.

### Phase 3: GENERATE step (operator-interactive)

**Files:** `skills/operations/generate-challenger.md` (new skill), `systems/autoresearch/orchestrators/<surface>/{baseline,resource,results}.{md,log}` (initial templates per surface).

**Tasks:**
- Skill: reads `baseline.md` + `resource.md` + last 5 results, returns a proposed challenger as a markdown response. Operator reviews + approves via the skill's interaction.
- On approval: orchestrator writes challenger to a new `component_variants` row (status = `experimental`).
- Operator-interactive — runs in Claude Code with Sonnet via Max credits per `feedback_max_credits_vs_api_boundary`.

**Acceptance:**
- Skill runs against a sample baseline.md, returns a coherent challenger.
- Persisted variant has correct schema + status.
- 4+ tests using a fixture sub-agent (no real Anthropic calls in tests).

### Phase 4: DEPLOY step

**Files:** `systems/autoresearch/deploy.py`, `tests/test_autoresearch/test_deploy.py`.

**Tasks:**
- Allocate next N leads (split 50/50) across baseline + challenger arms.
- Launch Beacon experiment campaign (uses Plan 2 Phase 2 infrastructure).
- Insert `experiments` row.
- Atomicity: if Beacon launch fails, no `experiments` row written.

**Acceptance:**
- 50/50 split on a 250-lead test pool (125 each, ±0).
- Beacon receives the right campaign config for both arms.
- Failure path: `experiments` row absent on Beacon error.
- 5+ tests.

### Phase 5: PROMOTE / REVERT step

**Files:** `systems/autoresearch/promote.py`, `tests/test_autoresearch/test_promote.py`.

**Tasks:**
- Atomic `baseline.md` rewrite via filesystem-level rename (no torn writes).
- DB-side: flip old baseline `component_variants.status` to `retired_by_autoresearch`; flip challenger to `approved`.
- Append winner/loser row to `results.log`.
- On REVERT: only DB status flip on challenger; baseline.md unchanged.

**Acceptance:**
- PROMOTE results in `baseline.md` matching the challenger's content + correct DB state.
- REVERT results in baseline.md unchanged + challenger marked rejected.
- Crash-resilience: incomplete write doesn't corrupt baseline.md (use temp+rename pattern).
- 6+ tests including the crash-resilience case.

### Phase 6: Cron + Slack notifications

**Files:** `scripts/run_autoresearch_cycle.py`, `.github/workflows/autoresearch.yml`, `systems/autoresearch/notifications.py`.

**Tasks:**
- CLI: takes `--surface` + `--client-id`. Runs the loop once for that surface/client.
- GitHub Actions cron: `0 */4 * * *` (every 4hrs). Iterates surfaces + active clients.
- Slack notifications: experiment-deployed, experiment-harvested-winner, experiment-harvested-loser. Reuses Plan 2 Phase 3 escalation Slack channel by default; can override.

**Acceptance:**
- Manual `uv run python scripts/run_autoresearch_cycle.py --surface=subject_line --client-id=kirsten-client-zero` executes cleanly.
- Cron run on test schedule (`*/5 * * * *`) for one cycle confirms end-to-end loop.
- Slack receives the expected messages.

### Phase 7: Multi-surface expansion

**Tasks:**
- Apply Phases 1-6 patterns to remaining 4 surfaces (icebreaker, body_template, offer_frame, list_filter).
- Per-surface `baseline.md` seeded from current top-performing variant per the `decision_log`.
- Per-surface `resource.md` curated by operator (drawing on existing `data/knowledge/experts/` content).

**Acceptance:**
- All 5 surfaces run an end-to-end cycle on the test client.
- No cross-surface coupling — surfaces run independently.

### Phase 8: Acceptance + merge + tag `plan-4`

- End-to-end on `kirsten-client-zero` against creative_branding niche: 2 surfaces deployed, 1 cycle each, 1 winner promoted, results.log updated.
- Cost benchmark: per-cycle cost (HARVEST + GENERATE + DEPLOY + PROMOTE) ≤ \$0.05 in steady state.
- PR + review + merge `--no-ff` to main + tag `plan-4`.

## Branch strategy

Branch off `main` (after Plan 2 + Plan 3 merged) as `feat/plan-4-autoresearch`. Phases 1-8 ship as 7-8 PRs (one per phase). Final merge with `--no-ff` + `plan-4` tag.

## Critical files to create/modify

| Phase | Files |
|---|---|
| 0 | depends on Plan 2 phases |
| 1 | `scripts/sql/020_autoresearch_experiments.sql` (new), `systems/autoresearch/storage.py` (new) |
| 2 | `systems/autoresearch/harvest.py` (new) |
| 3 | `skills/operations/generate-challenger.md` (new), per-surface `baseline.md` + `resource.md` + `results.log` templates |
| 4 | `systems/autoresearch/deploy.py` (new) — depends on Plan 2 Phase 2 Beacon adapter |
| 5 | `systems/autoresearch/promote.py` (new) |
| 6 | `scripts/run_autoresearch_cycle.py` (new), `.github/workflows/autoresearch.yml` (new) |
| 7 | per-surface orchestrator dirs populated |
| 8 | `data/captures/plan4-acceptance/` (gitignored) + `memory/INDEX.md` |

## Reuse from existing code

- **`outreach_reply` + `outreach_send_log`** (Plan 2 Phase 2-3) — HARVEST queries these tables directly.
- **`component_variants` schema** (Plan 1) — challenger variants land as new rows.
- **Beacon send adapter** (Plan 2 Phase 2) — DEPLOY launches campaigns through it.
- **Optimizer weekly review** (Plan 2 Phase 5 Task 2.5.1) — Plan 4 reuses the cron + Slack scaffolding.
- **Decision-log-emitter pattern** (Plan 1) — every Plan 4 cycle emits `decision_log` rows for harvest + deploy + promote events.
- **Skill + sub-agent pattern** (Plan 2 Tasks 2.5.4 + 2.5.6) — `generate-challenger.md` follows the same operator-interactive skill pattern as the copy grader and ICP filter.
- **Workload-tier rule** (`feedback_max_credits_vs_api_boundary`) — GENERATE step starts operator-interactive (Max credits), promotes to daemon (API) only after calibration proves out.

## Verification

End-to-end after all phases:

1. **Schema clean**: `experiments` table exists with all columns + indexes.
2. **HARVEST works**: a fixture experiment past its harvest time produces a correct verdict.
3. **GENERATE works**: skill runs in Claude Code, returns coherent challenger, persists variant.
4. **DEPLOY works**: 50/50 split campaign launches via Beacon.
5. **PROMOTE works**: winning challenger rewrites `baseline.md` atomically + flips DB status.
6. **Cron runs**: GitHub Actions triggers cycle every 4hrs without operator involvement.
7. **Slack delivers**: winner + loser + deploy notifications arrive.
8. **Cost guardrails**: per-cycle cost ≤ \$0.05; per-experiment volume bounded by client cap.
9. **Atomic on failure**: simulated Beacon failure leaves no orphaned `experiments` row.
10. **Multi-surface**: 5 surfaces run independently without cross-contamination.

## What this plan explicitly does NOT do

- Does NOT auto-generate challenger content in v1 — operator-interactive skill, operator approves.
- Does NOT replace Plan 2 Phase 5 Optimizer — Plan 4 generates new content; Plan 5 adjusts priors on existing variants. Both ship.
- Does NOT optimise across LinkedIn / SMS / WhatsApp — those channels ship in Plan 3 first.
- Does NOT cross-surface (e.g. "the orchestrator decides whether to optimise subject lines or icebreakers next based on diminishing returns") — v3 territory.
- Does NOT support multi-objective optimisation (reply rate + meeting-booked + revenue) — v2 territory.
- Does NOT change the autonomy progression — Plan 4 surfaces ship at `suggest` autonomy until proven out per CLAUDE.md guardrails.

## Order of execution

Plan 4 starts ONLY after Plan 2 Phase 5 ships AND 30 days of reply data exist.

1. Phase 1 (schema) — 1 day, single PR.
2. Phase 2 (HARVEST) — 2-3 days, single PR.
3. Phase 3 (GENERATE — operator-interactive) — 2-3 days, single PR.
4. Phase 4 (DEPLOY) — 2-3 days, single PR. Depends on Phase 3 completing.
5. Phase 5 (PROMOTE / REVERT) — 2 days, single PR.
6. Phase 6 (cron + Slack) — 1-2 days, single PR.
7. Phase 7 (multi-surface expansion) — 4-5 days. Per-surface PR or one bundled PR.
8. Phase 8 (acceptance + tag) — 1 day.

Estimated calendar: **2-3 weeks** of execution time once dependencies are met.

## Key tuning knobs

| Knob | Default | Notes |
|---|---|---|
| Cycle frequency | 4hrs | Karpathy 5min, Saraev 4hr. AIOS slower because email metric needs 48hr window. |
| Measurement window | 48hr | Per Saraev — replies usually arrive within 24-48hrs of send. |
| Significance threshold | +0.5pp absolute OR +30% relative | Whichever is larger. Conservative — favours baseline when noise is high. |
| Concurrent experiments per surface | 2 | Saraev runs ~12 across surfaces; AIOS starts low. |
| Experiment volume | 250 leads | 125/arm. Saraev's number. Volume-bound by Smartlead daily caps. |
| Cron | `0 */4 * * *` | UTC. Adjust per operator's preference. |
| Generate model | Sonnet 4.6 (operator-interactive) | Per workload-tier rule. Promote to daemon-Haiku for v2. |
