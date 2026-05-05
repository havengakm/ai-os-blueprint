# Reference: AIOS Agents Roster

**Purpose:** Quick-reference for every named agent in the AIOS — who they are, what they do, when to call them, and where the code lives. Single source of truth for "which agent handles X?"

**Owner:** Kirsten (operator).

**When to use this doc:** When you need to know which agent is responsible for a task, what its current status is in the build, or how to invoke it (manually or via schedule).

**Maintenance:** Update this doc whenever a Plan ships an agent or changes scope. Cross-reference: `agents/README.md` (manifest convention), `agents/<name>.md` (per-agent manifest), `memory/INDEX.md` (active plans).

---

## Quick-look roster (as of 2026-04-27)

| Agent | Status | Wraps | Schedule | When to call manually |
|---|---|---|---|---|
| **Scout** | ✅ Live | `systems/scout/*` | Daemon tick + per-stage daily cron | Ad-hoc list ingestion, force re-run on a stale stage |
| **Beacon** | ⏳ Plan 2 (in progress) | `systems/beacon/*` | Continuous send-window scheduler | Pause sends on a contact, force a reply re-classification |
| **Optimizer** | ⏳ Plan 2 Phase 5 | `systems/optimizer/*` | Weekly cron (Mon 06:00 operator-tz) | Ad-hoc weekly review, cost dashboard query |
| **Autoresearch (5 surfaces)** | 📋 Plan 4 (drafted, blocked) | `systems/autoresearch/orchestrators/<surface>/*` | 4hr cron per surface | Pause/skip a cycle, force-promote a challenger |
| Email channel | (folded into Beacon) | `systems/beacon/channels/email/*` (Plan 2) | Send-window cron, per client-tz | n/a — internal to Beacon |
| LinkedIn channel | 📋 Plan 3 | `systems/beacon/channels/linkedin/*` | Same | n/a — Plan 3 |
| SMS / WhatsApp / Voicemail / Letters | 📋 Plan 3 | `systems/beacon/channels/<surface>/*` | Same | n/a — Plan 3 |
| Voice booking agent | 🚫 Backlog | (none) | n/a | Per `feedback_voice_agent_backlog_not_rejected` — only ever inbound demo booking + objection handling, never high-ticket closing |

Legend: ✅ live · ⏳ in progress · 📋 planned · 🚫 backlog / not building.

---

## Per-agent reference

### Scout

**One-line:** Turns raw directory listings into personalised, ready-to-send outreach drafts.

**Owns:** the prospecting half of a human SDR's job — pull, score, screen, identity-resolve, enrich, compose.

**Doesn't own:** sending (Beacon), reply handling (Beacon Phase 3), closing (human).

**Output:** rows in `outreach_drafts` table with `status='rendered'`.

**Schedule:** background daemon (`scripts/agent_daemon.py`) ticks every 15 minutes. Per-stage crons fire daily:
- Pull: 02:00 client-tz
- Score: continuous within daemon tick
- Identity: 03:30 client-tz
- Enrich: 04:00 client-tz
- Compose: hourly

**Manual triggers:**
- `uv run python scripts/run_daemon_once.py --client-id=<X>` — runs all 7 stages once for a client
- `uv run python aios/daemon/main.py --once --stage=<stage>` — runs a single stage
- API: `POST /api/pipeline/<stage>` with `client_id` body

**When to call manually:**
- A new client is provisioned and needs initial list ingestion.
- A stage stalled (operator sees contacts stuck at a status).
- Validating a config change (new niche variant, new ICP rule) on a small cohort.

**Reference files:**
- Manifest: `agents/scout.md`
- Code: `systems/scout/`
- Plan history: Plan 1 (foundation + Scout migration), Plan 1.5 (cost discipline + body template + Path B fixes).

---

### Beacon — Plan 2 (in progress)

**One-line:** Takes Scout's rendered drafts, schedules + sends them, ingests + classifies replies, auto-responds to common objections, escalates the rest to a human.

**Owns:** the send + reply half of a human SDR's job.

**Doesn't own:** prospecting (Scout), closing (human), strategy decisions (operator).

**Output:** sends to ESP via Instantly v2 API; rows in `outreach_send_log`, `outreach_reply` tables; Slack escalations for human-needed replies.

