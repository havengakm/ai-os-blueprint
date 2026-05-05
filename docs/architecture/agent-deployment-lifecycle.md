# Agent deployment lifecycle

The two-home, six-stage rule for moving an agent from "idea" to "running unattended in the cloud." Read this before opening a new agent repo. Saves a lot of premature scaffolding.

Adopted 2026-05-04 alongside the cloud-execution + Supabase-as-context architecture (`~/.claude/plans/i-know-that-claude-smooth-bird.md`).

## The two homes

Every agent lives in two places:

1. **Master blueprint folder**: `ai-os-blueprint/systems/<agent>/`. Code lives here from the moment the agent is more than a spec, through development, through local testing. This is the dev source of truth.
2. **External routine repo**: `<deployment>-<agent>/` (e.g. `clymb-audit`, `clymb-discover`, `loud-rumor-scout`). A small private GitHub repo that the cloud Routine clones each run. Created **only when** the agent is ready for unattended cloud execution.

Both stay in sync forever after. The master repo is where you edit code; the external repo is the deployment vessel that the cloud runs.

## The six stages

```
Stage 1: SPEC               No code, no folder. Just a plan or spec doc.
Stage 2: BUILD              systems/<agent>/ folder created in master. Tests run locally.
Stage 3: SUPABASE-SEED      Insert agent_system_prompts + agent_skills + agent_frameworks +
                            agent_guardrails + agent_connections + agent_kpis rows.
Stage 4: LOCAL DRY-RUN      entrypoint.py runs end-to-end against dev Supabase from a
                            local venv. Operator manually reviews output.
Stage 5: CLOUD-REPO CREATE  NOW open the private repo (<deployment>-<agent>).
                            Copy entrypoint + CLAUDE.md + requirements.txt. Schedule the
                            Routine. Manually trigger first runs and observe.
Stage 6: PROMOTE            Schedule fires unattended. Operator reviews via reports/
                            commits + decision_log + Optimizer rollups.
```

The trigger to move from Stage 4 to Stage 5: **the agent passes a local dry-run end-to-end AND a real schedule has been decided.** Not before. Empty agent repos are operator-cognitive bloat for no benefit.

## When NOT to use this lifecycle

Some workflows aren't a good fit for the routine pattern:

- **Webhook listeners** (e.g. reply classifier ingesting Instantly webhooks). Always-on, sub-second response. Goes to a Cloudflare Worker or a tiny VPS, not a Routine. Code still lives in `systems/<agent>/`; deployment uses a different tool.
- **Per-contact pipeline steps** (enrichment, icebreaker generation) that need ≤1hr cadence and per-contact state. Routines have a 1hr frequency floor and are stateless. Use Trigger.dev instead. Code still lives in master `systems/`; deployment is a Trigger.dev task definition.
- **Always-on dispatchers** (per-minute send-window scheduler). Same reasoning as webhooks. Trigger.dev or VPS.

The cloud-execution-tool decision matrix:

| Workflow shape | Cadence | Deployment tool |
|---|---|---|
| Weekly Claude reasoning (audit, optimizer review) | weekly+ | **Claude Routines** |
| Daily Python pull (Trigify discovery, KPI snapshots) | daily | **Routines or Trigger.dev** |
| Per-contact pipeline (enrich, research, icebreaker) | ≤1hr | **Trigger.dev** |
| Webhook listener (reply ingest) | sub-second | **Cloudflare Worker** or **Hetzner VPS** |
| Per-minute dispatcher (send window) | per-minute | **Trigger.dev** |
| Multi-channel content agent | mixed | **Trigger.dev** triggers + **Routine** weekly review |

## Naming convention for routine repos

`<deployment-id>-<agent-id>`. Lowercase, hyphenated.

Examples:
- `clymb-audit`, `clymb-discover`, `clymb-linkedin`, `clymb-meta-ads`
- Future client: `loud-rumor-audit`, `loud-rumor-discover`, `acme-property-mgmt-tenant-comms`

Same code structure across all repos in a deployment. Same code structure across deployments for the same agent (different `client_id` env var, different Supabase row-set).

## Standard files in every routine repo

Every `<deployment>-<agent>` repo has the same shape. Use [clymb-audit](../../../clymb-audit/) as the canonical template.

