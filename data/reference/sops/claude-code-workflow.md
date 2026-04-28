# SOP: Claude Code Workflow Discipline

**Purpose:** Capture the disciplines that make Claude Code work well as a real teammate — context-tight, plan-first, self-checking. Adapted from Nate Herk's "32 Claude Code Hacks" and tuned for the AIOS project's actual practices and existing memory.

**Owner:** Operator (Kirsten) + the assistant. Operator triggers session-management commands + edits permissions; the assistant maintains memory + code + framework discipline.

**Trigger:** Run through Section A at the start of every working session. Keep Sections B-D as mid-session reference. Section E is a one-time gap analysis.

**Inputs:** An open Claude Code session in this repo.

**Outputs:** Tighter context windows, fewer wasted cycles, better first-pass output, durable session logs, captured learnings.

## Why this exists — six core principles

1. **Context is the scarcest resource.** Keep it small, monitor it, trim aggressively.
2. **Plan before execute.** Plan Mode + clarifying questions + 95% confidence rule reduce wasted cycles.
3. **Treat the assistant like a teammate.** Give it problems, let it reason, challenge weak outputs.
4. **Bake quality checks into the work itself.** Self-checks live IN the to-do list, not after.
5. **Capture learnings.** Update memory + skills whenever something new is figured out.
6. **Right-size the model.** Haiku for bulk + parallel; Sonnet/Opus for synthesis (already in `CLAUDE.md` cost rules).

---

## Section A — Session start (operator)

Five-step checklist. Should take under 2 minutes.

1. **Open today's session log.** `memory/sessions/YYYY-MM-DD.md`. Read the latest entries to see where we left off.
2. **Read the memory layer** (already in `CLAUDE.md`):
   - `memory/MEMORY.md` — stable project context
   - `memory/INDEX.md` — recent decisions + open loops
   - Most recent `memory/sessions/` file
3. **Decide session shape.** One focused task or several? If several, plan to use `/clear` between unrelated tasks.
4. **Spot-check `/context` budget** if resuming a heavy session. Above 40% used? Consider `/compact` with keep-instructions before going further.
5. **Confirm permissions.** Quick mental check: is anything destructive on the deny list (`rm -rf`, force pushes)? Anything else that should be added?

---

## Section B — Mid-session discipline

### B.1 — Validating steps

Build verification into the work, not after.

- **`TodoWrite` for every multi-step task.** Mark in-progress immediately. Mark complete the moment a step is done — never batch.
- **Tests run after every code change.** Full suite (`uv run pytest`) for cross-cutting changes; targeted file for narrow ones. Zero regressions before commit.
- **Validator check on every draft of operator-facing copy.** Banned words (`leverage`, `solution`, `scale`, etc.) + em-dash + banned diagnostic phrases. The runtime would reject otherwise. See `systems/scout/enrich/icebreaker_adapter._BANNED_WORDS_RE`.
- **Framework-check on every reply-response template.** Maps to ARA (Acknowledge → Reassert → Advance) per `data/reference/frameworks/objection-handling.md`.
- **95% confidence rule.** Don't move to the next to-do until 95% confident the current one is right. 90% one-shot beats 60% one-shot.
- **Re-read after edit only when needed.** The harness tracks file state; if `Edit`/`Write` succeeded, the change landed. Re-read is for verifying complex transformations, not routine.

### B.2 — Managing context

- **`/context`** to see what's eating tokens. System prompt, file contents, MCP servers — drill into the percentages.
- **`/compact` at ~60% used.** Pass instructions to keep critical state, e.g. `"/compact but keep the Plan 2 acceptance criteria + the framework SOP location"`. Compresses without losing load-bearing decisions.
- **`/clear` between unrelated tasks.** Wipes conversation, keeps `CLAUDE.md` + supporting files. Faster than dragging long context into a fresh task.
- **Scoped reads.** Don't `Read` an entire 600-line file when you need lines 50-80. Use `offset` + `limit`.
- **Sub-agents for bulk reads.** When the work needs to ingest a lot (long doc, many files, large search), dispatch a sub-agent (Explore for read-only search; general-purpose for compose-and-summarise) so the main thread stays clean.
- **`CLAUDE.md` discipline.** Routes to `rules/`, `skills/`, `data/knowledge/`. Keep it ≤ ~200 lines. New principle? Route it out to a file under one of those trees, not inline.

