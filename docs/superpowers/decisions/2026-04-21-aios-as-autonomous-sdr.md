# Decision: AIOS = Autonomous SDR System (not a toolkit)

**Date:** 2026-04-21
**Decided by:** Kirsten
**Status:** Accepted

## Context

During the 2026-04-21 session we aligned on architecture across many threads (surround-sound channels, buying signals, cool-off + rounds, component registry, self-optimization, foundation wiring). The session's final clarification put it in one sentence:

> "So it's a full on SDR system. HeyReach focuses on LinkedIn outreach which is a separate module for us but the methodology is similar."

Plus:

> "The goal is to have an autonomous outbound agent."

These two statements lock the product identity. Every earlier architectural decision flows from this framing.

## Decision

**AIOS is an autonomous SDR system.** It replaces the SDR function — end-to-end — not a single channel, not a DIY toolkit, not a workflow editor for a human to drive.

### Scope of "SDR function"

The human SDR's job decomposes into:

| Function | AIOS system | Plan |
|---|---|---|
| Research + build prospect list | Scout (pull + score + screen + identity + enrich + signals) | Plan 1 |
| Draft personalised outreach | Composer + research module + component registry | Plan 1 |
| Execute sequences across channels | Channel modules with cross-channel state coordination | Plan 2 (email) + 3-6 (other channels) |
| Handle replies + route appropriately | Beacon reply handler + classifier + autoresponder | Plan 2 |
| Book qualified prospects into closer's calendar | Beacon autoresponder + Plan 5 voice-booking module | Plan 2 + 5 |
| Learn from outcomes + iterate copy/offers | Optimizer (weekly analysis + bandit promotion + operator-approve queue) | Plan 7 |
| Run 24/7 without trigger | Autonomous daemon + scheduler service | Plan 1 Task 16.6 + Plan 2 scheduler |

What AIOS does NOT do (stays human):

- Strategic ICP decisions (which niches to target)
- Offer framing changes (what we're selling + at what price)
- Autonomy-level promotions (trusting the system to operate more unattended)
- Closer calls (Shelby Sapp methodology — always human)
- Final compliance approval at client onboarding

### Operational shape

AIOS runs as named agents with personas (`agents/scout.md`, `agents/beacon.md`, `agents/optimizer.md`, one per channel module). Each agent:
- Has a defined scope of responsibility
- Invokes a set of skills (markdown procedures in `skills/`)
- Runs on a schedule (tick cadence driven by the daemon)
- Respects its current autonomy level (suggest / draft / act_notify / autonomous)
- Reports to operator via the web app dashboard + weekly optimization report

The Bella / Rex / Jinx pattern from the HeyReach/Trigify webinar is the reference. Our systems are named and personified so the operator has a clean mental model of "who is doing what right now."

## Reasoning

### Why this framing is sharper than "AI operating system"

Buyers don't shop for "an AI OS." They shop for "fractional SDR capacity without the overhead of hiring, training, and managing an SDR team." "Autonomous SDR system" names the buyer's problem. "AIOS" names the architecture. Use the buyer's language externally (sales, marketing, positioning), use AIOS internally (engineering, docs, code).

### Why competitive positioning improves

Each competitor is pushed into a narrower lane:

- **GHL (GoHighLevel):** generic multi-channel workflow tool. User assembles from scratch. Blank canvas. AIOS ships with expert frameworks embedded.
- **HeyReach:** single-channel LinkedIn execution tool. AIOS is all channels + cross-channel state coordination.
- **Clay:** enrichment + data orchestration tool. AIOS has enrichment as a subsystem plus everything else.
- **Outreach / SalesLoft:** workflow engine for SDRs + managers. They assume a human SDR uses the tool. AIOS IS the SDR.
- **Instantly / Smartlead / Lemlist:** email send + sequences. AIOS has email as a channel module.

### Why autonomy is non-negotiable (not a nice-to-have)

Without continuous unattended operation, AIOS is a tool someone has to drive. At that point, buyers compare it to other tools (on feature count, price, workflow editor ergonomics) and we lose on maturity every time. Autonomy is the moat — continuous learning + unattended execution produces outcomes that no tool operated by a human SDR can match at the same cost.

### Why each function maps to a specific plan

See `docs/superpowers/plans/2026-04-20-foundation-scout-migration.md` amendments + the session's approved roadmap re-plan in `~/.claude/plans/please-ask-questions-one-refactored-bubble.md`. The mapping is a direct translation of the SDR-job table above. No function is skipped; each is scheduled with explicit ownership.

## Implications

### Repo structure (added as part of this decision)

- `skills/` — agent-runnable markdown procedures, operator-readable. Subfolders: `operations/` (running the system), `onboarding/` (setup), `authoring/` (creating content), `analysis/` (interpreting outcomes)
- `agents/` — YAML manifests per named agent (Scout, Beacon, Optimizer, channel modules). Human-readable with inline comments.
- `data/reference/sequences/` — YAML sequence DAGs per niche per round
- `.claude/commands/` — Claude Code slash commands (already committed: build-context, create-plan, decide, implement, prime)
- `.claude/skills/` — Claude Code-discoverable skill files (future population from `skills/`)

### Foundation shared across every client deployment

Every client built on AIOS inherits: all skills, all agent manifests, all slash commands, all expert knowledge, all operational SOPs. Customisation lives ONLY in:
- `context/` — WHO (this client's brand, ICP, stakeholders)
- Supabase `client_config` + `icp_definitions` per-client rows
- Component variants authored per niche (the client picks their niche(s))

This matches `feedback_productised_not_custom` and is reinforced by this decision: systems must be contextual, not fragmented. New skills / agents / slash commands ship to ALL clients at once because they build on the same foundation.

### Every subagent dispatch goes through this lens

From now on, every implementer / planner / reviewer dispatch prompt references:
- `feedback_autonomous_sdr_positioning` (what AIOS is)
- `feedback_autonomous_agent_goal` (the daemon-first principle)
- `feedback_surround_sound_architecture` (multi-channel coordination)
- `feedback_simplicity_over_complexity` (with the critical-systems + quality-first exceptions)

These four memories together define the product. Features that don't honor them get flagged.

## Reversal conditions

This identity is revisited only if:

- Market research shows buyers want a tool-with-AI-assist rather than a full-function replacement (unlikely based on current conversations)
- Technical constraints prove autonomous operation is infeasible at acceptable quality (unlikely — the HeyReach/Trigify pattern is proven)
- A specific client deployment requires human-in-the-loop for strategic reasons — in that case, drop the autonomy gate to `suggest` for that client; don't redesign the system

Absent these, the identity stands.