```
<deployment>-<agent>/
├── README.md               : What this routine does, when it runs
├── CLAUDE.md               : Workflow-only instructions (under 80 lines)
├── entrypoint.py           : Single script the Routine runs
├── requirements.txt        : Pins aios-foundation + workflow-specific deps
├── .env.example            : Documents required env vars
├── .gitignore              : .env, __pycache__, .venv, etc.
├── reports/                : Output directory (routine commits here)
│   └── .gitkeep
└── <deployment>-context/   : Submodule (Phase 2 onwards)
```

What is **not** in a routine repo:
- Knowledge / frameworks / guardrails (in Supabase, scoped by `client_id` + `agent_id`)
- Foundation Python code (in `aios-foundation` pip package)
- Plans / specs / decisions (in `aios-planning/`)
- Per-client narrative context (in `<deployment>-context/` submodule)
- Tests (live in master `ai-os-blueprint/tests/` against the foundation package)

The routine repo is **only** the workflow vessel: instructions, entrypoint, output. Everything substantive lives elsewhere.

## Connected system: how agents share, report, learn, and improve

Per-agent repos are physical separation. Every agent is connected through one **shared central hub** (Supabase) plus a versioned Python package (`aios-foundation`). This is what makes the AIOS a connected operating system rather than a flock of independent bots.

### Three pipes every agent uses

Every agent (Scout, Beacon, Optimizer, Auditor, future LinkedIn / Meta Ads / etc.) accesses the shared foundation through exactly three pipes:

1. **Python imports** (the `aios-foundation` pip package, Phase 3)
   - `decision_logger.py`: log every decision an agent makes, with full context + outcome
   - `autonomy.py`: check the autonomy level for this agent + action_type before acting
   - `knowledge.py`: read + write `knowledge_base`, `business_context`, `client_facts` rows
   - `embedder.py`: vector-embed text for semantic search across all hub tables
   - `feedback_loop.py`: surface patterns across past decisions
   - `pattern_matcher.py`: match new decisions against past outcome patterns
   - `context_loader.py`: `load_agent_context(client_id, agent_id)` returns this agent's full role + skills + frameworks + guardrails + KPIs in one call
   - `api_registry.py`: `get_api_endpoint(service_name, client_id)` resolves which env-var holds the credential for a given service

2. **Supabase queries** (the hub itself, scoped by `client_id` + `agent_id`)
   - The structured per-agent context: `agent_system_prompts`, `agent_skills`, `agent_frameworks`, `agent_guardrails`, `agent_connections`, `agent_kpis` (all per Phase 2 migration 025)
   - The shared knowledge graph: `context_registry`, `business_context`, `client_facts`, `knowledge_base`
   - The cross-agent learning channel: `learning_events`, `shared_learnings`, `employee_subscriptions`
   - The audit trail: `decision_log` (every agent writes; auditor + Optimizer read)
   - The output index: `agent_outputs` (every artefact catalogued for retrieval)
   - The KPI ladder: `agent_kpis` rolling up to `business_objectives`

