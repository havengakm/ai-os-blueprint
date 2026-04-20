# Decision: Lead-sourcing + enrichment architecture

**Date:** 2026-04-20
**Status:** Accepted (Amendment 2, same day)
**Decider:** Kirsten
**Drafted by:** Claude (AIOS agent) during Plan 1 execution
**Affects:** Plan 1 Tasks 9, 10, 12, 14 (reshape); new Tasks 3.6, 3.7, 3.8, 9.5 (client_config, settings, contacts columns, identity lookup); Plans 2/3/4 (downstream tool additions)

## Revision history

| Date | Amendment | Summary |
|---|---|---|
| 2026-04-20 (initial) | 1 | Original Manus-first + tiered-enrich architecture |
| 2026-04-20 (same day) | 2 | **Drop Manus**; Claude API replaces it as primary research executor. **Add Task 9.5 (Decision-Maker Discovery)** as a dedicated stage between pull and enrich (Apollo People Search → Hunter Domain Search → Claude scraper fallback). **Add 9 new `contacts` columns** (timezone, prospecting_method, buying_signals, key_pain_point, plus compliance audit + identity_source) via Task 3.8 migration. Remove `MANUS_API_KEY` from Settings. |

## Context

Plan 1 ported base-camp-agents' outbound pipeline, which defaults to Apollo as the primary lead source and uses generic email verification. During execution Kirsten flagged three shifts:

1. Apollo/ZoomInfo-style commodity databases are saturated — decision-makers on those lists are desensitised to cold outreach. Specialist directories (Clutch-for-agencies pattern, already proven in base-camp-agents) produce higher-intent, higher-response audiences at lower cost.
2. Manus AI is the preferred executor for scraping + research + enrichment wherever it can replace paid API credit burn.
3. Enrichment spend must be tiered by `icp_score` — no deep research or phone lookup on low-intent leads. Phone lookup hard-gated at score ≥ 50. No research/enrichment below score 35.

## Decision — one-sentence summary (Amendment 2)

**Scout's lead pipeline is a directory-first, Claude-API-driven architecture with a dedicated decision-maker discovery stage (Apollo + Hunter + Claude scraper waterfall), tiered waterfall enrichment pegged to `icp_score`, a lean vendor stack (Claude API + Apollo + Hunter + Lusha + ZeroBounce, ~$130–160/mo), jurisdiction-aware phone/SMS compliance, and 14 operator-facing `contacts` columns captured natively — with specialist tools (Cognism, Trigify, Champify, RB2B, Swan) added only when declared escalation triggers fire.**

## Architecture — in full

### Layer 1 — sourcing priority order (Amendment 2)

