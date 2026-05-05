# AIOS Structural Plan — Playbooks, AI Employees, COO

**Date:** 2026-04-29 (updated 2026-04-29 evening — Slice 33 alignment)
**Status:** Draft, awaiting operator approval before any code lands
**Decision log entries to read alongside this:** `feedback_agent_topology_5_agents.md`, `feedback_three_tier_skills.md`, `feedback_atomic_skills_architecture.md`, `feedback_autonomous_agent_goal.md`, `feedback_surround_sound_architecture.md`, `feedback_per_company_aios_silo.md`, `feedback_productised_not_custom.md`

## 1. Context

The AIOS started as a 5-agent topology (climbing-named: Scout, Lead, Belay, Compass, Beacon) with skills, departments, and a foundation layer. As of session 2026-04-29 only Scout and Beacon have substantial code; Lead and Belay were paper; Compass existed only as the conceptual "weekly learning loop" without code. CLAUDE.md describes a structure that is roughly 60% real.

A multi-slice architecture conversation locked the macro model:

- A **Playbook** is a specific mission (Cold Email Outreach, Facebook Ads, LinkedIn Outreach, etc.).
- An **AI Employee** is a job-level specialist that owns and runs one or more Playbooks.
- A **COO** (head-manager AI) coordinates all employees via daily dispatches and a weekly recap.
- A **Skill** is a capability — atomic OR job-specific. Skills aren't all universal.
- A **Tool** is a concrete instrument a skill uses (a scraper, a Trigify monitor, a Claude API call, an HTML cleaner).
- A **Workflow** is an ordered sequence of skills + tools that produces an outcome (a step in a playbook).
- A **decision feedback loop** runs continuously: every job completion + new context/data triggers a peer-to-peer learning event so employees optimise from each other.
- **Foundation** (context, knowledge, vector memory) is shared by all employees so they collaborate as a team rather than silos.

Build order chosen by operator: **C — greenfield + parallel.** Build the new structure alongside existing code, prove the pattern with one pilot employee, then migrate the rest.