3. **Environment variables** (secrets, never in repo files)
   - `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, vendor API keys
   - Resolved through `api_registry.get_api_endpoint(service_name)` so agents don't hard-code env-var names; the registry maps service → env-var name → actual secret value

### How agents REPORT (write to the hub)

Every action an agent takes generates audit + learning + KPI signal:

| What the agent did | What gets written |
|---|---|
| Made a decision (e.g. send / skip / escalate) | `decision_log` row with context, decision, reasoning, predicted outcome, KPI tag |
| Produced an artefact (LinkedIn post, ad creative, cold email draft) | `agent_outputs` row with artefact_uri, output_kind, embedding for retrieval |
| Reached a state worth telling other agents | `learning_events` row routed to subscribers via `employee_subscriptions` |
| Surfaced a cross-agent pattern (e.g. "subject < 5 words doubles reply rate for creative-branding ICP") | `shared_learnings` row, vector-indexed for retrieval by any agent that hits a similar context |
| Updated a metric it owns | `agent_kpis.current_value` updated; rollup to `business_objectives.current_value` |

The hub is append-only for `decision_log` and `learning_events`. Nothing gets overwritten; outcomes get attached to the prior decision row when known.

### How agents LEARN (read from the hub)

When an agent starts a run, before deciding anything:

1. **Loads its own context**: `load_agent_context()` returns role + skills + frameworks + guardrails + KPIs.
2. **Loads relevant business context**: vector-search `business_context` + `client_facts` for the situation at hand (e.g. Beacon prepping a send checks ICP + voice + active sequences).
3. **Loads relevant frameworks**: `agent_frameworks` rows declare which `knowledge_base` entries this agent uses; agent retrieves them ranked by weight.
4. **Subscribes to upstream learnings**: `employee_subscriptions` declares which other agents' `learning_events` flow into this one. Beacon subscribes to Scout (lead source quality patterns); Optimizer subscribes to all (whole-team performance review); Auditor subscribes to all (cross-agent integrity check).
5. **Queries past similar decisions**: `pattern_matcher` looks at `decision_log` for prior decisions with similar context + their actual outcomes. Calibrates confidence before deciding.

### How the system IMPROVES (the feedback loop)

Three layers of improvement, each runs on a different cadence:

| Layer | Cadence | What it does |
|---|---|---|
| **Per-agent self-check** | Every run | Before acting: check `pattern_matcher` for similar past decisions + outcomes. Adjust confidence. Use `agent_guardrails` to short-circuit if rules violated. |
| **Cross-agent learning** | Continuous (event-driven via `employee_subscriptions`) | When agent A writes a `learning_event`, subscribers B, C, D get it routed. Next run, they query for it via `shared_learnings`. New pattern propagates within a few runs. |
| **Operator review** | Weekly (Optimizer agent + Auditor agent) | Optimizer reviews `decision_log` + `outreach_send_log` + `outreach_reply` + KPI rollups, surfaces recommendations to operator. Auditor scores deployment via Four-Cs and surfaces gaps. Operator approves changes; promotion/demotion of autonomy levels happens here. |

**Improvement that doesn't require code changes** flows through Supabase rows (operator updates an agent's `agent_guardrails` row, agent picks up the new rule on next run).

**Improvement that requires code changes** flows through the master blueprint (operator edits `systems/<agent>/`, runs tests, ships, deploys to the agent's routine repo).

### Daily standup + coordination

Agents need to operate as a team, not as isolated workers. The coordination layer has three flows: **daily dispatch** (COO briefs each agent), **event-driven triggers** (one agent's action causes another to react), and **weekly recap** (COO synthesises team performance for the operator). All three flow through Supabase tables that already exist or are being added in Phase 2.

**Daily standup flow** (Operations Director / Optimizer cron, every morning):

1. Optimizer reads the last 24h: `decision_log` (what each agent decided), `agent_outputs` (what each produced), `agent_kpis.current_value` vs targets, `outreach_send_log` + `outreach_reply` (campaign-level signals).
2. Optimizer writes one `daily_dispatches` row per active agent. Brief is human-readable: "Scout: 12 new contacts surfaced from Trigify yesterday, 8 scored A-tier, 4 in uncertain band needing UncertainZoneJudge. Continue creative_branding focus." "Beacon: 47 sends yesterday, 3 replies, 1 escalated to operator. Variant V3 underperforming at 0.4% reply rate, watch."
3. Each agent's next run reads its dispatch as part of `load_agent_context()`. The dispatch becomes part of the system prompt for that run.
4. Agents act on their dispatch + their own context.

**Event-driven trigger flow** (continuous, not cron-driven):

When agent A produces output that agent B should react to, the coupling is via shared tables, not direct calls. Each agent's runtime checks its watched tables on every run for new rows since its last run cursor.

| Producer | Writes to | Consumer | Reaction |
|---|---|---|---|
| Scout finishes enriching a contact | `outreach_drafts` | Beacon | Picks up draft on next send-window run, dispatches |
| Inbound webhook receives reply | `outreach_reply` (classification NULL) | Conversation Manager (Beacon reply runtime) | Classifies + routes to operator queue or auto-handler |
| Beacon classifies a positive reply | `outreach_reply.classification` updated | Operator notification + future booking handler | Operator gets Slack ping; booking flow triggers |
| Any agent surfaces a pattern | `learning_events` | Subscribed agents (per `employee_subscriptions`) | Read on next run, factor into decisions |
| Operator approves an Optimizer recommendation | `optimizer_recommendation.status='approved'` | Affected agent (Scout / Beacon) | Picks up new ICP weight / variant on next run |

The principle: **no agent calls another agent directly**. Coordination is via Supabase rows. This keeps every agent independently scheduleable, retry-able, and testable. It also keeps the silo rule intact: every row is `client_id`-scoped, so agent A in deployment X can't accidentally trigger agent B in deployment Y.

**Weekly recap flow** (Operations Director / Optimizer cron, Monday morning):

1. Optimizer reads the last 7 days across all the same sources as daily, plus `business_objectives.current_value` deltas.
2. Optimizer writes one `weekly_recaps` row per client: top 3 wins, top 3 issues, KPI deltas, recommendations needing operator approval.
3. Recap surfaces to operator via Slack / web dashboard / commit to a `reports/` repo (per the cloud-execution model, future `clymb-recap` Routine).
4. Operator reviews, approves recommendations, adjusts autonomy levels if warranted.

**What each agent knows about the others**:

- **High-level activity**: yes, via daily dispatch + subscribed `learning_events`. (Scout knows Beacon's reply rate trend; Beacon knows Scout's lead source quality.)
- **Specific tasks**: no, agents don't read each other's full `decision_log`. That's the COO's job (Optimizer subscribes to all).
- **Real-time state**: no, agents react to row changes between runs, not live events. Mid-run state isn't shared.

**Concrete example: Scout finds a new lead → Beacon sends → Conversation Manager handles reply**

```
T+0     Scout daily run: pulls Trigify, scores, screens, enriches, renders draft
        Writes: contacts (1 row), outreach_drafts (1 row),
                decision_log (4 rows: pull/score/screen/render), agent_kpis (cost-per-good-contact updated)
