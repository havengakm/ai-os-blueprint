# Scout

**Plain-name label (operator-facing):** Prospect Researcher (find leads + enrich + score + screen).

**Climbing-name (code path):** `systems/scout/`. Per the agent-naming decision (2026-05-04), code paths keep climbing names; plain names are display-only. See `docs/architecture/agent-deployment-lifecycle.md`.

## What Scout does

Finds qualified prospects matching the deployment's ICP, enriches them with structural + signal data, scores fit, screens out misfits, and renders ready-to-send drafts. Does NOT send: that's Beacon's job. Multi-channel by design: Scout's pipeline is shared across email / LinkedIn / SMS / etc. via channel sub-modules under `outreach/` (per `feedback_lead_multi_channel_module`).

## Pipeline stages

```
pull → score → screen → identity → enrich → render → handoff_to_beacon
```

| Stage | Purpose |
|---|---|
| `pull` | Discover candidate contacts from sources (Trigify monitors, Apollo, Lusha, vertical scrapers) |
| `score` | ICP scoring 0-100 with optional UncertainZoneJudge (Haiku) for 40-60 band |
| `screen` | Secondary ICP screen (homepage + Haiku) on remaining candidates |
| `identity` | Resolve owner / decision-maker per contact |
| `enrich` | Apollo + Lusha + ZeroBounce + Claude research adapters + signal-gated Deep Research |
| `render` | Compose drafts via composer + IcebreakerAdapter; outputs to `outreach_drafts` |

Drafts then get picked up by Beacon's send pipeline.

## Layout

```
systems/scout/
├── pipeline/             : the seven stages above (PullStage, ScoreStage, etc.)
├── sources/              : per-source adapters (Trigify, Apollo, vertical scrapers like Clutch)
├── enrich/               : per-vendor enrichment adapters (Apollo, Lusha, ZeroBounce, Claude research)
├── identity/             : owner resolution
├── score/                : ICP scoring + UncertainZoneJudge
├── outreach/             : composer + IcebreakerAdapter (renders drafts)
├── budget/               : per-contact cost ceiling enforcement (PerContactCeiling)
├── supabase_backends/    : per-table Supabase write adapters
├── sql/                  : Scout-specific migration helpers (most schema lives in scripts/sql/)
├── skill.py              : ScoutSystem(BaseSystem) entry point
└── __init__.py
```

## How Scout talks to the hub

Per the connected-system pattern (see lifecycle doc):

- **Reads from Supabase**: `agent_system_prompts`, `agent_skills`, `agent_frameworks` (Saraev + Allbound), `agent_guardrails`, `client_config` (ICP + tier thresholds + budgets), `knowledge_base` (expert frameworks), `business_context` + `client_facts` (per-client narrative)
- **Writes to Supabase**: `contacts` (one row per discovered contact), `outreach_drafts` (rendered drafts ready for Beacon), `decision_log` (every score / screen / enrich / render decision with reasoning + KPI tag), `learning_events` (lead source quality patterns, cost-per-good-contact deltas)
- **API connections** (resolved via `api_registry`): Trigify (signal source), Apollo (enrichment), Lusha (phone enrichment), ZeroBounce (email validation), Anthropic API (Haiku for batch scoring + screening, Sonnet for deep research)
- **Subscribes to** (via `employee_subscriptions`): Optimizer's recommendations (ICP weight tuning, vendor swap signals)
- **Subscribed by**: Beacon (lead-source quality patterns), Optimizer (whole-pipeline performance), Auditor (cross-agent integrity)

## CLI entry points (in `scripts/`)

- `scripts/run_daemon_once.py`: single daemon tick, runs all Scout stages once
- `scripts/run_trigify_discovery.py`: manual Trigify pull (otherwise the daemon handles it)
- `scripts/configure_trigify_monitors.py`: operator setup tool, configures monitors per client
- `scripts/ingest_clutch_corpus.py`: bulk Clutch directory ingest
- `scripts/ingest_preresolved_contacts.py`: manual CSV ingest

## Tests

- `tests/test_scout/`: pipeline stage unit tests + integration tests for each enrichment adapter

## Owning skills (per `agent_skills` Supabase rows, Phase 2)

When the schema lands, Scout's row-set will activate skills under:
- `skills/outbound/` (lead sourcing, ICP definition, signal detection)
- `skills/operations/filter-icp-list.md` (operator-interactive ICP filtering)
- `skills/copywriting/` (icebreaker generation, body templates, shared with Beacon)
- `skills/meta/validate-writing.md` (fail-closed on every rendered draft)

Universal library, per-agent activation. Skills do not live in this folder.

## Migrations that brought Scout online

- `001`-`007`: foundation tables + Scout core (contacts, ICP, drafts)
- `008`-`013`: ICP scoring + tier thresholds + budgets + signals + escalations
- `014`: identity resolution (owner extraction)
- `024`: agent topology metadata
- (Phase 2 plan) `025`: agent_context_backbone

## Cloud-execution model

Scout's pipeline runs daily (pull) and continuously (score/enrich for new contacts). Per the decision matrix:

- **Daily Trigify pull** → Routines or Trigger.dev (either fits)
- **Per-contact score / enrich / render** → Trigger.dev (sub-hour cadence, per-contact state)
- **Weekly Scout performance review** → Routine (weekly cadence)

When Phase 4+ ships, Scout deployment will be a mix of one Trigger.dev project + one weekly Routine.

`clymb-discover` private routine repo (for the daily pull) will follow the `clymb-audit` template once that pattern is proven.
