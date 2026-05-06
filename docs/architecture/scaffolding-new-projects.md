# Scaffolding new AIOS-connected projects

Where new code, content, and config live, and how each reaches the AIOS substrate.

Companion to [agent-deployment-lifecycle.md](agent-deployment-lifecycle.md). That doc covers the six-stage Python-agent lifecycle. This one adds the explicit decision tree, the JS/TS path, and the per-asset access table.

Authoritative source docs already in the repo (read these too):
- [agent-deployment-lifecycle.md](agent-deployment-lifecycle.md) — the "two homes" + six-stage lifecycle
- [data/reference/client-deployment-sop.md](../../data/reference/client-deployment-sop.md) — manual fork-and-deploy SOP
- [aios/dependency_container.py](../../aios/dependency_container.py) — the registry pattern that wires foundation + systems
- Memory entries: `feedback_per_company_aios_silo.md`, `feedback_productised_not_custom.md`, `feedback_departments_skills_knowledge_layout.md`, `feedback_agent_topology_5_agents.md`

---

## The big picture: three layers, never mixed

```
┌──────────────────────────────────────────────────────────────┐
│ Layer 1  PIP PACKAGES   shared library code                   │
│  github.com/aios-kit/aios-foundation  v0.2.0  (shipped)       │
│  github.com/aios-kit/aios-scout       v0.1.0  (shipped)       │
│  github.com/aios-kit/aios-beacon      Phase 2.2               │
│  github.com/aios-kit/aios-optimizer   Phase 2.3               │
│  github.com/aios-kit/aios-content     future                  │
│                                                               │
│  Versioned. Public-API stable. NEVER per-client.              │
│  Imported by every deployment via pyproject.toml git pin.     │
└──────────────────────────────────────────────────────────────┘
                              ▲
                              │ pip install / git pin
                              │
┌──────────────────────────────────────────────────────────────┐
│ Layer 2  DEPLOYMENT REPOS   per-client wiring + activation    │
│                                                               │
│  ai-os-blueprint/         ← THIS is the canonical CLYMB Co    │
│                             deployment today + dev sandbox    │
│  clymb-audit/             ← cloud routine repo (one per       │
│  clymb-discover/             scheduled agent, Phase 5+)       │
│  acme-co-deployment/      ← future client (forks blueprint)   │
│  loud-rumor-deployment/   ← agency client (different ICP)     │
│                                                               │
│  Each contains: registry.py, .env, context/, data/.           │
│  NEVER share content across deployments.                      │
└──────────────────────────────────────────────────────────────┘
                              ▲
                              │ reads
                              │
┌──────────────────────────────────────────────────────────────┐
│ Layer 3  CONTENT VAULTS / PER-CLIENT BRAINS  (Phase 4)        │
│                                                               │
│  kirst-brain/         ← personal Obsidian vault, expert refs  │
│  clymb-co-brain/      ← business Obsidian vault, frameworks   │
│  acme-co-brain/       ← future client, same shape             │
│                                                               │
│  Markdown-first. Git-backed. AIOS reads, never writes.        │
└──────────────────────────────────────────────────────────────┘
```

**Hard rule:** Code goes in Layer 1. Wiring + identity goes in Layer 2. Knowledge + facts go in Layer 3. They cross-reference; they never copy.

---

## Decision tree: which folder do I work in?

```
                          What are you working on?
                                    │
        ┌───────────────────────────┼────────────────────────────┐
        │                           │                            │
   New behaviour                Per-client                  Knowledge
   that ALL clients             config / brand /            content
   will use                     identity                    (frameworks,
   (an algorithm,               (logo, voice, ICP,          SOPs, swipe
   a new adapter,               API keys, schedule          files, expert
   a new system)                cron expressions)           material)
        │                           │                            │
        ▼                           ▼                            ▼
   pip-package           ai-os-blueprint/             Vault repo or
   repo (Layer 1)        OR future                    data/knowledge/
                         clymb-co-deployment/         (Layer 3)
                         (Layer 2)
                         in: context/, data/,
                            registry.py, .env

   Examples:             Examples:                    Examples:
   - new Apollo          - CLYMB's voice.md           - Hormozi offer
     adapter             - CLYMB's API keys             framework
   - new score           - which agents are           - Saraev outbound
     algorithm             enabled for this             playbook
   - new BaseSystem        client                     - per-niche swipe
     hook                - this client's cron           file
                           cadence
```

