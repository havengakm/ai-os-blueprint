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