T+5     Beacon send-window cron tick: queries outreach_drafts WHERE status='approved' AND not_yet_sent
        Picks up Scout's new draft, dispatches via Instantly v2
        Writes: outreach_send_log (1 row), decision_log (1 row: send decision with KPI tag)
T+24h   Inbound: prospect replies. Webhook hits the reply ingest endpoint
        Writes: outreach_reply (classification NULL), learning_events (reply received)
T+24h+1m
        Conversation Manager (Beacon reply runtime): classifies via Haiku
        Writes: outreach_reply.classification updated, decision_log (classify decision)
        If positive_interest: writes shared_learnings ("subject pattern X gets positive replies for ICP Y")
T+next morning
        Optimizer daily standup: sees Scout's contributions, Beacon's send + reply outcomes
        Updates business_objectives.current_value (booked-demos rolling count)
        Writes daily_dispatches for tomorrow's runs
T+monday
        Optimizer weekly recap: aggregates the week
        Operator reviews
```

No agent called another. Every interaction was via a Supabase row. Yet the team operated as one.

### Why this design honours the silo + productisation rules

- **Per-company silo**: every Supabase row is scoped by `client_id`. Agent A in deployment X never sees deployment Y's rows. The same agent code runs for both deployments; only the `client_id` env var differs.
- **Productisation**: the foundation pip package + the schema + the universal skill library are identical across every deployment. New client = same code, same schema, new `client_id`-scoped row-set.
- **Knowledge compounds within a deployment**: the longer Clymb runs, the more its `decision_log` + `shared_learnings` accumulate, the smarter the agents get. Without leaking anything to other clients.
- **Cross-deployment learning** (across Clymb + future clients) is intentionally NOT built in. Each deployment is its own brain. If a pattern emerges in Clymb that should apply universally, it gets promoted into the universal `knowledge_base` (with `client_id="global"`) by an explicit operator decision, not automatically.

### Quick mental model

```
Every agent reads from and writes to the same hub:

         ┌─────────────────────────────────────────┐
         │            SUPABASE (per client)         │
         │                                         │
         │  agent_* tables    knowledge_base       │
         │  decision_log      shared_learnings     │
         │  agent_kpis        business_objectives  │
         │  api_registry      employee_subscriptions
         └────────────▲────────────────────────────┘
                      │
       ┌──────────────┼──────────────┐
       │              │              │
   ┌───┴───┐      ┌───┴───┐      ┌───┴───┐
   │ Scout │      │Beacon │      │ etc.  │
   └───┬───┘      └───┬───┘      └───┬───┘
       │              │              │
       └──── pip-installs aios-foundation ────┘
            (decision_logger, autonomy_gate,
             context_loader, api_registry...)