**Ask one question first:** *"If I delete this and start a fresh client tomorrow, do they need the same thing?"*
- Yes → Layer 1 (pip package)
- No, but every client wants their own copy → Layer 2 template (deployment repo)
- It's reference material I read, not code I run → Layer 3 (vault)

---

## When to break out into a separate repo

Default to the monorepo (`ai-os-blueprint`) until **all three** of these are true:

1. **The thing is stable.** Tests pass. Public API isn't changing weekly. You're done discovering what it should be.
2. **Something downstream needs a pinned version of it.** A deployment, a routine, or another package will `pip install` it at a specific tag and care which version.
3. **Splitting reduces churn, not adds it.** If extraction means you'll be cross-committing across two repos for every feature, don't extract yet.

Phase 1 (foundation) and Phase 2 (scout) extracted because all three were true. Beacon and Optimizer aren't extracted yet because their public APIs are still moving.

The opposite mistake — premature extraction — costs more than late extraction. An empty/half-complete `clymb-website-deployment/` repo is operator-cognitive bloat with no benefit. From the lifecycle doc: *"the agent passes a local dry-run end-to-end AND a real schedule has been decided. Not before."*

### Triggers that mean "yes, split now"

- About to schedule the thing in cloud (Routine, Trigger.dev, Cloudflare Worker) → make the deployment repo
- Two or more clients want this code → extract to pip package
- Public API stopped changing and you've been at this >3 weeks → extract to pip package
- You're about to write `if client_id == "clymb"` branching → STOP, that's a deployment-repo concern

### Triggers that mean "stay in monorepo for now"

- Still iterating on the API design
- Only CLYMB is using it
- Tests still flaky / coverage incomplete
- You're not sure what it's called yet

---

## Recipe A: New Python AIOS-connected project

Use this for: a new agent (clymb-audit, clymb-content-writer), a new daemon, a backend service that imports `aios-foundation` directly.

This is the **Stage-2 → Stage-5** path from the lifecycle doc.

### Stage 2 (BUILD): code lives in monorepo

```bash
# In ai-os-blueprint
mkdir -p systems/<agent-name>/{pipeline,storage}
mkdir -p tests/test_<agent-name>
```

Write the system inside `systems/<agent-name>/`:
- A `BaseSystem` subclass for the entry point (see [systems/scout/skill.py](../../systems/scout/skill.py) once Phase 2 monorepo cutover lands; today, `aios.scout.skill.ScoutSystem` after `pip install aios-scout`)
- Pipeline stages, adapters, storage backends — same pattern as scout
- Tests in `tests/test_<agent-name>/` against the same conftest

Wire it into [aios/dependency_container.py](../../aios/dependency_container.py) so existing routes can reach it.

**Stop here until tests are green.**

### Stage 4 (LOCAL DRY-RUN): prove it works end-to-end

```bash
# From monorepo root
.venv/bin/python scripts/run_<agent-name>_once.py --client-id=kirsten-client-zero --dry-run
```

Inspect output. Verify `decision_log` rows in Supabase.

### Stage 5 (CLOUD-REPO CREATE): extract the deployment vessel

Only when (a) tests pass, (b) you've decided when this runs in production, (c) you want it unattended.

```bash
gh repo create aios-kit/<deployment>-<agent> --private
# e.g. clymb-audit, clymb-discover, clymb-content-writer
```

Standard files (from [agent-deployment-lifecycle.md](agent-deployment-lifecycle.md)):

```
<deployment>-<agent>/
├── README.md               what this routine does, when it runs
├── CLAUDE.md               workflow-only instructions (<80 lines)
├── entrypoint.py           single script the cloud Routine runs
├── requirements.txt        pins aios-foundation@vX.Y.Z, aios-<system>@vA.B.C
├── .env.example            documents required env vars
├── .gitignore              .env, __pycache__, .venv
├── reports/                output dir (routine commits here)
└── <deployment>-context/   submodule pointing at vault (Phase 4)
```