### B.3 — Operator-assistant interaction patterns

- **Default to Plan Mode** (Shift + Tab) for non-trivial tasks. The assistant outlines + asks clarifying questions before changing anything. Skip Plan Mode only for mechanical edits (one-liner fixes, rename a constant).
- **Treat the assistant like a junior dev.** Give problems, not commands. "How should we handle X?" beats "Write me a function that does X."
- **Make the assistant ask questions.** "Continuously ask me questions until you're 95% confident you understand exactly what I need." Saves rounds of revision later.
- **Exit early and re-ask.** Wrong direction? Hit Escape, correct course, re-prompt. Wasted tokens compound.
- **Challenge weak outputs.** "This is just okay. Try a more elegant version" or "different approach entirely." Quality lifts dramatically on the second try when the bar is set.
- **Capture the learning.** Once a better version lands, ask the assistant to update `CLAUDE.md` or the relevant memory so the same mistake doesn't repeat. Hack #17 made literal.

---

## Section C — Session end (both sides)

Per `CLAUDE.md` session-end rule, enforced by the Stop hook.

- **Append to today's session log** (`memory/sessions/YYYY-MM-DD.md`): Summary, Decisions Made, Files Updated, Action Items, Counts.
- **Commit logical slices.** No giant end-of-day blob commits. Per-task or per-decision commits with clear messages.
- **Push.** `git push origin main` (or current branch). Local-only commits don't count.
- **Update `memory/INDEX.md`** if a significant decision landed or an open loop closed.

---

## Section D — When to reach for advanced moves

| Move | When to use | Cost |
|---|---|---|
| **Sub-agents** | Parallel research, bulk file reads, exploring multiple approaches | Cheap on Haiku, expensive on Sonnet/Opus |
| **`ultrathink`** | Architecture decisions, complex debugging, big refactors, when standard prompting falls short | ~32k tokens of thinking budget |
| **Git worktrees** (`claude-worktree <name>`) | Working on 2+ features in parallel without branch conflicts | Operator-side setup |
| **Custom skills** | Reusable workflows (code review, tech debt scan, copy grading) | One-time creation; reused across sessions |
| **Hooks** | Notifications when a session finishes; multi-session monitoring | Already configured for Stop hook (session log enforcement) |
| **`/loop`** | Recurring monitoring tasks within a single session (max 3 days) | Operator-triggered |
| **`/rewind`** | Quick undo of a wrong turn | Cheap + clean |
| **Agent Teams** | Large multi-stage projects where sub-agents need to coordinate + share state | Costlier than sub-agents; reach for it for cohesive big-project work |

---

## Section E — Adoption status: hack-by-hack

Status as of 2026-04-28. Update when state changes.

