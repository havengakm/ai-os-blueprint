# Memory Layer

Project-committed memory that travels with the code. Based on Max Mitcham's Claude Code memory system, adapted to coexist with the AIOS foundation.

## What lives here

- `MEMORY.md`: business context + tech stack + preferences. The "rarely changes" source of truth for this project.
- `INDEX.md`: scannable tables of recent decisions and open loops. Updated when a significant decision is made or a loop closes.
- `sessions/YYYY-MM-DD.md`: one file per working day. Summary, decisions made, action items.
- `topics/`: deeper dives by category (architecture/, preferences/, team/). Created only when a topic grows too long to live in MEMORY.md. Empty for now.

## How this fits with existing memory

The AIOS has several memory-shaped surfaces. They serve different audiences and DO NOT duplicate each other:

| Surface | Loaded when | Audience | Purpose |
|---|---|---|---|
| `CLAUDE.md` (repo root) | Every Claude Code session, automatically | You + Claude Code | Operating principles, hard rules, autonomy framework |
| `~/.claude/projects/.../memory/MEMORY.md` + files | Every Claude Code session, automatically | You + Claude Code (harness-level) | Per-user persistent facts across sessions (preferences, feedback, references) |
| `memory/` (THIS FOLDER) | On explicit read at session start | You + Claude Code + future collaborators | Project-scoped business/tech/decision context that travels with the code |
| `docs/superpowers/decisions/` | On demand | Operators + historical reviewers | Formal, dated decision docs with full rationale |
| `docs/superpowers/plans/` | On demand | Operators implementing | Step-by-step implementation plans |
| `docs/superpowers/specs/` | On demand | Operators designing | Brainstorming-phase design specs |
| `aios/foundation/decision_logger.py` (runtime DB) | Agent runtime | Scout, Beacon, Optimizer agents | Per-action autonomous-agent decisions with outcomes |

Rule of thumb:
- Personal-to-Kirsten feedback or preference that should persist across ALL projects: harness memory (`~/.claude/projects/.../memory/`).
- Project-wide principle or hard rule that should load every session: `CLAUDE.md`.
- Formal decision with full rationale worth re-reading later: `docs/superpowers/decisions/`.
- Daily work log, running decision index, open loops: `memory/` (here).
- Agent runtime decisions with outcomes: `decision_log` table via `aios/foundation/decision_logger.py`.

## Session-start instruction

At the start of every session, Claude should read:
1. `memory/MEMORY.md` for project context that rarely changes.
2. `memory/INDEX.md` for recent decisions and open loops.
3. The most recent file in `memory/sessions/` to see where we left off.

This instruction is also surfaced in `CLAUDE.md` so it loads automatically.

## Update rules

- Update `INDEX.md` whenever a significant decision is made or an open loop closes.
- Create a new session file at the start of each working day. At the end of the session, ask Claude to summarise what was done.
- Move stale detail out of `MEMORY.md` into `topics/` when a section grows beyond one screen.
- Keep `MEMORY.md` under 200 lines and `INDEX.md` under 100 lines. If either grows past that, split.

## Pruning

Session logs accumulate. Keep 30 days of daily files in `sessions/`. Older logs get summarised into a month-roll-up (`sessions/2026-04-summary.md`) and the daily files deleted. Pruning happens quarterly or when the folder hits 40+ files, whichever comes first.
