# Decision: Lead-sourcing + enrichment architecture

**Date:** 2026-04-20
**Status:** Accepted
**Decider:** Kirsten
**Drafted by:** Claude (AIOS agent) during Plan 1 execution
**Affects:** Plan 1 Tasks 9, 10, 12, 14 (reshape); new Tasks 3.6, 3.7 (client_config + settings); Plans 2/3/4 (downstream tool additions)

## Context

Plan 1 ported base-camp-agents' outbound pipeline, which defaults to Apollo as the primary lead source and uses generic email verification. During execution Kirsten flagged three shifts:

1. Apollo/ZoomInfo-style commodity databases are saturated — decision-makers on those lists are desensitised to cold outreach. Specialist directories (Clutch-for-agencies pattern, already proven in base-camp-agents) produce higher-intent, higher-response audiences at lower cost.
2. Manus AI is the preferred executor for scraping + research + enrichment wherever it can replace paid API credit burn.
3. Enrichment spend must be tiered by `icp_score` — no deep research or phone lookup on low-intent leads. Phone lookup hard-gated at score ≥ 50. No research/enrichment below score 35.

## Decision — one-sentence summary

**Scout's lead pipeline uses a Manus-first + directory-first architecture with tiered waterfall enrichment pegged to `icp_score`, a lean vendor stack (Manus Pro + Apollo + Lusha + ZeroBounce, ~$135–165/mo), and jurisdiction-aware phone/SMS compliance — with specialist tools (Cognism, Hunter, Trigify, Champify, RB2B, Swan) added only when declared escalation triggers fire.**

## Architecture — in full

### Layer 1 — sourcing priority order