| # | Hack | Status | Notes |
|---|---|---|---|
| 1 | `/init` for project context | ✅ Done | `CLAUDE.md` exists, auto-loaded |
| 2 | Status line | Optional | Operator preference |
| 3 | Voice input | Optional | Operator preference |
| 4 | Keep context small | ✅ Practiced | Per-task scoping is the norm |
| 5 | `/context` to find bloat | Adopt | Run when sessions feel heavy |
| 6 | `/compact` at 60%, `/clear` between | Adopt | Make routine |
| 7 | Always start in Plan Mode | Partial | Adopt for non-trivial changes |
| 8 | Treat as junior dev | ✅ Operator's pattern | Continue |
| 9 | Make assistant ask questions | ✅ Practiced | Continue |
| 10 | Self-checks in the to-do list | ✅ Partial | TodoWrite + framework-check + validator + tests; formalised in B.1 |
| 11 | Sub-agents for parallel work | ✅ Used | Explore agent for repo searches |
| 12 | Custom skills | ✅ In place | `skills/operations/grade-cold-email-copy.md`, `filter-icp-list.md`, `skills/meta/validate-writing.md` |
| 13 | Haiku for sub-agents | ✅ Per `CLAUDE.md` cost rules | Continue |
| 14 | Refresh `CLAUDE.md` + memory | ✅ Done each session | Continue |
| 15 | `CLAUDE.md` routes to other files | ✅ In place | Routes to `rules/`, `skills/`, `data/`, `memory/` |
| 16 | Exit early + re-ask | ✅ Operator's pattern | Continue |
| 17 | Challenge outputs aggressively | ✅ Operator's pattern | See Template 1 iteration history (Session 2026-04-28). Continue + capture learnings |
| 18 | `/rewind` for undos | Adopt | Use when needed |
| 19 | Hooks for notifications | ✅ Stop hook configured | Enforces session log |
| 20 | Use screenshots | ✅ Operator practice | Connor Murray framework discussion was screenshot-driven |
| 21 | Chrome DevTools | N/A | Not currently a frontend project |
| 22 | Clone inspiration sites | N/A | Not currently a frontend project |
| 23 | Git worktrees | Adopt | Use when working on 2+ features |
| 24 | API endpoints over MCP | ✅ Memory: `feedback_cli_over_mcp` | Continue |
| 25 | `/loop` for recurring tasks | Adopt | Case-by-case |
| 26 | VPS for always-on | N/A | Not currently needed |
| 27 | Phone remote control | Optional | Operator preference |
| 28 | No-SQL data analytics via CLI | ✅ Partial | `scripts/cost_dashboard.py` does plain-English-shaped output; can extend |
| 29 | `ultrathink` | Adopt | Use for system-wide decisions |
| 30 | Edit permissions for safe autonomy | **Adopt** | Explicit allow + deny list. Don't run with `--dangerously-skip-permissions` blanket-on |
| 31 | Agent Teams | Available | Use for big multi-agent projects |
| 32 | Context 7 MCP | **Trade-off — operator's call** | Conflicts with `feedback_cli_over_mcp`. Pro: up-to-date library docs injected before code. Con: MCP tool definitions in context. If installed, fence its use to actual library work, not always-on |

---

## Section F — Command cheat sheet

| Command | Purpose |
|---|---|
| `/init` | Scan project + generate `CLAUDE.md` |
| `/statusline` | Live dashboard at terminal bottom (model, context %, cost) |
| `/voice` | Native voice-to-code |
| `/context` | See exactly what's consuming tokens |
| `/compact` | Compress conversation; can pass keep-instructions |
| `/clear` | Wipe conversation, keep `CLAUDE.md` + supporting files |
| Shift + Tab | Cycle modes (Plan → Default → Auto-accept) |
| `/rewind` | Roll back to a previous conversation point |
| `/hooks` | Configure notifications + lifecycle hooks |
| `/loop` | Recurring task within a session (max 3 days) |
| `ultrathink` | Allocate ~32k thinking-token budget |
| `claude-worktree <name>` | Create parallel isolated workspace branch |

---

## Section G — Cross-references

- **`CLAUDE.md`** — project master instructions (cost rules, autonomy levels, session-start + session-end protocols, workload tier).
- **`memory/MEMORY.md`** — auto-memory pointer file.
- **`memory/INDEX.md`** — recent decisions + open loops.
- **`memory/sessions/YYYY-MM-DD.md`** — daily session logs.
- **`feedback_cli_over_mcp`** — harness memory: trade-off vs MCP servers.
- **`skills/`** — custom skills (`grade-cold-email-copy`, `filter-icp-list`, `validate-writing`).
- **`data/reference/frameworks/`** — methodology references (`allbound-system.md`, `objection-handling.md`).
- **`data/reference/sops/`** — operational SOPs (this file, `agents-reference.md`, `esp-migration-smartlead-to-instantly.md`).
- **Nate Herk "32 Claude Code Hacks"** — original source. This SOP adapts + extends.

---

## When this SOP applies

- Daily — Section A start-of-session checklist.
- Mid-session — Section B-D as reference.
- New principle discovered — update Section E + this file's "When this SOP applies" section.
- New operator joins — they start here.

## When to update this SOP

Update when:
- A hack moves from "Adopt" → "Done" in Section E.
- A new Claude Code feature ships that's worth adding.
- A project-specific discipline lesson emerges that should be codified (capture-the-learning principle #5).
- A trade-off (like Context 7 MCP) gets resolved one way.
