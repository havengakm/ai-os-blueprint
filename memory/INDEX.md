# Memory Index

Last 30 days only. Compressed to one-liners; full rationale lives in `docs/superpowers/decisions/`, harness memories (`feedback_*`), commit messages, or PR descriptions. Decisions older than 30 days move to `memory/archive/` (next archive: June).

## Recent Decisions

| Date | Decision | Reference |
|---|---|---|
| 2026-05-04 | Cloud-execution + Supabase-as-context architecture approved (5 phases): operator cleanup, schema additions, foundation pip package, first routine, future agents | plan: `~/.claude/plans/i-know-that-claude-smooth-bird.md` |
| 2026-05-04 | Adopted Four-Cs audit skill + EAD gate + 60/30/10 autonomy target + intake archive helper from Nate Herk's AIS-OS | `memory/sessions/2026-05-04.md` |
| 2026-04-28 | Agent topology: 5 plain-language roles (Prospect Researcher / Outreach Manager / Conversation Manager / Content Writer / Operations Director); climbing names retired | `feedback_agent_topology_5_agents` |
| 2026-04-28 | Lead is multi-channel module (Scout pipeline + channel sub-modules; not sibling agents) | `feedback_lead_multi_channel_module` |
| 2026-04-28 | Reply auto-respond stays at `suggest` until 30+ {prediction, reply, outcome} triples per class @ ≥80% accuracy | `feedback_replies_manual_first_then_automate` |
| 2026-04-27..28 | Plan 2 Phases 2-6 shipped: Beacon foundation + reply runtime + cost optimiser + Optimizer v1 + productisation script. 954→1268 tests. | migrations 016-023 |
| 2026-04-27 | ESP locked: Instantly Growth ($47/mo); Smartlead pool kept warm 30d as backup | `docs/superpowers/decisions/2026-04-27-esp-comparison.md` |
| 2026-04-27 | Plan 2 scope expanded (3 of 5 ideas); Plan 4 (Karpathy autoresearch) reserved; Max-credits-vs-API workload tier codified | `feedback_max_credits_vs_api_boundary` |
| 2026-04-26 | Plan 2 = email full-loop only; LinkedIn deferred to Plan 3; Optimizer absorbed as Plan 2 Phase 5 | `docs/superpowers/plans/2026-04-26-plan-2-beacon.md` |
| 2026-04-26 | Plan 1.5 merged; tag `plan-1.5` pushed | PR #1, commit `72ece5f` |
| 2026-04-26 | Roadmap clarifications: voice agent backlog (smarter-Calendly only), cost optimiser as continuous concern | 4 new harness memories |
| 2026-04-25 | Plan 1.5 Path B: em-dash banned in composer + IcebreakerAdapter, 75-word rule relaxed to target | commits `cebd2e8` + `e1e2dd0` |
| 2026-04-25 | Acceptance pivots to creative_branding; fitness_wellness niche parked | `feedback_target_market_not_gyms` |
| 2026-04-25 | Plan 1.5 Phase A complete; memory-maintenance gap closed (Stop hook + session template) | follow-ups-plan1.md |
| 2026-04-25 | Trigify skills relocated to `skills/playbooks/`; legacy `onboarding/` + `analysis/` folders removed | three-tier model |
| 2026-04-22 | Six architectural decisions same day: three-tier skill model + atomic skills rule + per-company silo + context-vs-knowledge distinction + global writing guardrails + memory layer | architectural foundation |
| 2026-04-21 | AIOS positioned as autonomous SDR system; daemon-first unattended autonomy as end goal | `feedback_autonomous_sdr_positioning` |

## Open Loops

| Topic | Next Action | Owner |
|---|---|---|
| Plan 2 (email full-loop) | PR #2 awaiting operator review + merge | Kirsten + Claude |
| Plan 4 (Karpathy/Saraev autoresearch) | Hard depends on Plan 2 Phase 2/3/5 + 30d reply data | Kirsten + Claude |
| Plan 1.5 Phases B-E | In progress on `feat/plan-1.5-completion` | Kirsten + Claude |
| Cloud-execution + Supabase-as-context architecture | Phase 1 (operator cleanup) in progress | Kirsten + Claude |
| Mindbody + Google Maps scrapers | Parked; 3-stage rewrite when agency-client deployment spawns | Kirsten |
| Hormozi + Brunson KB files | Write when the first matching skill demands them | Kirsten |
| 14 remaining capability categories | Write atomic skills as systems need them, not preemptively | Claude + Kirsten |
| Reconcile new harness memories with project state | LinkedIn learnings + v2 body template + Plan 1.5 cost notes still need INDEX entries | Claude |
| `00_ARCHIVE/base-camp-agents/` | 2 docs ported; some niche files may still be worth pulling | Kirsten |
| Split `data/knowledge/company/` further | Decide whether business-plan/strategy/metrics/current-data stay or move to `data/plans|outputs|captures/` | Kirsten |
| HERMES + OpenCLAW manual research | Visit https://hermes-agent.nousresearch.com/ and https://openclaw.ai/. Evaluate fit vs current stack (Claude Routines + Trigger.dev + Claude Agent SDK + Supabase). Prior automated research returned unverifiable hallucinations; first-hand assessment needed before any adoption. Default recommendation: skip both. | Kirsten |

## Active Plans

Plan 1 (Foundation + Scout): COMPLETE 2026-04-23. Plan 1.5 (cost + acceptance + body template): COMPLETE 2026-04-26 (tag `plan-1.5`). Plan 2 (email full-loop): in progress, PR #2 open. Plan 3 (multi-channel surround-sound): not started. Plan 4 (Karpathy autoresearch): drafted 2026-04-27. Cloud-execution + Supabase-as-context: approved 2026-05-04.

## Frozen / Rejected

AI voice agent for high-ticket closing: rejected (closing stays human). AI voice agent for inbound booking: backlog (smarter-Calendly only, post Plan 2). Manus AI, Clay, Opus, Telegram-as-client-UX, n8n-alongside-Python: all rejected. See specific feedback memories.

## Pointers

Decision rationales: `docs/superpowers/decisions/` | Harness memory: `~/.claude/projects/-home-kirsten-01-PERSONAL-10-PERSONAL-PROJECTS-ai-os-blueprint/memory/MEMORY.md` | Operating principles: `CLAUDE.md` | Session logs: `memory/sessions/`
