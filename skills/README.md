# AIOS Skills

Agent-runnable markdown procedures. Each skill is a step-by-step set of instructions an agent (or human operator) follows to accomplish a specific operational task.

## What goes here vs elsewhere

| Location | Audience | Format | Purpose |
|---|---|---|---|
| `skills/` (here) | Agents + operators | Markdown with step-by-step imperative instructions | Unit of agent-executable work |
| `data/reference/sops/` | Humans (operators, developers, new hires) | Prose-heavy markdown with context + rationale | Understanding the system |
| `systems/*` | Python runtime | Code | The actual implementation an agent calls |
| `agents/*` | Operators | YAML manifest with inline comments | Who does what (persona + responsibilities) |
| `.claude/commands/` | Claude Code users | Slash command definitions | Interactive shortcuts |
| `.claude/skills/` | Claude Code agents | Claude-Code-native skill format | Skills the Skill tool can invoke |

**Rule of thumb:**
- Skill = one unit of work an agent runs (compose a draft, classify a reply, run the weekly optimization pass).
- SOP = the human-facing explanation of why the system works this way.
- System = the code that executes the skill.
- Agent = the named persona + schedule that invokes skills.

## Folder structure

- `operations/` — running the system day-to-day (run-nightly-pipeline, diagnose-stuck-contact, weekly-optimization-review)
- `onboarding/` — setting up a new client (onboard-client, seed-knowledge-base, configure-trigify-monitors)
- `authoring/` — creating or updating content (compose-draft, write-component-variant, score-offer-against-27-constraints)
- `analysis/` — interpreting outputs (handle-reply, classify-objection, explain-scoring-decision)

## Skill file convention

Each skill is a markdown file named in kebab-case: `skills/operations/run-nightly-pipeline.md`.

Suggested structure inside each skill:

```markdown
---
name: Run nightly pipeline
description: Advance all contacts through ready pipeline stages, log decisions, report tier distribution.
when-to-use: Daily at 02:00 client timezone, or on-demand for a dry-run.
trigger: Scheduler (Plan 1 Task 16.6) OR operator invocation via web app.
---

## Preconditions
- ...

## Steps
1. ...
2. ...

## Verification
- ...

## Escalation
- ...
```

Skills get authored as the corresponding plan tasks are completed. Don't backfill empty skills; write them when the underlying code works.

## Portability across client deployments

Every AIOS client inherits every skill. Customisation happens at the `context/` + `client_config` + niche-specific YAML-sequence level, not by forking skills per client. If a client legitimately needs a different procedure, the right move is usually a new autonomy gate or a niche-conditional step inside an existing skill, not a forked skill file.

See `docs/superpowers/decisions/2026-04-21-aios-as-autonomous-sdr.md` for the shared-foundation principle.

## Library scope — grows with AIOS systems

AIOS spans multiple systems per `CLAUDE.md` (Scout / Beacon / Optimizer / Content OS / Ads / Landing Page OS / etc.). The skill library grows as each system ships. Skills are authored alongside the code that implements them, NEVER preemptively.

Reference library for inspiration (inspired by the mature agency library Kirsten shared 2026-04-21):

### Scout + Beacon + Optimizer (Plan 1 + 2 + 7 — in or near scope)

- **Authoring:** compose-draft, write-component-variant, copywriting, copy-editing, brand-guidelines, email-sequence, score-offer-27-constraints, write-yaml-sequence
- **Analysis:** handle-reply, classify-objection, explain-scoring-decision, explain-composition-decision, competitor-intel, memory-recall, revenue-analysis, weekly-report-narrative, ab-test-setup, analytics-tracking
- **Operations:** run-nightly-pipeline, diagnose-stuck-contact, weekly-optimization-review, rerun-cool-off-contacts, pause-client, resume-client, inspect-daemon-state
- **Onboarding:** onboard-client, onboarding-cro, seed-knowledge-base, configure-trigify-monitors, configure-client-offer, configure-channel-stack, verify-deployment

### Content OS (future system — not yet planned)

Blog writing + SEO + content marketing. Candidate skills: `blog-research`, `blog-outline`, `blog-write`, `blog-status`, `schema-markup`, `programmatic-seo`, `linear-blog` (for Linear content roadmap integration), `marketing-psychology`, `marketing-ideas`.

### Ads system (future — per CLAUDE.md)

Paid acquisition across Meta / Google / LinkedIn Ads. Candidate skills: `paid-ads`, `launch-strategy`, `audience-research`, `creative-iteration`, `ad-performance-analysis`.

### Landing Page OS (future)

Conversion-rate optimisation for landing pages, popups, paywalls, forms. Candidate skills: `page-cro`, `popup-cro`, `paywall-upgrade-cro`, `form-cro`, `saved-search-cro`, `free-tool-strategy`, `frontend-design`.

### Distribution systems (future)

Post-launch growth mechanics. Candidate skills: `referral-program`, `employee-advocacy`, `customer-success`, `ceo-proactive` (for operator-level strategic tasks).

### Cross-system skills

Skills invoked by multiple agents regardless of which system they belong to: `memory-recall`, `brand-guidelines`, `analytics-tracking`, `pricing-strategy`. These sit in their natural role-based folder but get referenced by multiple agents' manifests.

## Skill ownership via agent manifests

Each agent's manifest (`agents/{name}.md`) declares which skills it invokes. Scout's skills appear in `agents/scout.md`; Beacon's will appear in `agents/beacon.md` when Plan 2 ships; each channel module's skills in its own manifest. One skill CAN be invoked by multiple agents (e.g., `memory-recall` is Scout + Beacon + Optimizer). That's expected — skills are the reusable units, agents compose them.

## When to add a new skill

Three signals that it's time:

1. A **concrete, repeatable task** that happens more than once (compose a draft, handle a reply, explain a scoring decision).
2. Code or infrastructure exists that implements it (don't author skills for features we haven't built).
3. An **agent manifest will reference it** (if no agent needs it, it probably doesn't belong as a skill — could be an SOP or just docs).

When you add a skill, update the relevant agent manifest to list it, and update the subfolder's README to remove the "planned" tag and replace with a link to the actual file.
