---
name: audit-aios-health
description: Score the AIOS deployment 0-100 across Context / Connections / Capabilities / Cadence (the Four Cs), assign a stage label (Foundation / Built / Compounding / Autonomous), and rank the top 3 gaps by leverage. Operator-interactive. Runs via Claude Code sub-agent on Max-plan credits, no Anthropic API spend. Adapted from nateherkai/AIS-OS audit pattern.
tier: capability
category: operations
tags: [health-check, weekly-review, max-credits, audit, kpi]
input: client_id (string, optional. Defaults to the deployment's primary client). Optional flag include_evidence (bool, default false). If true, attaches per-criterion evidence pointers (file path, query, log location) used to score.
output: {scored_at: ISO-8601 string, total_score: int 0-100, stage: "Foundation"|"Built"|"Compounding"|"Autonomous", scores: {context: int, connections: int, capabilities: int, cadence: int}, top_gaps: [{c: string, criterion: string, points_lost: int, leverage: "high"|"medium"|"low", action: string}, ...], evidence?: dict}
requires_skills: []
requires_tools: [Read, Bash, Glob, Grep, Agent]
references:
  - memory/MEMORY.md
  - CLAUDE.md
  - data/reference/sops/
when-to-use: Weekly operator review (Friday). Before promoting any system to a new autonomy level. After a major plan slice ships. Before onboarding a new client (audit the foundation, not the client deployment).
---

# audit-aios-health

Weekly objective health score for the AIOS. Adapted from Nate Herk AI's `/audit` pattern: Four Cs (Context, Connections, Capabilities, Cadence), 25 points each, total out of 100, stage label, top-3 gaps ranked by leverage.

Operator runs this Friday alongside the existing Optimizer weekly report. The Optimizer measures business outcomes (reply rates, costs, bandit performance). This skill measures system completeness: is the AIOS itself wired up?

## Purpose

`/prime` is narrative: "what could be better?" That works for direction but not for tracking. This skill produces a single number you can plot over time and a punch-list of what to fix next.

The score is not the goal. The trend is. A deployment that goes from 42 (Built) to 67 (Compounding) over six weeks is healthy. A deployment stuck at 58 for three months has stalled.

## The Four Cs (25 points each, 100 total)

### Context (25 pts): what the AIOS knows

| Criterion | Points | What "yes" looks like |
|---|---|---|
| Operator profile + voice loaded | 5 | `data/knowledge/personal/{client_id}/voice.md` + `bio.md` exist and are non-empty |
| Company facts loaded | 5 | `data/knowledge/company/{client_id}/` has services, pricing, case studies, testimonials |
| ICP defined | 5 | `client_config.icp` populated: titles (>=4 each), geographies (full names), industries, employee_min/max, positive + negative examples |
| Brand voice + writing rules enforced | 5 | `rules/global-writing-guardrails.md` exists; `validate-writing` skill runs fail-closed on every outbound |
| Memory + decision log current | 5 | `memory/INDEX.md` updated within 14d; latest session note within 7d |

### Connections (25 pts): what's wired up

| Criterion | Points | What "yes" looks like |
|---|---|---|
| Signal source live | 3 | Trigify CLI configured, monitor IDs in `client_config.trigify_search_ids` |
| Enrichment stack live | 3 | Apollo + Lusha + ZeroBounce credentials in `.env`, last successful call within 7d |
| Send channel live | 3 | Instantly account configured, `send_account` rows present, last send within 7d |
| State store live | 3 | Supabase connection healthy, migrations applied to latest |
| Reply-handler webhook live | 3 | Webhook endpoint reachable, last inbound reply ingested within 30d (or N/A if no sends yet) |
| Cost dashboard live | 3 | `scripts/cost_dashboard.py` runs clean; tier budgets + spend visible |
| Credentials validated | 4 | All required keys in `.env`, no placeholder values, no expired tokens |
| Schedules + triggers active | 3 | Daemon tick + cron entries running on schedule (check `scripts/run_daemon_once.py` last invocation) |

### Capabilities (25 pts): what the AIOS can do

| Criterion | Points | What "yes" looks like |
|---|---|---|
| Skill library populated | 5 | At least 3 atomic skills per active category; meta + composites + playbooks tiers all have entries |
| Active systems have agent manifests | 5 | Every running `systems/<name>/` has matching `agents/<name>.md` with autonomy levels declared |
| QA validators fail-closed | 5 | `validate-writing`, icebreaker validator, ICP validator all wired to short-circuit before send |
| Cost optimiser running | 5 | `scripts/run_optimizer_weekly.py` last successful run within 7d; per-contact cost tracked |
| Reply classifier calibrated | 5 | Classifier accuracy >=80% over rolling 30d, or `suggest`-level placeholder if not yet calibrated |

### Cadence (25 pts): how reliably it runs

| Criterion | Points | What "yes" looks like |
|---|---|---|
| Daily pull | 4 | Scout pipeline pulled new contacts on >=5 of last 7 days |
| Daily send window | 4 | Beacon respected send window + daily cap on >=5 of last 7 days |
| Weekly Optimizer report | 4 | Report shipped to operator on most recent Monday |
| Weekly operator review | 4 | `/prime` invoked + at least one campaign decision logged on most recent Friday |
| Per-session memory writes | 4 | `memory/sessions/YYYY-MM-DD.md` written for >=80% of sessions in last 14d |
| SOP coverage | 5 | Every active system under `systems/<x>/` has a written SOP at `data/reference/sops/<x>/`. Missing SOP for an active system = 0 points (productisation principle: workflow not documented = not productised). |

## Stage labels

| Score | Stage | Meaning |
|---|---|---|
| 0-25 | Foundation | Setup-in-progress. Most systems not yet wired. |
| 26-50 | Built | Wired but unproven. Running, not yet trusted. |
| 51-75 | Compounding | Trusted on most paths. Promotion-ready candidates exist. |
| 76-100 | Autonomous | Running unattended. Operator reviews, doesn't drive. |

A deployment can be Compounding overall while one C is at Foundation. The gap report names the laggard.

## Steps

1. **Resolve `client_id`.** Default to the primary deployment per `memory/MEMORY.md` (currently `clymb`).

2. **Load context.**
   - Read `memory/MEMORY.md`, `memory/INDEX.md`, latest `memory/sessions/*.md`.
   - Read `CLAUDE.md` for the autonomy + hard-rules baseline.
   - List `skills/`, `systems/`, `agents/`, `data/knowledge/personal/{client_id}/`, `data/knowledge/company/{client_id}/`.

3. **Score each criterion.** For each of the 24 criteria, decide pass / partial / fail. Pass = full points, partial = half (round down), fail = 0. Be strict: "exists but empty" is a fail.

4. **Compute totals.** Sum each C (out of 25). Sum all four (out of 100). Map to stage label.

5. **Rank top 3 gaps by leverage.** Leverage = (points_lost × downstream_blast_radius). A missing ICP definition is high-leverage (blocks every outbound). A missing single skill in `legal/` is low-leverage. The top 3 are what the operator actions next.

6. **Output the JSON.** Print + return. Operator pastes into the weekly review.

## Output schema

```json
{
  "scored_at": "2026-05-04T15:00:00Z",
  "total_score": 67,
  "stage": "Compounding",
  "scores": {
    "context": 22,
    "connections": 18,
    "capabilities": 15,
    "cadence": 12
  },
  "top_gaps": [
    {
      "c": "cadence",
      "criterion": "Daily send window",
      "points_lost": 5,
      "leverage": "high",
      "action": "Beacon hasn't sent on 4 of last 7 days. Check scheduler + send-account daily caps."
    },
    {
      "c": "capabilities",
      "criterion": "Reply classifier calibrated",
      "points_lost": 5,
      "leverage": "high",
      "action": "Classifier has 14 labelled triples; needs 30+ at >=80% accuracy before promotion off `suggest`."
    },
    {
      "c": "connections",
      "criterion": "Reply-handler webhook live",
      "points_lost": 3,
      "leverage": "medium",
      "action": "Webhook reachable but no inbound replies in 32d. Verify Instantly forwarding config."
    }
  ]
}
```

## What this skill does NOT do

- Does NOT measure business outcomes (reply rates, booked meetings, revenue). That's the Optimizer's job.
- Does NOT auto-fix anything. It scores. The operator decides what to action.
- Does NOT call the Anthropic API. Runs via the Claude Code Agent tool on Max-plan credits per `feedback_max_credits_vs_api_boundary`.
- Does NOT replace `/prime`. `/prime` decides what to improve next; this skill measures whether the foundation is ready to support that improvement.

## Calibration

The rubric will drift as the AIOS grows. Review the criteria quarterly:

- Add criteria for new systems as they ship (Plan 3 LinkedIn module, Plan 4 SMS, etc.).
- Retire criteria that are no longer load-bearing (e.g. credentials check once secret-rotation is automated).
- Recalibrate the leverage weighting based on which gaps actually predicted outage in the last quarter.

Quarterly calibration is the operator's job. The skill itself stays static between calibrations.