**Schedule:** continuous send-window scheduler. Daily caps per email account (~20-25/day during warmup, ramp to 30-50 once warm). Reply-ingest webhook fires on each ESP event.

**Manual triggers:** TBD (defined in Plan 2 Phase 2 Task 2.2.3).

**When to call manually (planned):**
- Pause sends on a specific contact (operator decided not to engage).
- Force-resend a draft after fixing a copy issue.
- Manually classify or escalate a reply that the auto-classifier got wrong.
- Pull recent reply stats for a client.

**Reference files:**
- Manifest: TBD (`agents/beacon.md` lands during Plan 2 Phase 2).
- Code: `systems/beacon/` (under construction).
- Plan: `docs/superpowers/plans/2026-04-26-plan-2-beacon.md`.

---

### Optimizer — Plan 2 Phase 5 (planned)

**One-line:** Reads decision_log + outreach_send_log + outreach_reply weekly. Surfaces cost-per-lead/reply/meeting, variant performance, adapter ROI, and recommends adjustments. Operator approves before any change applies (v1 = read-only-recommendations).

**Owns:** the learning loop — what's working, what's wasting money, where to invest next.

**Doesn't own:** auto-applying recommendations (that's Plan 4 territory). Doesn't generate new variant content (that's also Plan 4 / autoresearch).

**Output:** weekly markdown report at `data/captures/optimizer/<date>.md`; rows in `optimizer_recommendation` table; Slack notification with summary + report link.

**Schedule:** weekly cron, default Monday 06:00 operator-tz.

**Manual triggers (planned):**
- `uv run python scripts/run_optimizer_weekly.py --client-id=<X>` — runs an off-cycle review.

**When to call manually:**
- After a major config change (new niche, new ICP rules) — get a baseline report 7 days later.
- Mid-week ad-hoc cost check ("did anything spike?").
- Pre-board-meeting dashboard pull.

**Reference files:**
- Manifest: TBD (`agents/optimizer.md` lands during Plan 2 Phase 5).
- Code: `systems/optimizer/` (Plan 2 Phase 5).
- Plan: `docs/superpowers/plans/2026-04-26-plan-2-beacon.md` Phase 5 tasks.

---

### Autoresearch (5 surface orchestrators) — Plan 4 (drafted, blocked)

**One-line:** 5 independent per-surface orchestrators (subject_line, icebreaker, body_template, offer_frame, list_filter). Each runs a tight 4-hour loop: HARVEST → GENERATE challenger → DEPLOY A/B → MEASURE → PROMOTE/REVERT. Auto-evolves variant content based on objective metric (positive reply rate).

**Owns:** autonomous content generation + A/B-driven promotion. Goes beyond Optimizer's "recommend adjustments" by actually generating + deploying new content.

**Doesn't own:** strategic decisions (which surface to optimise, what counts as a winner) — those are codified in `resource.md` + `significance_threshold` config.

**Output:** new `component_variants` rows (status=`experimental` → `approved` or `rejected_by_autoresearch`); updated `baseline.md` per surface; append-only `results.log` per surface; Slack notifications on harvest events.

**Schedule:** 4-hour cron per surface (`0 */4 * * *` UTC).

**Manual triggers (planned):**
- `uv run python scripts/run_autoresearch_cycle.py --surface=<X> --client-id=<Y>` — run one cycle for one surface.
- `scripts/promote_baseline.py` — operator manual override to force-promote a specific challenger.

**When to call manually:**
- Pause / skip a cycle (campaign blackout window, holiday).
- Force-promote a challenger the operator likes even though it didn't statistically beat the baseline (use sparingly).
- Investigate a result.log entry.

**Reference files:**
- Manifest: TBD (`agents/optimizer.md` may include autoresearch as a sub-persona, or each surface gets its own).
- Code: `systems/autoresearch/orchestrators/<surface>/` (Plan 4).
- Plan: `docs/superpowers/plans/2026-04-27-plan-4-autoresearch.md`.

**Blocked on:** Plan 2 Phase 2 (Beacon send) + Phase 3 (reply ingest) + Phase 5 (Optimizer v1) shipping + 30 days of reply data.

---

### Voice booking agent — backlog (not building)

**Status:** Backlog per `feedback_voice_agent_backlog_not_rejected`. **Don't propose, build, or research** until pulled from backlog.

