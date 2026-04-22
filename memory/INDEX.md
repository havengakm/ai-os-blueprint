# Memory Index

Scannable summary of what's active and what's pending. Update when a significant decision is made or an open loop closes.

## Recent Decisions

| Date | Decision | Rationale | Status |
|---|---|---|---|
| 2026-04-22 | Three-tier skill model (capability / composite / playbook) | Atomic-only left a real gap for multi-skill chains; adapted from Gooseworks public catalog | Active |
| 2026-04-22 | `skills/playbooks/` sits under `skills/`, not under `data/reference/sops/` | Everything agent-invokable lives in one tree; `data/reference/sops/` stays for human-facing docs | Active |
| 2026-04-22 | Four departments split out of Operations | Admin, Finance, Tax, Legal are distinct functions with distinct autonomy rules | Active |
| 2026-04-22 | Per-company AIOS silo | Each company gets its own `context/` + `data/`; foundation dirs shared as template; content never copied across deployments | Active |
| 2026-04-22 | `context/` = identity, `data/knowledge/` = facts | Loose personal files under `context/` root created ambiguity; tightened rule + migrated 15 files accordingly | Active |
| 2026-04-22 | Atomic skills rule (one input to one output to one job) | Broad skills like "copywriting" rejected; 15-category taxonomy | Active |
| 2026-04-22 | Global writing guardrails at `rules/global-writing-guardrails.md`, enforced by validator | "If not enforced at system level, everything degrades fast" | Active |
| 2026-04-22 | Memory layer adopted (Max Mitcham system, adapted) | Session logs + decision index fill real gaps; skipped MEMORY duplication | Active |
| 2026-04-21 | AIOS positioned as autonomous SDR system, not toolkit | Replaces SDR function; differentiated vs GHL / HeyReach / Clay / Outreach | Active |
| 2026-04-21 | Daemon-first, unattended autonomous operation as end goal | Every feature gated by "does this move us toward or away from autonomy" | Active |

Formal decision docs for higher-stakes items live in `docs/superpowers/decisions/`.

## Open Loops (To Do)

| Topic | Status | Next Action | Owner |
|---|---|---|---|
| Populate Hormozi KB files | Pending | Write `data/knowledge/experts/hormozi/offers.md` when the first Offer & Positioning skill needs it | Kirsten |
| Populate Brunson KB files | Pending | Write `data/knowledge/experts/brunson/funnels.md` when the first GTM skill needs it | Kirsten |
| Split `data/knowledge/company/` further | Pending | Decide whether `business-plan.md`, `strategy.md`, `metrics.md`, `current-data.md` stay here or move to `data/plans/`, `data/outputs/`, `data/captures/` | Kirsten |
| Clarify `context/voice.md` audience | Resolved 2026-04-22 | Moved to `data/knowledge/personal/voice.md` per Kirsten's confirmation (operator voice) | Done |
| Second composite skill | Pending | Write when a second real multi-skill workflow demands it | Claude |
| First playbook skill | Pending | Likely `launch-new-niche.md` or `onboard-new-client.md` when the underlying composites exist | Claude |
| Dev-time `.claude/skills/audit-new-skill.md` | Pending | Consider adding a helper that validates frontmatter + guardrail references on new skills | Claude |
| Client deployment provisioning script | Pending | Needed when the first client AIOS is spun up; bootstraps empty `context/` + `data/knowledge/personal/` + `company/`, copies `experts/` as baseline | Claude |
| Plan 1 Task 17 (diagnose-stuck-contact) | Pending | Part of Scout plan; not yet authored | Kirsten |
| Plan 2 (Beacon send scheduler) | Not started | Blocks autonomous send | Kirsten |
| Populate 14 remaining capability categories | Ongoing | Write atomic skills as systems need them, not pre-emptively | Claude + Kirsten |
| `agents/scout.md` references to legacy skill paths | Pending | Still points at `skills/operations/run-nightly-pipeline.md` etc; relocate to `skills/playbooks/` or `data/reference/sops/` when those are authored | Claude |
| Evaluate Instantly as vendor before building send engine | Pending | Hans / Max webinar 2026-04-21 pattern; revisit at Plan 2 kick-off | Kirsten |

## Active Plans

- Plan 1 (Foundation + Scout migration): in progress. See `docs/superpowers/plans/2026-04-20-foundation-scout-migration.md`.
- Plan 2 (Beacon): not started.
- Plan 7 (Optimizer): not started.

## Frozen Items / Explicitly Rejected

| Item | Rejected | Reason |
|---|---|---|
| AI voice agent | Yes | High-ticket calls stay human |
| Manus AI as research executor | Yes | Productisation + cost; Claude API replaces |
| Clay as enrichment vendor | Yes | Cognism / Hunter only on escalation |
| Telegram as client-facing UX | Yes | Operator-only; web app or Slack for clients |
| Claude Opus for any workload | Yes | Cost; Haiku batch, Sonnet complex |
| Folder-per-skill with `SKILL.md` + `skill.meta.json` (Gooseworks style) | Deferred | Premature; revisit at ~50 populated skills |
| JSON schema validation for skills (Gooseworks style) | Deferred | Premature; revisit at ~50 populated skills or first client provisioning |

## Pointers

- Historical decisions with full rationale: `docs/superpowers/decisions/`.
- Harness-level persistent memory: `~/.claude/projects/-home-kirsten-01-.../memory/MEMORY.md`.
- Operating principles (always loaded): `CLAUDE.md`.
- Session logs: `memory/sessions/`.
