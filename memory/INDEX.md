# Memory Index

Scannable summary of what's active and what's pending. Update when a significant decision is made or an open loop closes.

## Recent Decisions

| Date | Decision | Rationale | Status |
|---|---|---|---|
| 2026-04-25 | Plan 1.5 Phase A complete (Tasks 1.5.1 - 1.5.4) | Four follow-ups-plan1.md rough edges fixed: preflight info_schema cross-check, seed scripts auto-load .env, test suite isolation from .env, cron_secret optional default. Test suite 925 → 927 passing. 7 pre-existing .env-leakage failures resolved. | Active |
| 2026-04-25 | Plan 1.5 plan doc formalised | 12 numbered tasks across Phases A-E; body template = new `body_template` component type at variant level; fitness_wellness acceptance = 1 rendered draft end-to-end. See `docs/superpowers/plans/2026-04-25-plan-1.5-cost-and-acceptance.md`. | Active |
| 2026-04-25 | Phase 0 merged to main | Both `fix/cost-discipline-haiku-waterfall` (24 commits) and `chore/folder-cleanup-pre-plan15` (2 commits) merged via separate `--no-ff` commits (`4ed108d`, `b1c060f`). Plan 1.5 remaining work on `feat/plan-1.5-completion`. | Active |
| 2026-04-25 | Memory-maintenance gap closed | Three layers: CLAUDE.md Session end rule + .claude/settings.json Stop hook + memory/sessions/_TEMPLATE.md. Triggered by 3-day session-log gap (Apr 22 → Apr 25). | Active |
| 2026-04-25 | Trigify skills relocated to `skills/playbooks/` | Multi-step orchestrations with code + human-in-the-loop fit the playbook tier; legacy `skills/onboarding/` and `skills/operations/` superseded | Active |
| 2026-04-25 | Legacy skill folders removed (`onboarding/`, `authoring/`, `analysis/`) | All were README-only stubs from before the three-tier model; deleted to avoid drift | Active |
| 2026-04-25 | Stale `os/` references replaced with `aios/` across 9 docs | Directory was renamed during Plan 1 (item 63 in follow-ups) but docs lagged | Active |
| 2026-04-25 | Plan1 worktree archived | `plan1-foundation-scout` branch fully merged; worktree was a stale 492MB checkout | Active |
| 2026-04-25 | Test CSVs moved to `data/captures/test_contacts/` | Loose `data/test_contacts_*.csv` at root were ephemeral test data; gitignored | Active |
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
| Second composite skill | Pending | Write when a second real multi-skill workflow demands it | Claude |
| First populated playbook | In progress | Two playbooks now populated (Trigify monitors + discovery); next candidates are `launch-new-niche.md` and `onboard-new-client.md` | Claude |
| Dev-time `.claude/skills/audit-new-skill.md` | Pending | Helper that validates frontmatter + guardrail references on new skills | Claude |
| Client deployment provisioning script | Pending | Needed when the first client AIOS is spun up; bootstraps empty `context/` + `data/knowledge/personal/` + `company/`, copies `experts/` as baseline | Claude |
| Plan 2 (Beacon send scheduler) | Not started | Blocks autonomous send. Evaluate Instantly-as-vendor first per `feedback_cold_email_stack_reference` | Kirsten |
| Plan 1.5 (cost + acceptance + body template) | In progress | Phase 0 merged to main; Phase A shipped on `feat/plan-1.5-completion`; Phases B-E remaining | Kirsten + Claude |
| Populate 14 remaining capability categories | Ongoing | Write atomic skills as systems need them, not pre-emptively | Claude + Kirsten |
| Merge order: cleanup branch + cost-discipline | Pending | Decide whether to merge cleanup into cost-discipline first, or both into main separately | Kirsten |
| Archive `00_ARCHIVE/base-camp-agents/` more aggressively | Pending | 2 valuable docs ported (icebreaker, Saraev templates); some niche files (functional-medicine, email-template-variations) may still be worth pulling if a relevant deployment spawns | Kirsten |
| Reconcile new harness memories with project state | Pending | LinkedIn analysis learnings + v2 storytelling body template + Plan 1.5 cost optimizations all add open loops not yet captured here | Claude |

### Plan 1.5 specific (from new harness memories)

| Topic | Status | Next Action | Reference |
|---|---|---|---|
| LinkedIn outbound playbook | Planned | 7d Tier 1/2 freshness, 48h SLA, Touch 2+3 ship with Plan 2 send | `feedback_linkedin_analysis_learnings` |
| LinkedIn content parallel to outbound | Planned | Future module | `feedback_linkedin_analysis_learnings` |
| Loom as future LinkedIn medium | Future | Pattern noted, not built | `feedback_linkedin_analysis_learnings` |
| 10x enrich cost reduction (Haiku swap + signal-gated Deep Research) | In progress | Phase 1 + Phase 2 commits landed on `fix/cost-discipline-haiku-waterfall` | `feedback_plan15_cost_optimizations` |
| v2 storytelling body template | Staged | Needs new `body_template` component type for template-level bandit A/B; copy locked verbatim | `feedback_v2_body_template_storytelling` |

## Active Plans

- Plan 1 (Foundation + Scout migration): COMPLETE. Branch `plan1-foundation-scout` merged into main 2026-04-23, branch deleted 2026-04-25.
- Plan 1.5 (cost discipline + acceptance + body template): in progress. Phase 0 (cost discipline + folder cleanup) merged to main. Phase A (rough edges) shipped on `feat/plan-1.5-completion`. Phases B/C/D/E remaining. See `docs/superpowers/plans/2026-04-25-plan-1.5-cost-and-acceptance.md`.
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
| n8n workflows alongside Python system | Yes | `aios/` foundation is the abstraction; do not shadow it (per `data/reference/frameworks/allbound-system.md`) |

## Pointers

- Historical decisions with full rationale: `docs/superpowers/decisions/`.
- Harness-level persistent memory: `~/.claude/projects/-home-kirsten-01-.../memory/MEMORY.md`.
- Operating principles (always loaded): `CLAUDE.md`.
- Session logs: `memory/sessions/`.