**If pulled from backlog (future):** primary use is **inbound demo booking** from ads / applications + handling a few common objections + handing off to a human for the actual demo + close. NOT for high-ticket closing calls. Voice agent = a smarter Calendly that pre-handles objections.

**Why in this doc:** so future sessions don't accidentally re-litigate the rejection. The earlier "AI voice agent REJECTED" memory was superseded; the current stance is "backlog with narrow primary use."

---

## Decision tree: which agent owns task X?

```
Is the task about turning a directory listing or CSV into ready-to-send drafts?
  → Scout

Is the task about sending an email, ingesting a reply, or auto-responding to an objection?
  → Beacon

Is the task about analysing what's working / not working over a week+?
  → Optimizer

Is the task about generating + auto-deploying NEW variant content based on A/B results?
  → Autoresearch (Plan 4 — blocked, see "Blocked on" above)

Is the task about closing a deal, negotiating pricing, or making commercial commitments?
  → Human (none of the above; AIOS doesn't close)

Is the task about LinkedIn / SMS / WhatsApp / voicemail / letters outbound?
  → Plan 3 (not yet built)

Is the task about a strategic / one-off operator workflow (variant authoring, list filtering, weekly review, copy grading)?
  → Operator-interactive Claude Code skill in skills/operations/* (Max-credits path; per
    feedback_max_credits_vs_api_boundary)
```

---

## How to call an agent

### Scheduled (default)

Agents fire on their schedule via the daemon. No operator action needed once the deployment is up.

```bash
# Scout: runs as a long-lived daemon process
uv run python -m aios.daemon
```

### Manual one-shot

Each agent's primary system has a `run_<stage>_once` or equivalent CLI:

```bash
# Scout — single client, single cycle
uv run python scripts/run_daemon_once.py --client-id=kirsten-client-zero

# Scout — single stage
uv run python scripts/run_daemon_once.py --client-id=kirsten-client-zero --stages=enrich

# Beacon (planned, Plan 2 Phase 2)
uv run python scripts/run_beacon_once.py --client-id=<X>

# Optimizer (planned, Plan 2 Phase 5)
uv run python scripts/run_optimizer_weekly.py --client-id=<X>

# Autoresearch (planned, Plan 4)
uv run python scripts/run_autoresearch_cycle.py --surface=subject_line --client-id=<X>
```

### Operator-interactive (via Claude Code skills)

Some agent-adjacent work runs as **operator-interactive skills** inside Claude Code (Max credits, per `feedback_max_credits_vs_api_boundary`). The operator drives; the skill invokes a sub-agent.

| Skill | When to use | Where it lives |
|---|---|---|
| `grade-cold-email-copy` (Plan 2 Phase 5) | Grade a draft variant before approving for production | `skills/operations/grade-cold-email-copy.md` |
| `filter-icp-list` (Plan 2 Phase 5) | Filter a fresh CSV through ICP rules + LLM judgment before ingesting | `skills/operations/filter-icp-list.md` |
| `generate-challenger` (Plan 4) | Generate a challenger variant for a specific autoresearch surface | `skills/operations/generate-challenger.md` |
| `review-experiment` (Plan 4) | Pre-deploy review of a generated challenger | `skills/operations/review-experiment.md` |

Run these via Claude Code's `Agent` tool with the appropriate `subagent_type`.

---

## What this doc does NOT do

- Does not replace `agents/<name>.md` per-agent manifests (those are the YAML source of truth for autonomy levels, schedules, skill bindings).
- Does not list every skill / playbook / composite — those live in `skills/` and have their own README per category.
- Does not document HOW each agent works internally — that's in the system code + plan docs.

## Related references

- `agents/README.md` — manifest format + roster (may lag this doc by a Plan-cycle).
- `agents/scout.md` — Scout's full manifest.
- `docs/superpowers/decisions/2026-04-21-aios-as-autonomous-sdr.md` — agents = the SDR function decomposed.
- `memory/INDEX.md` — active plans + recent decisions.
- `data/reference/sops/esp-migration-smartlead-to-instantly.md` — operational SOP for ESP migration (Beacon-adjacent).

## Format note

This doc is markdown for editability + git-diff. To export as PDF: `pandoc agents-reference.md -o agents-reference.pdf` (requires LaTeX) or use any markdown-to-PDF tool (e.g. https://md2pdf.netlify.app for a quick one-off).