```

Agents are physically separate routine repos. They're logically one connected system because they all read and write the same hub via the same library.

## Worked examples: agents she named

| Agent | Stage today | Open `<deployment>-<agent>` repo when |
|---|---|---|
| **Auditor** (`clymb-audit`) | Stage 4 (audit-aios-health skill exists, cost dashboard runs locally; Phase 4 of plan ships next) | Phase 4: foundation pip package shipped, Supabase migration 025 applied, dry-run passes |
| **LinkedIn Content Writer** (`clymb-linkedin`) | Stage 1 (spec only) | After Plan 3 (multi-channel) ships and `systems/scout/channels/linkedin/` has working compose + post code, a 30-day cadence decided, KPI named ("inbound qualified leads from LinkedIn") |
| **Meta Ads Agent** (`clymb-meta-ads`) | Stage 1 (spec only) | After backlog promotion: `systems/meta_ads/` has working bid + creative-test logic, daily KPI pull working, escalation rules in `agent_guardrails` |
| **Website Design Agent** (`clymb-website`) | Stage 1 (spec only) | Likely never as a Routine. Heavy human-in-loop suggests Trigger.dev tasks instead. Re-evaluate when scoped. |
| **Scout / Discovery** (`clymb-discover`) | Stage 4 (working in `systems/scout/`) | Could ship now as a Routine. Plan 1.5 / Plan 2 deferred to keep Phase 4 single-routine first. |
| **Reply Classifier** (`clymb-reply-classifier`) | Stage 4 (working in `systems/beacon/reply/`) | Goes to a Cloudflare Worker / VPS, not a Routine. Different deployment model. |

## Productisation rule preserved

When a second client deployment spins up (e.g. property management):

1. The same agent code in master `systems/<agent>/` runs for both deployments. No fork.
2. New `<new-client>-<agent>` repo gets created with the same shape as the existing one. Different `client_id` env var.
3. Supabase rows scoped by the new `client_id` provide deployment-specific context.
4. Vertical-specific defaults come from `data/knowledge/verticals/<vertical>/` starter pack at provisioning.
5. Operator tunes per client via Supabase row updates.

Every deployment looks structurally identical. Vertical muscle plugs into named slots.

## Quick reference: where does X live?

| Thing | Lives in |
|---|---|
| Agent's Python code (during dev + after) | `ai-os-blueprint/systems/<agent>/` |
| Foundation modules every agent uses | `aios-foundation/` (pip package) |
| Per-deployment narrative context | `<deployment>-context/` (submodule) |
| Per-deployment structured context | Supabase rows scoped by `client_id` |
| Per-agent system prompt + skills + frameworks + guardrails + KPIs | Supabase `agent_*` tables |
| Plans, specs, formal decisions | `aios-planning/` (sibling folder, future repo) |
| Skill definitions (universal capability library) | `ai-os-blueprint/skills/` |
| Vertical starter packs (knowledge defaults per industry) | `ai-os-blueprint/data/knowledge/verticals/<vertical>/` |
| Department activation manifests (which systems run per vertical) | `ai-os-blueprint/departments/<vertical>.md` |
| Cloud Routine config (schedule, env, network access) | `claude.ai/code/routines` (web UI) |
| Test suite | `ai-os-blueprint/tests/` (against pip-installed foundation) |
| Session memory + INDEX | `ai-os-blueprint/memory/` |

## When this doc stops being current

Revisit and update:
- After Phase 3 ships (foundation pip package real, not preview)
- After Phase 4 ships (first routine running unattended)
- After the second client deployment spins up (productisation tested in practice)
- When a new cloud-execution tool (e.g. HERMES, OpenCLAW) is evaluated and adopted

Otherwise, this doc stays the canonical reference.