**Per-deployment isolation, universal architecture (Slice 33 lock).** The AIOS architecture is universal; each business gets its own fully isolated AIOS instance — a *deployment* — with its own context, data, integrations, and vector memory. CLYMB Co is deployment 1 (the AIOS we have today is configured for Climb's outbound use). Each client purchase creates a new deployment from a *vertical template*. Customisation lives only in context, data, integrations, and per-vertical config — never in code. Property management is one example of a future client vertical, not the product itself. Matches `feedback_per_company_aios_silo.md` and `feedback_productised_not_custom.md`.

**Plain-language naming (Slice 33 lock).** Climbing names retire. All employees use plain-language role-descriptive names everywhere — code, decision logs, web app, Slack, marketing. CLYMB Co's company-level brand stays climbing-named; individual employees do not.

The intended outcome: every business function (sales, marketing, ads, ops, finance, ...) becomes a job-level AI Employee managing concrete Playbooks, with the COO running a daily/weekly cadence and a continuous learning loop tying it all together — replicable across deployments via vertical templates.

## 2. The Model

```
DEPLOYMENT (one per business — fully isolated context + data + integrations)
│
├── COO / Operations Director  (head manager — daily dispatch + weekly recap + learning-loop dispatcher)
│
└── AI Employees (job-level specialists, plain-language role-descriptive names)
    │
    ├── Prospect Researcher    → list-building employee
    ├── Outreach Manager       → multi-channel outbound employee (email / LinkedIn / SMS)
    ├── Conversation Manager   → reply / nurture / booking employee
    ├── Content Writer         → content / copy employee
    └── (vertical-specific employees added per deployment, e.g. Tenant Relations Manager
         under property-management vertical, Maintenance Coordinator, etc.)

Each employee owns one or more Playbooks (missions):
    └── Playbook (e.g. Cold Email Outreach)
        │
        └── Workflows (ordered sequences of skills + tools)
            │
            ├── Skills (atomic OR job-specific capabilities)
            └── Tools (concrete instruments)

Foundation (universal across deployments — shared library; per-deployment isolated runtime data)
    ├── context/           per-deployment identity (brand, ICP, integrations) — ISOLATED
    ├── data/knowledge/    three-tier (personal / company / experts) — ISOLATED per deployment
    ├── decision_log       audit trail with outcome backfill — ISOLATED via client_id
    ├── employee_memory    per-employee pgvector store — ISOLATED via client_id + employee_id
    ├── daily_dispatches   COO's per-employee task brief — ISOLATED via client_id
    ├── weekly_recaps      COO's team synthesis — ISOLATED via client_id
    └── learning_events    peer-to-peer learning channel — ISOLATED via client_id

Vertical Templates (deployment bootstraps — what each new deployment configures from)
    ├── creative-branding/         CLYMB Co's deployment template
    ├── property-management/       future client cohort template
    └── (add more verticals as clients onboard)
```

## 3. Terminology Lock — current code → new model

| New term      | Plain-language description                                          | Mapping from current code                                |
|---------------|---------------------------------------------------------------------|----------------------------------------------------------|
| Skill         | Atomic OR job-specific capability                                   | Same. `skills/<category>/` keeps its shape.              |
| Workflow      | Ordered sequence of skills + tools                                  | **Rename**: `skills/composites/` → `workflows/`.         |
| Playbook      | Mission specification (workflows + cadence + success criteria)      | **Elevate**: `skills/playbooks/` → top-level `playbooks/`. |
| Tool          | Concrete instrument (scraper, API client, validator)                | **New top-level**: `tools/` extracts from `systems/`.    |
| Employee      | Job-level specialist (plain-language role-descriptive name)         | **New top-level**: `employees/` materialises what `agents/` only documented. Climbing names retire. |
| COO / Operations Director | Head-manager AI                                         | **New top-level**: `coo/` net-new from scratch.          |
| Deployment    | One business's full isolated AIOS instance                          | New first-class concept (per-`client_id` isolation in foundation tables). |
| Vertical Template | Per-client-cohort deployment-bootstrap config                   | **New top-level**: `vertical-templates/`. |
| Department    | (deferred)                                                          | **Deprecate** for now. Employees are job-level; departments dissolve until any single domain has 3+ specialists. |

### Plain-language employee renaming (Slice 33)

| Old climbing name | New role-descriptive name | Plain-language description |
|---|---|---|
| Scout   | **Prospect Researcher**  | Finds and qualifies leads matching the deployment's ICP |
| Lead    | **Outreach Manager**     | Sends and dispatches across channels (email, LinkedIn, SMS) |
| Belay   | **Conversation Manager** | Handles replies, runs nurture sequences, books meetings |
| Beacon  | **Content Writer**       | Drafts posts, emails, ad copy, marketing assets |
| Compass | **Operations Director**  | The COO — daily dispatch + weekly recap + cross-team coordination |

Climbing names appear nowhere in code, decision logs, web app, Slack, or marketing surfaces. They retire. Historical references in this doc are kept only for the migration table above.

## 4. Directory Layout — NEW / KEEP / DEPRECATE

```
ai-os-blueprint/
├── coo/                                         ← NEW. The head-manager AI ("Operations Director").
│   ├── playbooks/
│   │   ├── daily_dispatch.py
│   │   └── weekly_recap.py
│   ├── workflows/                               ← orchestration sequences
│   ├── skills/                                  ← COO-specific (synthesise_team_status, etc.)
│   └── README.md
│
├── employees/                                   ← NEW. Plain-language role-descriptive employees.
│   ├── prospect-researcher/                     ← migrated from systems/scout/
│   │   ├── playbooks/
│   │   │   ├── lead_generation.py
│   │   │   └── icp_refinement.py
│   │   ├── workflows/
│   │   ├── skills/                              ← prospect-researcher-specific skills
│   │   └── README.md
│   ├── outreach-manager/                        ← built net-new in new shape
│   ├── conversation-manager/                    ← built net-new in new shape
│   ├── content-writer/                          ← migrated from systems/beacon/
│   └── README.md
│
├── vertical-templates/                          ← NEW. Per-client-cohort deployment configs.
│   ├── creative-branding/                       ← CLYMB Co's deployment template
│   │   ├── deployment.yaml                      ← employee roster + playbook list + integration manifest
│   │   ├── icp.yaml                             ← industries, titles, employee_min/max, geographies
│   │   ├── knowledge-seed/                      ← boilerplate knowledge files copied into new deployments
│   │   └── README.md
│   ├── property-management/                     ← future vertical, scaffolded in Phase 10
│   └── README.md
│
├── playbooks/                                   ← NEW. Cross-employee Playbook registry / specs.
│   └── (yaml or python definitions; see Section 6)
│
├── workflows/                                   ← NEW (renamed from skills/composites/)
│   └── (chained skill+tool sequences)
│
├── tools/                                       ← NEW. Concrete instruments.
│   ├── scrapers/                                ← clutch, designrush, goodfirms, etc.
│   ├── api_clients/                             ← anthropic, trigify, instantly, supabase
│   ├── validators/                              ← writing_validator, json parser
│   └── README.md
│
├── skills/                                      ← KEEP. Atomic + job-specific capabilities.
│   ├── meta/                                    ← validate_writing, etc.
│   ├── outbound/                                ← cold-email, reply, sequence-building
│   ├── copywriting/                             ← KEEP categories
│   └── ... (other 15 categories)
│
├── aios/foundation/                             ← KEEP + extend
│   ├── decision_logger.py                       ← extend with record_outcome wiring
│   ├── pattern_matcher.py                       ← KEEP (already used)
│   ├── embedder.py                              ← KEEP
│   ├── feedback_loop.py                         ← NEW. Listens to outcomes, dispatches learning.
│   ├── employee_memory.py                       ← NEW. Per-employee pgvector Protocol + impl.
│   ├── registry.py                              ← extend with new services
│   └── ...
│
├── systems/                                     ← KEEP during migration; deprecate per-system.
│   ├── scout/                                   ← migrate code into employees/prospect-researcher/ (Phase 4)
│   ├── beacon/                                  ← migrate into employees/content-writer/ (Phase 5)
│   └── optimizer/                               ← absorb into coo/ (Phase 8)
│
├── agents/                                      ← DEPRECATE (currently doc-only)
│   └── (delete after migration verifies)
│
├── departments/                                 ← DEPRECATE for now (manifest-only, no runtime binding)
│   └── (revisit when any domain has 3+ specialists)
│
├── context/                                     ← KEEP (per-deployment identity, isolated)
├── data/                                        ← KEEP (knowledge + SOPs + outputs, isolated per deployment)
├── rules/                                       ← KEEP (writing guardrails etc., universal)
├── scripts/                                     ← KEEP (admin CLIs, universal)
├── api/                                         ← KEEP (HTTP endpoints, universal)
├── config/                                      ← KEEP
└── memory/                                      ← KEEP (project memory layer)
```

## 5. Foundation Extensions — what's new vs. what's wired up

The exploration showed the foundation primitives mostly exist. Two are net-new, three are extensions of existing code.

### 5.1 NET-NEW: `aios/foundation/feedback_loop.py`

A service that listens for outcome signals (email opened, reply received, booking confirmed, content published, ad metrics returned, ...) and:

1. Calls `decision_logger.record_outcome()` to backfill the matching `decision_log` row (today this method exists but has zero callers).
2. Generates a `learning_event` row with embedding (so other employees can semantically subscribe).
3. Routes the learning event to relevant employees' vector stores via routing rules (e.g. Outreach Manager's "subject line X drove 30% open rate" → Content Writer's content-writing memory).

The service is async — it does not block the writing employee. Invoked from webhooks (`api/webhooks/`), cron (`scripts/run_feedback_drain.py`), and post-job hooks inside employees.

### 5.2 NET-NEW: `aios/foundation/employee_memory.py`

A Protocol + pgvector implementation for per-employee semantic memory. Per-deployment isolation enforced via `client_id`:

```python
class EmployeeMemory(Protocol):
    async def remember(self, client_id: str, employee_id: str, content: str, *, kind: str, metadata: dict) -> str: ...
    async def recall(self, client_id: str, employee_id: str, query: str, *, k: int = 5, kind_filter: set[str] | None = None) -> list[Memory]: ...
    async def subscribe(self, client_id: str, employee_id: str, source_employee_id: str, kind_filter: set[str]) -> None: ...
```

Default implementation uses Supabase pgvector. The Protocol lets us swap in Pinecone or Obsidian later without touching employee code. Schema:

```
employee_memory (
    id uuid pk,
    client_id text,                    -- per-deployment isolation
    employee_id text,                  -- 'prospect-researcher' | 'outreach-manager' | 'conversation-manager' | 'content-writer' | 'operations-director' | (vertical-specific)
    kind text,                         -- 'job_completion' | 'learning' | 'observation' | 'recap'
    content text,
    embedding vector(1024),
    metadata jsonb,
    created_at timestamptz
)

employee_subscriptions (
    client_id text,
    employee_id text,
    source_employee_id text,
    kind_filter text[],
    primary key (client_id, employee_id, source_employee_id)
)
```

### 5.3 EXTEND: `decision_log` outcome backfill

`decision_log.outcome`, `outcome_data`, `outcome_at` columns exist; `record_outcome()` API exists; nothing calls it today. Wire callers:

- Send webhooks (Content Writer's `pipeline/webhook_handler.py`) call `record_outcome` when a `sent` or `bounced` event arrives matching a logged compose/dispatch decision.
- Reply ingestion calls `record_outcome` on the corresponding outreach decision.
- Each Playbook's terminal step calls `record_outcome` with positive/negative/neutral.

### 5.4 EXTEND: embed all decision-log writers

Foundation's `DecisionLogger` embeds; the existing `SupabaseDecisionLogger` (currently under `systems/beacon/`) doesn't. Inject the same embedder so PatternMatcher's similarity search covers the full corpus.

### 5.5 EXTEND: `aios/foundation/registry.py`

Add fields for the new services:

```python
@dataclass
class SystemRegistry:
    decision_logger: DecisionLogger
    pattern_matcher: PatternMatcher
    employee_memory: EmployeeMemory          # NEW
    feedback_loop: FeedbackLoop              # NEW
    coo: COO                                 # NEW (lazy)
    embedder: Embedder
    # ... existing backends ...
```

### 5.6 NEW TABLES: standup channel

Two tables for the bi-cadence standup the operator described, both with `client_id` for per-deployment isolation:

```
daily_dispatches (
    id uuid pk,
    client_id text,                    -- per-deployment isolation
    employee_id text,                  -- recipient employee
    dispatched_at date,                -- one per (client, employee, date)
    tasks jsonb,                       -- ordered list of {playbook, priority, rationale}
    company_alignment text,            -- COO's context paragraph
    consumed_at timestamptz,           -- set when employee reads
    primary key (id),
    unique (client_id, employee_id, dispatched_at)
)

weekly_recaps (
    id uuid pk,
    client_id text,                    -- per-deployment isolation
    week_start date,                   -- one per (client, week_start)
    synthesis text,                    -- COO's narrative recap
    kpis jsonb,                        -- { listing_count, send_count, reply_rate, ... }
    decisions_for_next_week jsonb,
    primary key (id),
    unique (client_id, week_start)
)
```

Migration: SQL DDL added to `scripts/sql/<next>_standup_channel.sql`.

## 6. Playbooks as First-Class Definitions

A Playbook is a YAML or Python spec that names the mission, owner employee, workflows it composes, success criteria, and cadence. Example shape:

```yaml
# playbooks/cold_email_outreach.yaml
name: cold_email_outreach
owner_employee: outreach-manager
mission: |
  Run an end-to-end cold-email outbound mission against an enriched contact list.
  Includes list pull, enrichment, copy compose + QA, send dispatch, reply triage hand-off to conversation-manager.
workflows:
  - workflows/list_pull
  - workflows/enrich_contact
  - workflows/compose_outreach
  - workflows/dispatch_send
  - workflows/handoff_to_conversation_manager  # cross-employee
success_criteria:
  - reply_rate >= 0.05
  - bounce_rate <= 0.02
cadence: continuous   # vs daily | weekly | on-demand
budget_per_contact_cents: 5
```

Python mirror for type-safety:

```python
@dataclass
class PlaybookSpec:
    name: str
    owner_employee: str
    mission: str
    workflows: list[str]
    success_criteria: list[str]
    cadence: Literal["continuous", "daily", "weekly", "on_demand"]
    budget_per_contact_cents: int | None
```

Playbook execution is delegated to the owning employee, but the spec is registered globally so the COO can read it (and so other employees can hand off into it via cross-employee references).

## 7. The Pilot — Build COO First

Per build order C, the first thing built inside the new structure is the COO. Reasoning:

- Net-new — no existing code to displace, no risk of breaking the live outbound pipeline.
- Forces every new abstraction to materialise: Employee scaffold, Playbook spec, Workflow + Skill files, Tool extraction, vector store, feedback loop, standup tables.
- Output (daily dispatches + weekly recap) immediately benefits the existing employees once they're migrated.
- Aligns with the operator's emphasis on coordination + continuous improvement as the load-bearing piece.

COO scaffold:

```
coo/
├── __init__.py
├── coo.py                         ← Employee runtime, .run() entry point
├── playbooks/
│   ├── daily_dispatch.py          ← reads decision_log + employee_memory recent activity per employee, generates per-employee task brief, writes daily_dispatches row
│   └── weekly_recap.py            ← reads dispatches + outcomes from past week, generates synthesis, writes weekly_recaps row, emits learning_events
├── workflows/
│   ├── observe_team.py            ← workflow: read from employee_memory + decision_log
│   └── synthesise_status.py       ← workflow: LLM-summarise + KPI-aggregate
├── skills/
│   ├── synthesise_team_status.py  ← skill: LLM call with structured output
│   └── score_priority.py          ← skill: rank tasks for an employee
└── README.md
```

COO daemon scheduling:

- Daily 6am client-local — `coo.daily_dispatch` runs, writes a row to `daily_dispatches` for each active employee.
- Weekly Sunday 7pm client-local — `coo.weekly_recap` runs, writes one `weekly_recaps` row.

Employees consume dispatches at the start of their next run (read `daily_dispatches WHERE client_id = self.deployment AND employee_id = self AND dispatched_at = today AND consumed_at IS NULL`). Recaps are read on the first run of each week.

**Output shape (Slice 33 lock for Slack + Web App readability):** COO writes `daily_dispatches` and `weekly_recaps` as structured JSON, not free-text only, so the future Slack bot and web-app dashboards can render them as cards / lists / KPI tiles without re-parsing. Schema:

```python
DispatchPayload = {
    "narrative": str,                   # COO's short context paragraph
    "tasks": [
        {"playbook": str, "priority": int, "rationale": str}
    ],
    "kpis": dict,                       # current KPI snapshot
    "alignment_text": str,              # company-level alignment for the day
}

RecapPayload = {
    "synthesis": str,                   # COO's narrative recap
    "kpis": dict,                       # weekly KPIs
    "decisions_for_next_week": [
        {"decision": str, "rationale": str, "owner_employee": str}
    ],
}
```

## 8. Phased Build Order

Each phase is a discrete deliverable, reviewable, revertable. No phase ships without the prior phase passing tests + operator review.

| Phase | Name | Scope |
|---|---|---|
| 1 | Foundation extensions | Empty top-level dirs (`coo/`, `employees/`, `vertical-templates/`, `playbooks/`, `workflows/`, `tools/`); `aios/foundation/employee_memory.py` (Protocol + pgvector impl); `aios/foundation/feedback_loop.py` (service skeleton; record_outcome wiring; learning_event emission); SQL DDL for `employee_memory`, `employee_subscriptions`, `daily_dispatches`, `weekly_recaps`, `learning_events`; extend `SystemRegistry` with new services; wire embedder into the existing `SupabaseDecisionLogger`. **Universal — applies to every deployment.** Estimated 1-2 days. |
| 2 | COO end-to-end (Operations Director) | Build inside new structure from scratch. Daily-dispatch + weekly-recap playbooks. Output is structured JSON readable by future Slack/web surfaces. Daemon scheduling integration. Tests + live verification against the existing `kirsten-client-zero` deployment. Estimated 3-5 days. |
| **2.5 (NEW)** | **Slack chat interface** | Slack bot reads `daily_dispatches` + `weekly_recaps` for the deployment; accepts tagged commands (`@operations-director status`, `@operations-director dispatch`, `@<employee> run <playbook>`, `@<employee> last-week`); writes operator commands to a queue employees consume next run. Validates COO is operator-usable before any vertical-specific work. Estimated 1-2 days. |
| 3 | Vertical-template scaffold + creative-branding deployment config | Build `vertical-templates/creative-branding/` with `deployment.yaml`, `icp.yaml`, `knowledge-seed/`. Establish how a new deployment boots from a template. Loader code in `aios/foundation/deployment_loader.py`. CLYMB Co's existing deployment ports onto this template (no behaviour change; just configuration extraction). Estimated 1-2 days. |
| 4 | Migrate Prospect Researcher (existing Scout code) | `systems/scout/` → `employees/prospect-researcher/` under the creative-branding vertical. Extract integration helpers into `tools/`. Define playbooks (`lead_generation`, `icp_refinement`). Re-wire the daemon to consume dispatches + write to employee_memory on job completion. Existing 1349-suite must stay green. Estimated 2-3 days. |
| 5 | Migrate Content Writer (existing Beacon code) | `systems/beacon/` → `employees/content-writer/`. Reply-handling code becomes a workflow inside content-writer's playbooks initially (will move to Conversation Manager in Phase 7). Estimated 1-2 days. |
| 6 | Build Outreach Manager (net-new) | No existing code (Lead was paper). Build straight inside `employees/outreach-manager/`. Initial playbooks: `cold_email_outreach`, `linkedin_outreach`. **The reframed Slice D (Trigify engaged-content for Tier-1 icebreakers) lands here as a workflow inside `cold_email_outreach`.** Estimated 3-4 days. |
| 7 | Build Conversation Manager (net-new) | No existing code (Belay was paper). Build inside `employees/conversation-manager/`. Initial playbooks: `reply_handling`, `nurture_sequence`, `demo_booking`. Move reply-handling from Phase 5 home into this employee. Estimated 2-3 days. |
| 8 | Absorb Optimizer into COO | `systems/optimizer/weekly_review.py` and `recommendations.py` become COO weekly-recap workflow inputs. Decommission `systems/optimizer/`. Estimated 1 day. |
| **9 (NEW)** | **Web app (Next.js + Supabase)** | Operator dashboard, employee status views, KPI rendering, dispatch/recap card UI, approval flows for human-gated actions, deployment-management screen. Targets non-technical users (per `feedback_client_ux.md` — premium web app default). Estimated separate track, parallelisable from Phase 4 onward. |
| **10 (NEW)** | **Property-management vertical template** | Build `vertical-templates/property-management/` — PM-specific employee roster (e.g. Acquisitions Researcher, Tenant Relations Manager, Maintenance Coordinator, Rent Collection Manager, Owner Reporting Specialist, Marketing Specialist + Operations Director), PM-specific playbooks, PM integrations (AppFolio/Buildium/Zillow), PM knowledge-seed (lease templates, landlord-tenant law refs). First external-client deployment cohort kicks off from this template. Estimated 5-7 days for the template + 1-2 days per client deployment afterwards. |

The previously-named "decommission `agents/` and `departments/`" cleanup rolls into the appropriate phases as the migrations finish.

## 9. Decision Feedback Loop — concrete mechanics

Per the operator's addition: every job completion + new context/data triggers continuous learning across employees. The loop runs at four touchpoints:

1. **Job completion** — at the end of any Workflow that produced a measurable artifact (a sent email, a generated icebreaker, a published post, a captured reply), the workflow calls `feedback_loop.publish(client_id, employee_id, kind, content, outcome=None)`. This writes to `employee_memory` AND to `learning_events` for subscribed employees.

2. **Outcome arrival** — when a webhook or cron observes the outcome (reply, booking, ad metric), `feedback_loop.record_outcome(client_id, decision_id, outcome, outcome_data)` updates `decision_log` AND emits a learning_event linking decision → outcome. The pattern_matcher can now serve "what worked last time" queries with real outcome data.

3. **Standup synthesis** — daily and weekly, the COO reads recent learning_events + employee_memory and writes synthesis rows. Synthesis is itself stored as a learning_event (`kind='synthesis'`) so future standups have continuity.

4. **Employee subscription** — at Phase 1 we seed default subscriptions:
   - Content Writer subscribes to Outreach Manager's outcome events (subject lines that drove replies → content tone signal).
   - Outreach Manager subscribes to Content Writer's outcome events (post topics that drew engagement → outreach angle signal).
   - Conversation Manager subscribes to Outreach Manager's send events (which sequences produced replies → reply-handling priors).
   - Prospect Researcher subscribes to Outreach Manager's bounce events (bad emails → ICP refinement signal).

Subscriptions are data, not code — operator can edit `employee_subscriptions` rows to retune cross-pollination per-deployment.

## 10. Open Questions Deferred

These don't gate Phase 1 or Phase 2. Should be answered before the phase that hits them.

| Question | Gates phase |
|---|---|
| Playbook versioning — when we update a playbook spec, do running instances finish on old version or switch mid-stream? | Phase 6 |
| COO autonomy — does COO auto-promote low-risk recommendations or always human-in-loop? | Phase 2 (informs daily_dispatch authority) |
| Cross-playbook state — share via decision_log, or per-playbook isolated state? | Phase 6 |
| Department layer — when do we re-introduce `departments/` as middle layer? | When any deployment has 3+ specialists in one domain |
| Per-deployment subscription overrides — does each deployment get the same default subscriptions, or per-vertical? | Phase 6 |
| Slack workspace per deployment vs shared — do all deployments use one Slack workspace with channel routing, or one workspace per client? | Phase 2.5 |

## 11. Verification

The plan is complete when:

1. **Suite green** — every existing test (1349 currently) still passes after each phase.
2. **Live integration** — at the end of Phase 2, run COO against the real `kirsten-client-zero` deployment's `decision_log` + foundation. Confirm a `daily_dispatches` row is written for Prospect Researcher (the only employee currently active in that deployment), with a non-empty `tasks` array referencing real prospect-research activity.
3. **Slack gate (Phase 2.5)** — a Slack message to the Operations Director bot returns the latest dispatch text rendered as a card; a `@<employee> run <playbook>` command queues the playbook and the employee picks it up on next daemon tick.
4. **Deployment-isolation gate (Phase 3)** — provisioning a new deployment from the `creative-branding` vertical template produces an isolated employee roster + zero cross-deployment data leak (verified by querying foundation tables filtered by `client_id`; no rows from other deployments returned).
5. **Migration verification** — at the end of each migration phase (4, 5, 8), the migrated employee runs an end-to-end pipeline pass that produces identical (or improved) outputs vs the pre-migration baseline. No regression in score, enrichment quality, or send rate.
6. **Feedback loop closes** — at the end of Phase 6, simulate an Outreach Manager send + reply event. Confirm `decision_log.outcome` is backfilled, `learning_events` row is emitted, Content Writer's subscription consumes it, and the next Content Writer `compose` call's prompt includes the learning context.

## 12. Pre-Phase-1 Operator Decisions

Before Phase 1 starts, two practical decisions:

1. **Push the four local-only commits** (`8f93125 / f63b2f3 / 45c502b / 3356bf1`) to origin/main so they don't tangle with the structural rewrite.
2. **Approve this plan.** Specifically:
   - Per-deployment isolation framing reads right (Section 1 + Section 2 + foundation extensions all `client_id`-scoped)?
   - Plain-language renaming applied consistently?
   - Phase order: Foundation → COO → Slack → Vertical-template scaffold → Migrate Prospect Researcher → Migrate Content Writer → Build Outreach Manager → Build Conversation Manager → Absorb Optimizer → Web app (parallel) → Property-management template?
   - Slack at Phase 2.5 (smallest viable validation surface for COO before vertical work)?

Once those answers are in, Phase 1 starts. No code lands until then.