`requirements.txt` example:
```
aios-foundation @ git+https://github.com/aios-kit/aios-foundation.git@v0.2.0
aios-scout @ git+https://github.com/aios-kit/aios-scout.git@v0.1.0
anthropic>=0.34.0
supabase>=2.7.0
```

`entrypoint.py` is **all** the deployment repo runs. It builds the registry, calls one method, writes a report. No business logic.

### Stage 6 (PROMOTE): schedule it, observe via reports/

Add the schedule (Trigger.dev / Claude Routine / cron). Watch the first three real runs. After that the operator only reviews the weekly Optimizer rollup.

---

## Recipe B: New JS/TS web app reading AIOS data

Use this for: a Next.js operator dashboard, a client portal, an internal tool that visualises decision_log + agent_outputs. Cannot directly `pip install` foundation — it's a Python package. Reaches AIOS through Supabase queries instead.

### Folder layout

```
clymb-portal/                          ← new private GitHub repo
├── README.md
├── package.json
├── next.config.ts                     ← or vite.config / remix / whatever
├── .env.local.example                 ← documents NEXT_PUBLIC_SUPABASE_URL etc
├── .gitignore
├── app/                               ← routes
├── components/                        ← UI
├── lib/
│   ├── supabase.ts                    ← @supabase/supabase-js client
│   └── aios.ts                        ← typed wrappers around the AIOS tables
└── types/
    └── aios.d.ts                      ← TypeScript types for decision_log,
                                          agent_outputs, knowledge_base, etc.
```

### Reaching AIOS from JS/TS

There are exactly two pipes (mirror of the Python three-pipes pattern):

1. **Supabase client** — read/write the same hub tables Python writes:
   ```ts
   import { createClient } from '@supabase/supabase-js'
   const sb = createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY)
   const { data } = await sb.from('decision_log')
     .select('*')
     .eq('client_id', 'clymb-co')
     .order('created_at', { ascending: false })
     .limit(50)
   ```
   Tables your JS app cares about: `decision_log`, `agent_outputs`, `knowledge_base`, `business_context`, `client_facts`, `agent_kpis`, `learning_events`.

2. **HTTP shim** (only if needed) — if you need to *trigger* a Python agent rather than just read state, hit a FastAPI endpoint exposed by the deployment's [api/main.py](../../api/main.py). For most dashboards you don't need this — read-only is enough.

### What does NOT belong in the JS repo

- API keys for third-party services (Apollo, Hunter, etc.). Those live in the Python deployment's `.env`. The JS app only needs `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (or anon key for client-side reads), and any auth-provider keys.
- Foundation Python code. The JS app never reasons about `BaseSystem` — it sees the *outputs* in Supabase.
- Per-client narrative context (voice.md, ICP.md). If the JS app needs to render those, expose them via a Supabase view or a FastAPI endpoint.

### When the JS app *is* per-client vs shared

- One JS app per client (e.g. `clymb-portal`, `acme-co-portal`) → simple, isolates secrets, one Supabase project per app
- Multi-tenant single JS app → ALL queries must `.eq('client_id', currentTenant)`, and you need row-level security in Supabase. More work, deferred unless you're running 5+ clients.

Default: **one JS app per client.** Match the per-deployment silo rule from `feedback_per_company_aios_silo.md`.

---

## Where each AIOS asset lives + how to reach it

