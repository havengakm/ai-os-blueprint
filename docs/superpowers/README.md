# docs/superpowers (relocated)

Plans, specs, and decision logs moved out of this repo on 2026-05-04 to keep the always-loaded surface lean. They now live in the sibling folder:

`/home/kirsten/01_PERSONAL/10_PERSONAL_PROJECTS/aios-planning/`

## What moved

| Was here | Is now |
|---|---|
| `docs/superpowers/plans/` | `aios-planning/plans/` |
| `docs/superpowers/specs/` | `aios-planning/specs/` |
| `docs/superpowers/decisions/` | `aios-planning/decisions/` |

## Why

Operator-only artefacts. Never auto-loaded by Claude; never read by routines; never shipped to client deployments. ~540K of weight removed from the master repo working tree.

## Pointer references

Existing INDEX.md and CLAUDE.md references to plan filenames (e.g. `docs/superpowers/plans/2026-04-26-plan-2-beacon.md`) resolve in the sibling folder under the same relative path.

## Lifecycle

When the cloud-execution architecture (per `~/.claude/plans/i-know-that-claude-smooth-bird.md`) goes live, `aios-planning/` becomes a private GitHub repo. Until then it's a local sibling for review.