| # | Source | Mechanism | Cost |
|---|---|---|---|
| 1 | Specialist directories / associations | Dedicated Python adapter (Clutch pattern, ported from base-camp-agents) + generic `directory_scraper.py` driven by per-directory YAML spec; Claude API for structured HTML extraction | Claude API (batch Haiku) |
| 2 | Niche public sources (podcasts, conferences, team pages, Who's Who, regulatory registers) | Python scraper + Claude extraction + Tavily/Serper web search for discovery | Claude API + optional Tavily ~$5–10/mo |
| 3 | Apollo (commodity DB) for company-level search | Direct API adapter | Apollo subscription |
| 4 | CSV ingest | Upload + re-verify | — |

### Layer 2 — field-by-field waterfall (Amendment 2)

The waterfall now recognises **two distinct concerns**: (a) company-level data found by our scrapers + Claude research; (b) people-level identity + contact data found by purpose-built APIs. The new **Task 9.5 Identity Lookup stage** runs between pull and enrich and hard-fails contacts where no decision-maker resolves.

| Field | Primary | Secondary | Tertiary | Gate |
|---|---|---|---|---|
| Company name / website | Directory scraper | Claude-driven web search (Tavily/Serper) | Apollo company search | Always |
| Firmographics (industry / employees / revenue) | Apollo | Directory | Claude extraction from website | Always |
| First / last name + title (decision-maker) | **Apollo People Search** | **Hunter Domain Search** | Claude scraper (Playwright → LinkedIn company page, press, Crunchbase) | Always (hard-fail → archive if none resolves) |
| Work email | Apollo People Search (via identity lookup) | Hunter Domain Search | Pattern-match via verified domain | Always |
| Email verified | ZeroBounce | — | — | Pre-send mandatory |
| LinkedIn URL | Apollo People Search | Hunter | Claude scraper | Always |
| Mobile (SMS) | Lusha | Cognism (escalation) | Apollo Premium (US) | **`icp_score ≥ 50` HARD** |
| Timezone | Derived from location (pytz) | Manual inference | — | Always |
| Prospecting method + buying signals + key pain point | Claude research (Tier A/B/C only) | — | — | Research gate (`icp_score ≥ 50`) |

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

### Layer 4 — intent signals (three-tier, Amendment 2)

| Layer | Pattern | Tool | Plan |
|---|---|---|---|
| L1 research-time | Claude API one-shot per contact (hiring, funding, posts, job listings, trigger events) — Haiku batch, Sonnet complex | Anthropic SDK | **Plan 1** |
| L2A outbound target triggers | Continuous monitoring of our target list | Trigify.io | Plan 3–4 |
| L2B inbound visitor triggers | Continuous website visitor deanon | RB2B free → Swan AI | Plan 2+ |

L2A and L2B push webhooks → `activity_log` → re-score. Schema supports today; no Plan 1 changes.

### Layer 5 — vendor stack (lean baseline, Amendment 2)

| Role | Vendor | Cost |
|---|---|---|
| Scraping + research | **Claude API (Anthropic SDK)** — Haiku batch, Sonnet complex | API costs (already in stack) |
| Decision-maker identity (primary) | **Apollo People Search** (Basic → Pro) | $49–79/mo |
| Domain-wide email discovery (partner-firm case) | **Hunter.io Domain Search** | ~$34/mo |
| Mobile (SMS-enabled, gated ≥50) | **Lusha Team** | $29/mo |
| Email verification | **ZeroBounce** | ~$18/mo |

**All-in ~$130–160/mo** (excluding Claude API usage).

**Escalation triggers:**
- 5+ active clients OR heavy EU/UK/GDPR → add **Cognism** (compliance-grade mobile + DNC)
- US-mobile-heavy deployment → upgrade Apollo to Professional tier
- Specific directory blocks our scraper → add **ScraperAPI** (~$49/mo) or **Bright Data** (~$99/mo) — only when we hit blocks, not preemptive
- Warm-list re-engagement becomes the optimisation lever → add **Trigify**
- First content/landing pages driving traffic → add **RB2B free** (US) or **Swan AI** ($99–299)
- 2+ year customer base for job-change tracking → add **Champify**

**Rejected from the stack:**
- **Manus AI** — productisation loss (platform-locked tasks), cost (credits > Claude API for equivalent scrape), no unique capability we can't replicate with Python + Claude + targeted proxy subscription. Optional re-entry only if operator-facing ad-hoc UI becomes a recurring bottleneck.
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
| Cost per Tier A qualified lead | < $0.50 | Claude Haiku for batch, tier-gated enrich |
| Cost per Tier D touched lead | < $0.05 | Email + verify only |
| Decision-maker resolution rate | > 75% (Apollo + Hunter + Claude fallback) | Escalate if Apollo People Search miss rate > 30% |
| Bounce rate rolling 7-day (per inbox) | < 3% | ZeroBounce pre-gate + auto-pause |
| Opt-out rate weekly | < 2% | QA relevance gate |
| Claude API cost per 1k contacts researched | < $2.00 (Haiku batch) | Prompt tuning + re-eval if breached |
| Claude research hit rate (intent signal found) | > 60% Tier A/B | Prompt tuning cycle |

## Plan 1 impact — task-level changes

### New tasks (Amendment 2)
- **Task 3.6** ✅ — extend `client_config` with per-tier budgets + `active_directories` list + `weights` JSON (`003_client_config_extensions.sql`)
- **Task 3.7** ✅ — extend `Settings` + `.env.example` with `LUSHA_API_KEY`, `HUNTER_API_KEY`, `COGNISM_API_KEY`. (Initially added `MANUS_API_KEY`; **removed in Amendment 2 patch** since Claude API replaces Manus.)
- **Task 3.8 (NEW in Amendment 2)** — `004_contacts_extensions.sql` adding 9 new columns to `contacts`: `timezone`, `prospecting_method`, `buying_signals` JSONB, `key_pain_point`, `phone_source`, `phone_consent_basis`, `phone_found_at`, `sms_opted_out`, `identity_source`.
- **Task 9.5 (NEW in Amendment 2)** — Decision-Maker Discovery stage. New package `systems/scout/identity/` with `apollo_people.py`, `hunter_domain.py`, `claude_identity_scraper.py`, plus an orchestrator. Runs between Task 9 (pull) and Task 12 (enrich). Hard-fails contacts where no named decision-maker resolves (archives rather than passing to enrich) so no enrichment budget is wasted on un-contactable rows.

### Reshaped tasks (Amendment 2)
- **Task 9 `pull.py`** — `systems/scout/sources/` package: `clutch.py` (ported from base-camp-agents), `directory_scraper.py` (generic YAML-driven adapter + Claude API for HTML extraction), `apollo_company.py` (company-level search, NOT people), `csv_ingest.py`. Produces company-level contacts only; **no decision-maker data expected at this stage** (that's Task 9.5's job).
- **Task 10 `score.py`** — two-phase scoring: `score_v1()` post-pull, `score_v2()` post-enrich; weights read from `client_config.weights`; tier assignment on result. Reach category now includes "decision-maker identity resolved?" signal populated by Task 9.5.
- **Task 12 `enrich.py`** — `systems/scout/enrich/` package: **`claude_research.py`** (replaces any planned `manus_research.py`), `apollo_enrich.py`, `lusha.py`, `zerobounce.py`. Tier-gated orchestrator. Every blocked adapter call logs to `decision_log` with reason.
- **Task 14 research module** — **Claude-driven** (Anthropic SDK) with structured JSON output schema: company_summary, recent_events, tech_stack_signals, open_roles, hook_candidates, **prospecting_method**, **buying_signals**, **key_pain_point**, timezone, buying_intent_score. Output directly populates the 4 new operator-facing columns added in Task 3.8. **Rejection criteria built into the prompt**: no `info@` / `contact@` / `hello@` as valid primary email, no "Unknown" for decision-maker name, no "Available on website" for phone — explicit `null` + failure reason + attempted sources only.

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
- Cost-efficient: Claude API (Haiku batch) replaces Manus for research at lower cost and full ownership; ~$130–160/mo stack replaces a ~$400–600/mo Clay-centric alternative
- Quality-first: directory-first leads are higher-intent; tiered spend avoids wasting credits on low-intent contacts
- Compliance-first: jurisdiction-aware SMS/phone rules baked in before first send
- Extensible: L2A + L2B intent channels slot in as Plan 2+ additions with no schema change

**Negative / risks:**
- Claude API availability is a production dependency — mitigate with retries + circuit breakers at the adapter layer; fallbacks between Haiku and Sonnet if one model returns malformed output
- Directory adapters (Clutch) are scraping logic that breaks when the target site's HTML changes — mitigate with schema-drift alerts + fast-iteration YAML specs for the generic directory_scraper path + snapshot fixtures in unit tests
- LinkedIn access is handled via Apollo/Hunter APIs (not scraping) for identity; the Claude fallback scraper uses public profile views only and throttles to 1 visit / 15–30s. No burner-account management needed unless we add Sales Nav integration later.
- Tier thresholds (35/50/65/80) are initial guesses — will tune from decision_log outcomes quarterly per `feedback_improvement_backlog`

## Related
- `feedback_lead_sourcing` memory — directory-first preference with Clutch precedent
- `feedback_manus_ai_integration` memory — Manus considered + rejected; see `feedback_research_stack` for the Claude-based replacement
- `feedback_enrichment_tiers` memory — score-gated tiers with phone ≥ 50
- `feedback_vendor_stack` memory — lean baseline + escalation triggers
- `feedback_intent_signals` memory — three-layer intent architecture
- `data/reference/sops/compliance/phone-sms-compliance.md` — legal workaround SOP
- Plan 1: `docs/superpowers/plans/2026-04-20-foundation-scout-migration.md` (amended with Tasks 3.6, 3.7 + reshapes of 9/10/12/14)
- Design spec: `docs/superpowers/specs/2026-04-20-aios-clymb-deployment-design.md`

## Review cadence
- Quarterly re-evaluation of vendor stack + tier thresholds against decision_log outcomes
- Immediate re-evaluation if any escalation trigger fires