| # | Source | Mechanism | Cost |
|---|---|---|---|
| 1 | Specialist directories / associations | Dedicated adapter (Clutch) + generic Manus `directory_spec.yaml` | ~free (Manus credits) |
| 2 | Niche public sources (podcasts, conferences, team pages, Who's Who, regulatory registers) | Manus parameterised research | ~free |
| 3 | Apollo (commodity DB) | Direct API adapter | Subscription |
| 4 | CSV ingest | Upload + re-verify | — |

### Layer 2 — field-by-field waterfall

| Field | Primary | Secondary | Tertiary | Gate |
|---|---|---|---|---|
| First / last name | Directory | Manus | Apollo | Always |
| Company website | Directory | Manus | Apollo domain | Always |
| LinkedIn URL | Directory | Manus | Apollo | Always |
| Work email | Directory (if public) | Apollo finder | Pattern-match | Always |
| Email verified | ZeroBounce | — | — | Pre-send |
| Mobile (SMS) | Lusha | Cognism (escalation) | Apollo Premium (US) | **`icp_score ≥ 50` HARD** |
| Job title | Directory | Manus | Apollo | Always |
| Firmographics | Apollo | Directory | Manus | Always |

### Layer 3 — two-phase scoring (0–100)

**v1 (post-pull, pre-enrich):** Fit 40 + Reach 20 + Recency 10 = max 70. Archive if < 35.
**v2 (post-enrich):** Add Intent 30 (funding / hiring / product / leadership / individual activity / job postings). Final = 0–100.

Tier map:
- **A** 80+ — full enrich ~25¢/contact
- **B** 65–79 — mid enrich ~12¢
- **C** 50–64 — light enrich ~8¢ (phone floor)
- **D** 35–49 — email + verify only ~3¢ (no phone, no research)
- **Archive** <35 — 0¢

Weights configurable per client in `client_config.weights`. Per-tier budgets in `client_config` (not a single `enrichment_budget_per_contact_cents` field).

### Layer 4 — intent signals (three-tier)

| Layer | Pattern | Tool | Plan |
|---|---|---|---|
| L1 research-time | Manus one-shot per contact (hiring, funding, posts, job listings) | Manus Pro | **Plan 1** |
| L2A outbound target triggers | Continuous monitoring of our target list | Trigify.io | Plan 3–4 |
| L2B inbound visitor triggers | Continuous website visitor deanon | RB2B free → Swan AI | Plan 2+ |

L2A and L2B push webhooks → `activity_log` → re-score. Schema supports today; no Plan 1 changes.

### Layer 5 — vendor stack (lean baseline)

| Role | Vendor | Cost |
|---|---|---|
| Scraping + research | **Manus Pro** | ~$40/mo |
| Work email + domain | **Apollo Basic → Pro** | $49–79/mo |
| Mobile (SMS-enabled) | **Lusha Team** | $29/mo |
| Verification | **ZeroBounce** | ~$18/mo |

**All-in ~$135–165/mo.**

**Escalation triggers:**
- 5+ active clients OR heavy EU/UK/GDPR → add **Cognism** (compliance-grade mobile + DNC)
- Apollo email-finder hit rate < 85% → add **Hunter.io** as second-pass
- US-mobile-heavy deployment → upgrade Apollo to Professional tier
- Warm-list re-engagement becomes the optimisation lever → add **Trigify**
- First content/landing pages driving traffic → add **RB2B free** (US) or **Swan AI** ($99–299)
- 2+ year customer base for job-change tracking → add **Champify**

**Rejected from the stack:**
- **Clay** — middleman credit markup; workspaces don't template across clients (violates productisation). Acceptable only as short-term VA convenience for ad-hoc list cleanup — not production backend.
- **ZoomInfo** — saturated-lead problem + enterprise pricing without structural advantage over Cognism.
- **Common Room / UserGems** — priced at enterprise tier; not justified at startup scale.

### Layer 6 — deliverability + compliance

- **Domain separation** — cold from `try-{client}.co`, never primary domain
- **SPF + DKIM + DMARC strict** during provisioning (SOP 03-setup-railway extension)
- **Email verification** — ZeroBounce every address pre-send; catch-all threshold configurable
- **Per-inbox throttling** — max 40 sends / inbox / day (Smartlead — Plan 2)
- **Bounce budget** — rolling 7-day bounce > 3% on any inbox auto-pauses it (Plan 2 enforcement; thresholds defined now)
- **QA sub-agent** — Plan 2 agent scores every draft on placeholder factuality, spam-trigger density, relevance-to-research fit; fail = no send
- **SMS compliance** — see `data/reference/sops/compliance/phone-sms-compliance.md`. Waterfall: Lusha → Cognism → Apollo. Score ≥ 50 only. Jurisdiction-aware (POPIA / GDPR / TCPA / CASL). STOP mechanism SLA 24h. DNC screening per send.

## Quality + cost targets

| Metric | Target | Mechanism |
|---|---|---|
| Cost per Tier A qualified lead | < $0.50 | Manus does heavy lift, tier-gated enrich |
| Cost per Tier D touched lead | < $0.05 | Email + verify only |
| Email finder hit rate | > 85% | Escalation trigger for Hunter otherwise |
| Bounce rate rolling 7-day (per inbox) | < 3% | ZeroBounce pre-gate + auto-pause |
| Opt-out rate weekly | < 2% | QA relevance gate |
| Manus credits per 1k contacts | < 1k credits | Prompt tuning + re-eval if breached |
| Manus research hit rate (intent signal found) | > 60% Tier A/B | Prompt tuning cycle |

## Plan 1 impact — task-level changes

### New tasks
- **Task 3.6** — extend `client_config` with per-tier budgets + `active_directories` list + `weights` JSON; DB migration appendix to `002_scout.sql` (or a new `003_client_config_tiers.sql`)
- **Task 3.7** — extend `Settings` + `.env.example` with `MANUS_API_KEY`, `LUSHA_API_KEY` (keeping Apollo + ZeroBounce keys already declared)

### Reshaped tasks
- **Task 9 `pull.py`** — introduce `systems/scout/sources/` package: `clutch.py` (port from base-camp-agents), `manus_directory.py` (generic directory_spec-driven adapter), `apollo.py` (fallback), `csv_ingest.py`. `pull.py` becomes an orchestrator that reads `client_config.active_directories` and dispatches.
- **Task 10 `score.py`** — two-phase scoring: `score_v1()` post-pull, `score_v2()` post-enrich; weights read from `client_config.weights`; tier assignment on result.
- **Task 12 `enrich.py`** — introduce `systems/scout/enrich/` package: `manus_research.py`, `apollo_enrich.py`, `lusha.py`, `zerobounce.py`. `enrich.py` becomes the tier-gated orchestrator. Every blocked adapter call logs to `decision_log` with reason.
- **Task 14 research module** — Manus-driven with structured JSON output schema (company_summary, recent_events, tech_stack_signals, decision_maker_recent_activity, open_roles, hook_candidates, buying_intent_score). Depth pegged to tier.

### Unchanged
- Tasks 1–8 (worktree, deps, settings scaffold, schemas already committed, SOPs, API, middleware, trigger)
- Tasks 11 (screen), 13 (templates), 15 (renderer), 16 (deployment scripts), 17 (e2e), 18 (SOPs), 19 (verification) — the reshape above doesn't change these

## Out-of-scope (deferred)

- **Plan 2:** QA sub-agent, Smartlead send + warmup, webhook handler (which also powers RB2B / Swan ingest), reply classification, response drafts
- **Plan 3–4:** Trigify integration, Champify integration, cost-management auto-pauses, deliverability monitor, Cognism upgrade trigger
- **Plan 5–6:** client web app / Slack UX, expert knowledge library, deployment hardening

## Consequences

**Positive:**
- Productisable: every adapter is replaceable, every directory is a config file, zero per-client bespoke code
- Cost-efficient: Manus does the research work specialists charge $150+/mo for; ~$135–165/mo stack replaces a ~$400–600/mo Clay-centric alternative
- Quality-first: directory-first leads are higher-intent; tiered spend avoids wasting credits on low-intent contacts
- Compliance-first: jurisdiction-aware SMS/phone rules baked in before first send
- Extensible: L2A + L2B intent channels slot in as Plan 2+ additions with no schema change

**Negative / risks:**
- Manus availability / API reliability is a new production dependency — mitigate with fallback cascades at every stage
- Directory adapters (Clutch) are scraping logic that breaks when the target site's HTML changes — mitigate with schema-drift alerts + fast-iteration directory_spec YAML for the Manus-generic path
- LinkedIn account risk for Manus-authenticated research — mitigate with dedicated burner account + throttling + audit logging per `feedback_intent_signals`
- Tier thresholds (35/50/65/80) are initial guesses — will tune from decision_log outcomes quarterly per `feedback_improvement_backlog`

## Related
- `feedback_lead_sourcing` memory — directory-first preference with Clutch precedent
- `feedback_manus_ai_integration` memory — Manus as primary executor
- `feedback_enrichment_tiers` memory — score-gated tiers with phone ≥ 50
- `feedback_vendor_stack` memory — lean baseline + escalation triggers
- `feedback_intent_signals` memory — three-layer intent architecture
- `data/reference/sops/compliance/phone-sms-compliance.md` — legal workaround SOP
- Plan 1: `docs/superpowers/plans/2026-04-20-foundation-scout-migration.md` (amended with Tasks 3.6, 3.7 + reshapes of 9/10/12/14)
- Design spec: `docs/superpowers/specs/2026-04-20-aios-clymb-deployment-design.md`

## Review cadence
- Quarterly re-evaluation of vendor stack + tier thresholds against decision_log outcomes
- Immediate re-evaluation if any escalation trigger fires