| Asset | Lives in | Python access | JS/TS access |
|---|---|---|---|
| `BaseSystem`, `AutonomyGate`, `DecisionLogger`, `EmployeeMemoryPgVector`, `KnowledgeStore`, `PatternMatcher` | `aios-foundation` pip package | `from aios.foundation import ...` | n/a — read decision_log table directly |
| `ScoutSystem`, pipeline stages, adapters | `aios-scout` pip package | `from aios.scout import ScoutSystem` | n/a — read agent_outputs / decision_log |
| Per-client identity (brand, voice, ICP) | Layer 2 deployment repo: `context/` | Markdown read at runtime by `EmployeeMemoryPgVector.load_full_context()` | Read via Supabase `business_context` table or FastAPI shim |
| Per-client API keys, secrets | Layer 2 deployment repo: `.env` (gitignored) | `from aios.scout.config import get_settings` (4 keys); other secrets via `os.getenv` directly | Same approach via runtime env (Vercel env vars, etc.) |
| Per-client facts (decision history, contact list) | Supabase, scoped by `client_id` | `EmployeeMemoryPgVector` + custom queries | `@supabase/supabase-js` client |
| Knowledge (frameworks, swipe files, SOPs) | Layer 3 vault repos OR `data/knowledge/` in deployment repo | `KnowledgeStore.retrieve(client_id, query)` | Read via Supabase `knowledge_base` table |
| Cron schedules + which agents are active | Layer 2: `client_config.yaml` (Phase 3) | Read at startup by `build_registry()` | Same |
| Skills (atomic capability docs, playbooks) | Wherever the skill is canonical: foundation has cross-cutting; aios-scout has scout-specific; deployment has client-specific | Read by Claude Code at session start | Render in dashboard if useful |
| `BaseSystem` glue, registry wiring | Today: [aios/dependency_container.py](../../aios/dependency_container.py) in monorepo. Phase 3: `clymb-co-deployment/registry.py` | Imported by [api/deps.py](../../api/deps.py) and entrypoints | Triggered via FastAPI shim |

---

## CLYMB worked example: three concrete projects

| Project | Recipe | Why this shape |
|---|---|---|
| `clymb-audit` (a Claude routine that reviews CLYMB's decision_log weekly) | **Recipe A**, cloud routine repo. Code lives in `ai-os-blueprint/systems/auditor/` until Phase 2.4 extracts to `aios-auditor`. Routine repo `clymb-audit/` is `entrypoint.py` + reports/ + scheduled by Claude Routines. | Repeating Python workflow, weekly cadence, Claude reasoning. Six-stage lifecycle fits exactly. |
| `clymb-portal` (a Next.js dashboard for Kirsten to monitor CLYMB's pipeline) | **Recipe B**, JS app reading Supabase. Lives in its own private repo. Imports nothing from aios-foundation. | Visual UI, real-time, JS ecosystem. Reads outputs only; doesn't need to import Python. |
| `clymb.co` (CLYMB's marketing website) | Regular Next.js / Webflow / whatever. **Doesn't reference AIOS.** | Static marketing site has no business logic, no per-client decisions, no AIOS coupling. Don't pretend it does. |

Notice: even within "CLYMB website" there are three different shapes. The decision tree at the top of this doc resolves which.

---

## Verification

Once you've scaffolded a new project, you can test the wiring without burning credits:

### For Recipe A (Python AIOS-connected)
```bash
cd <new-project>/
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -c "from aios.foundation import AutonomyGate, DecisionLogger; from aios.scout import ScoutSystem; print('imports OK')"
python entrypoint.py --client-id=<client> --dry-run
```
Expected: imports succeed; entrypoint runs; if it talks to Supabase, decision_log rows appear with `dry_run=true` flagged.

### For Recipe B (JS/TS reading AIOS)
```bash
cd <new-project>/
npm install
npm run dev
# In a browser dev console:
#   const { data } = await supabase.from('decision_log').select('*').limit(1)
```
Expected: at least one row returned (proves the client-id + RLS + creds are wired). If empty, you're querying the wrong client_id or the deployment hasn't run yet.

### Decision-tree self-check (any shape)
Before shipping the new project, verify:
- [ ] No code in this repo would need to be edited if I onboarded a *second* client tomorrow (else: that code belongs in Layer 1 not Layer 2)
- [ ] No file in this repo names a different client by ID (else: cross-contamination — see `feedback_per_company_aios_silo.md`)
- [ ] No third-party API keys are committed (else: regenerate, gitignore, and add to `.env.example`)
- [ ] Foundation pin in `requirements.txt` / `package.json` references a tagged version, not `main` (else: not reproducible)

---

## Scope

- **Reference doc.** Read it, point future-you at it when starting a new project.
- **Not a Phase 3 plan.** Phase 3 (the actual `aios-deployment-template` scaffold + `clymb-co-deployment` extraction) is its own milestone. When ready, write a separate plan that produces a runnable `gsd-new-deployment` template, and link back to this doc.
- **Companion to [agent-deployment-lifecycle.md](agent-deployment-lifecycle.md)**, which is the canonical six-stage rule for Python agents. This doc adds the JS/TS path and the explicit decision tree.
