# Archived: Old structural direction (2026-04-29)

This directory holds folders and documents from an architectural direction that was SUPERSEDED by the productised multi-repo plan (2026-05-05).

The earlier direction kept everything in one monorepo with top-level `employees/`, `coo/`, `playbooks/`, `workflows/`, `vertical-templates/`, `tools/`, `agents/`, and `departments/` folders. The new direction splits the AIOS into:

- A shared-core Python package (`aios-foundation`) plus per-system repos (`aios-scout`, `aios-beacon`, `aios-optimizer`, `aios-content`)
- Per-deployment repos (`<client>-deployment`) that compose which systems run for one company
- Per-deployment Obsidian vaults (`<client>-brain`, `<operator>-brain`) that hold business + personal knowledge as source-of-truth

See:
- `docs/superpowers/plans/2026-05-05-phase1-foundation-extraction.md` — Phase 1 detailed plan
- `~/.claude/plans/yes-this-fits-with-moonlit-elephant.md` — high-level architecture plan

These archived files are kept as historical decision context. Do not edit; they describe an architecture that no longer applies.
