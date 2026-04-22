# Context

What this deployment IS. Identity and configuration. Every AIOS deployment has its own siloed `context/` that is NEVER shared across deployments.

## Rule

- **`context/`** = **identity & configuration** (who the deployment is, how it's wired)
- **`data/knowledge/`** = **facts & frameworks** (what the deployment knows)

If you're ever unsure which folder a file belongs in, ask:
- "Does changing this file change WHO the deployment is?" → context
- "Does changing this file update a FACT the deployment draws on?" → knowledge

## Current contents

- `brand/`: brand identity assets (brand guide, voice, visual system, color palette, typography, mood board, design preferences)
- `integrations.md`: which external systems this deployment is wired to (APIs, databases, tools)

## Per-company silo

Each company's AIOS is fully siloed: its own `context/`, its own `data/`. The AIOS foundation (`skills/`, `rules/`, `departments/`, `agents/`, `systems/`, `os/`, `scripts/`, `api/`, `config/` structure, `.claude/commands/`) is the shared template every deployment inherits. `context/` + `data/` content NEVER copies across companies.

This deployment is Kirsten's (Clymb). A client deployment would have:
- the same `context/` folder structure (brand/, integrations.md)
- their own brand, their own integrations
- empty or client-specific contents; zero inheritance from Kirsten's files

## What was moved out on 2026-04-22

These files used to live at `context/` root but relocated to `data/knowledge/` per the "context = identity, knowledge = facts" rule:
- `personal.md`, `personal-operating.md`, `personal-operating-context.docx`, `voice.md` → `data/knowledge/personal/`
- `business-frameworks.md` → `data/knowledge/experts/general/`
- `projects/clymb/*` → `data/knowledge/company/` (Clymb is the company, not a sub-project)
- `projects/clymb/research/*` → `data/knowledge/company/research/`

## Future: sub-projects

If Clymb later spawns distinct sub-projects (product lines, client engagements), they can live at `context/projects/<project-name>/`. Until then, the `projects/` folder is intentionally absent. Don't pre-create it.
