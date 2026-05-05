# AIOS Skills: Three-Tier Library

Everything the agent or an operator can invoke. Three tiers, one tree.

## The three tiers

| Tier | Scope | Steps | Decisions | Human gates | Example |
|---|---|---|---|---|---|
| **Capability** | One input, one output, one job | 1 atomic step | None | No | `generate-cold-email` |
| **Composite** | One batch orchestration | 3 to 8 capabilities chained | Linear | Rarely | `run-cold-outreach-campaign` |
| **Playbook** | End-to-end workflow | Many, often branching | Branches on signals | Named checkpoints | `launch-new-niche` |

Rule of thumb:
- Fits on one page with zero branches: capability.
- A sequence diagram with one path: composite.
- A flowchart with branches and human gates: playbook.

If a composite has more than 8 steps, branches on more than one condition, or pauses for human approval, it is a playbook.

## Folder structure

```
skills/
  meta/                      cross-cutting quality gates (atomic)
  <15 capability categories>/  one folder per category (atomic, flat per-category)
  composites/                multi-skill chains
  playbooks/                 end-to-end workflows
```

The 15 atomic capability categories: `market-intelligence/`, `offer-positioning/`, `gtm/`, `outbound/`, `inbound/`, `copywriting/`, `sales/`, `customer-success/`, `data-analytics/`, `revops-automation/`, `finance/`, `legal/`, `operations/`, `admin/`, `brand/`.

## What goes here vs elsewhere

| Location | Format | Purpose |
|---|---|---|
| `skills/` (here) | Atomic capabilities, composites, playbooks | Everything invokable |
| `rules/` | Global rule files | Guardrails every skill enforces |
| `systems/` | Python code | The runtime that executes skills |
| `data/reference/` | Human-facing system documentation | Specs, guides, deep explanations (not invokable) |
| `data/knowledge/` | Knowledge base | Personal, company, expert facts skills read |

`data/reference/sops/` is the home for **human-facing** system docs. `skills/playbooks/` is the home for **agent-invokable** workflows. A deep reference guide can link to a playbook and vice versa, but each file has one primary audience.

## Skill file convention

Every skill file (regardless of tier) uses this frontmatter:

```markdown
---
name: generate-cold-email
description: <concrete action; first sentence matters most for agent routing>
tier: capability | composite | playbook
category: <one of 15 categories; composites/playbooks may use a category or omit>
tags: [outreach, sales, cold-email, writing]    # controlled vocabulary, see below
input: <named inputs with types>
output: <named outputs with shapes>
requires_skills:                                 # other skills invoked at runtime
  - skills/meta/validate-writing.md
requires_tools: []                               # external APIs, MCPs, vendor CLIs
references:                                      # docs and KB read but not invoked
  - rules/global-writing-guardrails.md
  - data/knowledge/experts/saraev/cold-email.md
when-to-use: <explicit trigger or precondition>
human_checkpoints: []                            # playbooks only: named pause points
---

# <skill-name>

Follow rules/global-writing-guardrails.md.

## Purpose
## Inputs
## Steps  (capabilities)  |  Orchestration  (composites)  |  Phases  (playbooks)
## Output
## Quality gate
## Escalation
```

**Distinction that matters:**
- `requires_skills` = skills invoked AT RUNTIME by this skill's procedure
- `references` = docs, rules, KB files the skill READS for context
- `requires_tools` = external tools (Instantly API, Trigify CLI, Supabase) the skill touches

Moving `skills/meta/validate-writing.md` from `references` to `requires_skills` makes the skill-to-skill dependency graph explicit; tooling (future) can traverse it.

## Tag vocabulary

Tags are orthogonal to category folders. One skill has one category (its folder) but can have 2 to 5 tags spanning multiple domains. Controlled list:

**Domain tags** (pick at least one):
`outreach, sales, marketing, content, brand, research, ops, finance, legal, admin, analytics, revops, positioning, gtm, meta`

**Function tags** (pick 1 to 3 if useful):
`cold-email, linkedin, email, writing, sequencing, classification, reply-handling, personalisation, quality-gate, integration, scraping, enrichment, scoring, segmentation, reporting, forecasting`

Add a new tag to this list only when a second skill would use it. Don't invent one-off tags.

## The description field is a matcher

When an agent picks a skill, it reads the `description` first. Lead with the concrete action. Include when NOT to use if the trigger is narrow. Source: Max (Trigify) webinar 2026-04-21: "optimise that very first section that AI scans always."

## Content-producing skills must

1. Include `rules/global-writing-guardrails.md` in `references`.
2. Include the line `Follow rules/global-writing-guardrails.md.` near the top of the body.
3. Include `skills/meta/validate-writing.md` in `requires_skills`.
4. Invoke `validate-writing` on output before returning.

Grep check: `grep -L "rules/global-writing-guardrails.md" skills/outbound/*.md skills/inbound/*.md skills/copywriting/*.md` must return nothing.

## When to author a new skill

Three signals:
1. A concrete, repeatable unit of work happens more than once.
2. Code or infrastructure exists that the skill relies on.
3. A department manifest, composite, playbook, or agent will reference it.

Don't backfill empty skills. Mark the category README "populated" when authored.

## Productised library, per-deployment activation

Every AIOS deployment inherits the full `skills/` library and `rules/`. Client deployments activate a subset via the deployment repo's `client_config.yaml` (Phase 3 of the productised AIOS plan; see `docs/superpowers/plans/2026-05-05-phase1-foundation-extraction.md`). Customisation stays in `context/` and `data/knowledge/`. Never fork a skill per client.

## Gooseworks alignment

The three-tier model (capability / composite / playbook) is adapted from the public Gooseworks skills catalog, which ships 108 skills in these tiers. Folder-per-skill (their SKILL.md + skill.meta.json convention) and CLI installer tooling are deliberately NOT adopted yet; revisit at ~50 skills or when the first client-deployment provisioning script is needed.

## Legacy folders

`skills/onboarding/`, `skills/authoring/`, `skills/analysis/` remain from earlier scaffolding. They describe planned system-level runbooks that are actually playbooks by the new taxonomy. Relocation to `skills/playbooks/` happens when each is authored.

## Source

- Atomic taxonomy (15 categories): Kirsten's direction 2026-04-22.
- Writing guardrails: Kirsten's direction 2026-04-22.
- Three-tier model: adapted from Gooseworks skills catalog, analysed 2026-04-22.
- Portability principle: `docs/superpowers/decisions/2026-04-21-aios-as-autonomous-sdr.md`.
