# AIOS Blueprint — Clymb First Deployment Design

**Date:** 2026-04-20
**Owner:** Kirsten
**Scope:** Take Clymb live as the first instance of the AIOS Blueprint (May 1 pilot target), then onboard the first external paying client via the same template (June 15 target). Dates are targets, not commitments — quality gates decide.
**Status:** Design approved, pending implementation plan.

---

## Executive summary

Clymb Co. is the first deployment of the AIOS Blueprint. It becomes a full client instance — separate Supabase, separate Railway, forked blueprint — to dogfood the deployment SOP. The first system live is Scout (outbound prospecting), migrated from `base-camp-agents` into the blueprint's `BaseSystem` contract with full foundation integration (decision logging, autonomy gates, pattern matching, knowledge retrieval).

**The AIOS Blueprint is a productised service — not custom software.** Every client deployment is structurally identical. Customisation lives exclusively in context, data, brand, and pre-approved templates. Custom code per client is prohibited. This constraint is the business model, not a nice-to-have: the 72-hour sprint, the named products (AgencyOS, FractionalOS, AdvisoryOS), the $25K handover package, and the margin profile all require every deployment to be the same thing with different data.

The pilot tests a **3 niches × 3 offers matrix** via pre-approved templates with AI-filled placeholders, QA-gated per-message sending, and a four-phase autonomy ladder tied to QA agent calibration. The three niches — Digital Agencies, Fractional Executives, and Boutique Consulting — share Pipeline as their #1 research-validated pain, making Scout their natural entry offer.

Client-facing interface is a branded web app (Next.js + Supabase) with role-based operator and client views. Telegram is retained for Kirsten's internal operator flow only; Slack integration is roadmapped for post-W6. Cost management enforces tier-based monthly caps with three gates (70% soft alert / 90% hard alert / 100% auto-pause) and per-contact sub-budgets to prevent loop runaways (past incident: $900 SMS overage). A monthly margin review surfaces quality-parity efficiency, value expansion, and tier alignment recommendations — always leading with client value, never cost-cuts that degrade outcomes. A structured improvement backlog with five feedback sources and three cadences drives continuous AIOS evolution.

Every operational step is documented in a centralised SOP library (`data/reference/sops/`) to enable automation, delegation, and repeatable client deployment.

---

## Key decisions locked in

| # | Decision | Rationale |
|---|---|---|
| 1 | First deployment scope: full arc May 1 (Clymb pilot) → June 15 (first external client) | Proves OS end-to-end before selling it |
| 2 | Strict BaseSystem conformance from day one | Clymb pilot validates the whole OS loop |
| 3 | Full scope on launch: Scout + web app + reply handling + weekly report | Matches the 72-hour sprint promise |
| 4 | First external client sourced from Clymb's own outbound | Cleanest case study, proves the system sells the system |
| 5 | Approach 3 — hybrid, offer-test first (agencies), niche-test second (fractional, consulting) | No May 1 slip; what's ready ships first |
| 6 | Three niches: Agencies + Fractional Executives + Boutique Consulting | All three have Pipeline as #1 pain; DMCs deferred (their #1 pain is Proposals, wrong entry offer) |
| 7 | Templates are pre-approved human-written; AI fills placeholders only | Deliverability, brand, compliance, voice consistency |
| 8 | QA sub-agent validates every rendered message (outbound + inbound reply drafts) | Scales beyond per-message human review |
| 9 | Human approves templates, not individual sends | Volume does not permit per-send approval |
| 10 | Client-facing UX: web app (primary) + Slack (secondary, W6+), Telegram operator-only | Premium positioning, modern UX is the moat |
| 11 | Full isolation for Clymb (separate Supabase + Railway) | Dogfoods the deployment SOP |
| 12 | Separate named sending domains per niche (tryfractionalos.com, tryadvisoryos.com) | Matches strategy.md moat-building plan |
| 13 | Timeline flexibility — quality gates decide, not calendar dates | Don't ship broken systems; protect deliverability + guarantees |
| 14 | Cost caps enforced at 3 gates with auto-pause; per-contact sub-budgets | Past $900 SMS incident; protects rebilled-service margin |
| 15 | Monthly margin review: value-first efficiency, evidence before swaps | Never reduce value to cut cost |
| 16 | Improvement backlog with 5 sources, 3 cadences, outcome measurement | Makes "gets smarter every week" a repeatable process |
| 17 | **Productised service — same deployment for every client, customisation only in data** | Non-negotiable constraint from the business model; custom code per client destroys margin and SOP |
| 18 | Every offer scored against the 27-constraint offer framework; target 5/5 per constraint | Ties tactical iteration to structural quality; makes "no-brainer" measurable |
| 19 | Expert knowledge library expands across named authorities (Hormozi, Saraev, Brunson, Acosta, Walsh, Sapp) | Domain-specific RAG content is the moat over generic AI |

---

## Section 0 — Productisation principle (the non-negotiable constraint)

**The AIOS Blueprint IS the product. Clymb's deployment is the template every client deployment follows.**

### What's allowed to differ per client

- **Context** (`context/projects/{client}/`) — their company, strategy, ICP, metrics, operations, team, financials
- **Data** — call recordings, captures, knowledge loaded into their Supabase
- **Brand** (`context/brand/`) — logo, colors, fonts, voice rules
- **Pre-approved copywriting templates** — niche-specific + voice-specific, but structurally the same template engine
- **ICP definitions** — rows in `icp_definitions` table, not new code
- **Cost budgets and tier configuration** — rows in `cost_budgets`
- **Autonomy rules** — rows in `autonomy_rules`
- **Domain set** — their sending identities

### What's forbidden to differ per client

- Custom code per client
- Custom database schema per client
- Custom infrastructure topology per client
- One-off features built for a single client
- Client-specific branches with divergent logic
- Custom integrations requiring bespoke code

### The "can this be data?" rule

Every time a client asks for something "their way," the first question is: **can this be expressed as context, template, data, or config?**

- If yes: generalize it. Add it to the blueprint as a configurable capability that any client can enable. Then load the right data for this client.
- If no: add it to the blueprint as an optional feature controlled by config, feature-flagged off by default. Still not a client-specific fork.
- The answer is never: "we'll build this custom for this client only."

### Implications across this design

- **Web app is ONE codebase** serving all clients, differentiated by tenant/branding at runtime. Not fork-per-client.
- **SOP library enforces sameness.** Every deployment runs the same SOPs in the same order. The SOP is the productisation mechanism.
- **Template engine is shared.** Clients bring their own approved templates (data), but the rendering engine, placeholder system, and QA agent are identical.
- **Client forks stay current.** Because forks contain no divergent code, they can pull upstream blueprint updates safely.
- **Improvement backlog generalizes.** Any client-specific feature request gets generalized before build. "Feature X for client A" becomes "optional feature X for any client who configures it."
- **Red flag:** any code change that differs across clients triggers architectural review. The goal state is zero per-client code.

### How Clymb's deployment enforces the principle

Clymb is deployed using the same blueprint that the first external client will use. No exceptions. If something only works for Clymb, the blueprint is broken. If the 72-hour sprint requires custom code to finish, the SOP is broken. Clymb pays the price of being first — every gap it hits is a gap we fix in the blueprint before the external client arrives.

### What this means for every section that follows

All architectural choices, table schemas, infrastructure setups, SOPs, web app routes, API endpoints, and workflows in Sections 1-11 are blueprint-level artifacts. They apply verbatim to Clymb and to every future client. When reading any section, ask: "does this produce a different outcome for different clients only because of different data, not different code?" If yes, it's correct. If no, it's a productisation violation to be refactored.

---

## Section 1 — Four-layer architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 4 — SYSTEMS (pluggable, replaceable, revenue-producing)   │
│  Each one a "7-figure playbook" that plugs into the OS below.    │
│                                                                  │
│  Scout (outbound email)  ← built first (Clymb pilot)             │
│  LinkedIn Outreach       ← next, parallel channel                │
│  Beacon (inbound reply)  ← handles replies into bookings         │
│  Content OS              ← LinkedIn posts, authority             │
│  Ads                     ← paid amplification of winning offers  │
│  Reporting               ← weekly client intelligence brief      │
│                                                                  │
│  Every system: extends BaseSystem, reads from layers 1-3,        │
│  writes outcomes back, never acts without passing the gate.      │
│  Each will have its own revenue playbook + metrics (future).     │
└──────────────────────────────────────────────────────────────────┘
                             ▲   ▲   ▲   ▲
                             │   │   │   │     (read + write)
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 3 — DECISION LOOP (HOW THE OS LEARNS)                     │
│                                                                  │
│   Retrieve similar past decisions  (pattern_matcher)             │
│                   │                                              │
│                   ▼                                              │
│   Check autonomy gate              (autonomy)                    │
│                   │                                              │
│                   ▼                                              │
│   Act  (suggest / draft / act_notify / autonomous)               │
│                   │                                              │
│                   ▼                                              │
│   Log decision + reasoning         (decision_logger)             │
│                   │                                              │
│                   ▼                                              │
│   Observe outcome (reply / meeting / close / bounce)             │
│                   │                                              │
│                   ▼                                              │
│   Write outcome back to decision → loop closes                   │
│                                                                  │
│   Result: every send, every score, every copy variant becomes    │
│   training data for the next one.                                │
└──────────────────────────────────────────────────────────────────┘
                             ▲   ▲   ▲
                             │   │   │
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 2 — DATA (WHAT THE OS KNOWS — the IQ)                     │
│                                                                  │
│  • Expert knowledge (RAG, embeddings):                           │
│      Nick Saraev frameworks, copywriting patterns,               │
│      offer upgrade playbook, niche-specific research             │
│  • Past decisions + outcomes (decision_log + outcomes table)     │
│  • Captures (client call recordings, Slack, meeting notes)       │
│  • Performance data (campaign metrics, reply/meeting rates       │
│      segmented by niche × offer × variant × day × inbox)         │
│  • Market research (niche research, pain buckets, 21 offers)     │
│                                                                  │
│  Lives in: data/knowledge/, data/captures/, data/outputs/,       │
│            Supabase tables (with embeddings for retrieval)       │
└──────────────────────────────────────────────────────────────────┘
                             ▲   ▲
                             │   │
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 1 — CONTEXT (WHO THE OS WORKS FOR)                        │
│                                                                  │
│  personal.md · personal-operating.md · voice.md                  │
│  business-frameworks.md · integrations.md · brand/               │
│  projects/clymb/{company, strategy, icp, metrics, financials,    │
│                   operations, business-plan, team, research/}    │
│                                                                  │
│  Loaded once, embedded into Supabase, retrieved per task.        │
└──────────────────────────────────────────────────────────────────┘
```

**Gap assessment for Clymb pilot:**
- Layer 1 — mostly ready. Clymb context complete. Fractional + Consulting ICPs need adding.
- Layer 2 — knowledge embeddings not yet loaded. Performance tables (`campaigns`, `outcomes`) not created. **Expert knowledge library expansion pending** (see below).
- Layer 3 — code exists (`os/foundation/`) but outcomes writeback not yet wired. pattern_matcher untested on real data.
- Layer 4 — Scout is a stub. Needs full migration from `base-camp-agents/`.

### Expert knowledge library (Layer 2 expansion)

CLYMB's AIOS is only as good as the frameworks it retrieves. The knowledge library is a living corpus of domain-specific expert content, embedded into Supabase via pgvector for RAG retrieval. Every new system loads the relevant expert's frameworks before acting.

**Currently loaded (`data/knowledge/`):**
- `nick-saraev-cold-email.md` — cold outbound templates + patterns
- `nick-saraev-ai-positioning.md` — AI positioning + offer strategy
- `copywriting-frameworks.md` — general copywriting patterns

**Planned expansions (to be created in W2-3 alongside template work):**

| Domain | Authority | File | Used by |
|---|---|---|---|
| Offers + value equation | **Alex Hormozi** | `hormozi-offers.md` | Offer design, template writing, margin review, tier structure |
| LinkedIn content (authority frameworks) | **Lara Acosta** | `lara-acosta-linkedin.md` | Content OS (future), personal brand strategy |
| LinkedIn content (volume + distribution) | **Matt Walsh** | `matt-walsh-linkedin.md` | Content OS, engagement tactics |
| Funnel building | **Russell Brunson** | `brunson-funnels.md` | Value ladder, tripwire design, webinar structure (post-pilot) |
| High-ticket sales | **Shelby Sapp** | `shelby-sapp-sales.md` | Discovery call scripts, objection handling, close sequences |

Each file follows the format established by `nick-saraev-ai-positioning.md`: 5-10 named frameworks per authority, each with principle + how-to-apply + 1-2 examples. Embedded via `scripts/load_knowledge.py`.

**Productisation note:** expert knowledge is blueprint-level, not client-specific. Every client benefits from every added expert. New experts are added to the blueprint and propagate to all forks on next sync.

---

## Section 2 — 3×3 test matrix + copy architecture + two-gate approval

### The test matrix

| | Niche 1: Digital Agencies | Niche 2: Fractional Executives | Niche 3: Boutique Consulting |
|---|---|---|---|
| **Offer A** | cell A1 — pain-bucket #1 angle | A2 | A3 |
| **Offer B** | B1 — pain-bucket #2 angle | B2 | B3 |
| **Offer C** | C1 — Nick Saraev archetype | C2 | C3 |

Nine cells. Each is a `(campaign_id, niche, offer_variant)` tuple with its own contacts, own pre-approved template, own metrics.

**Why these three niches:** all three have Pipeline as their research-validated #1 pain (per `research/customer/pain-buckets-and-offers.md`). All three have Scout as the natural entry offer. This keeps the test clean — we're testing offer angles within a shared Scout thesis, not cross-mismatched systems. DMCs deferred (their #1 pain is Proposals, wrong entry system). M&A deferred (needs DealOS, a separate system).

### Offer score framework (every offer evaluated before launch)

Every template written, every offer pitched, and every new system built is scored against the 27-constraint scorecard from `data/reference/offer-upgrade-playbook.docx`. Target: 5/5 on every constraint (135/135 total). Baseline at design time: 110/135 (81%). Playbook target: 132/135 (98%).

**The 27 constraints (max 5 each):**

| # | Constraint | Current | Target |
|---|---|---|---|
| 1 | Clear moat / differentiators | 3 | 5 |
| 2 | Recession resilient | 4 | 5 |
| 3 | AI replacement protection | 2 | 4 |
| 4 | Strong brand potential | 4 | 5 |
| 5 | Simple repeatable ops | 4 | 5 |
| 6 | Untapped growth opportunities | 4 | 5 |
| 7 | MRR / subscription potential | 5 | 5 |
| 8 | Low customer concentration | 3 | 5 |
| 9 | Not geographically limited | 5 | 5 |
| 10 | Fun, freedom, fulfilment | 3 | 4 |
| 11 | Small lean team | 5 | 5 |
| 12 | Irreplaceably human element | 3 | 5 |
| 13 | Productised ecosystem | 3 | 5 |
| 14 | Fundamental need / real pain | 5 | 5 |
| 15 | Not bespoke / productised | 4 | 5 |
| 16 | Not hours for money | 4 | 5 |
| 17 | Not oversaturated | 3 | 5 |
| 18 | Profitable, scalable, realistic | 4 | 5 |
| 19 | Low capital, fast to start | 5 | 5 |
| 20 | Low barrier to entry | 4 | 5 |
| 21 | Not overly complex | 4 | 5 |
| 22 | Clone and iterate | 5 | 5 |
| 23 | Predictable cashflow | 4 | 5 |
| 24 | Asymmetric risk-reward | 5 | 5 |
| 25 | Dhandho framework | 5 | 5 |
| 26 | $30k+ monthly potential | 4 | 5 |
| 27 | Seven figure vision | 4 | 5 |

**The no-brainer test (secondary qualitative filter):**
1. ROI is obvious enough that saying no is irrational
2. Risk sits with Clymb, not the client
3. Walking away costs the client more than accepting

**Integration with the design:**

- `templates` table adds `offer_score` column (JSONB of per-constraint scores + total + last_reviewed_at)
- New templates scored by Kirsten before approval; templates scoring < 120/135 (89%) flagged for upgrade before launch
- Monthly margin review (Section 10) adds an offer-score trajectory panel: which constraints have moved, which are stuck
- Improvement backlog (Section 11) gains an `offer_quality` category — backlog items explicitly tagged with which constraints they move
- The nine upgrade areas from the playbook become permanent roadmap threads: build unbreakable moat, eliminate AI replacement risk, make human element irreplaceable, build productised ecosystem, eliminate commodity trap, make ROI undeniable, make guarantee bulletproof, price for value, accelerate speed to value

**Metric addition to Section 8:**
- **Offer score per template** (total + per-constraint breakdown)
- **Offer score trajectory** (monthly delta)
- **Constraint improvement velocity** — which constraints are improving fastest across the portfolio

### ICP definitions

Three, one per niche, stored in `icp_definitions` table:
- Industry codes, title filters, company size, geography, blacklist overrides, fit-score weightings
- `score_contacts.py` reads the right definition based on the contact's source/niche tag

### Domain allocation (sending infrastructure)

| Phase | Niche | Sending domains | Registration deadline | Warmup ready |
|---|---|---|---|---|
| May 1 | Agencies (AgencyOS) | `tryclymb.com` × 3 inboxes | done (warming since Apr 15) | Apr 28-30 |
| May 11 | Fractional (FractionalOS) | `tryfractionalos.com` + 1 variant × 3 inboxes each | **Apr 21** | May 5-12 |
| May 18 | Consulting (AdvisoryOS) | `tryadvisoryos.com` + 1 variant × 3 inboxes each | **Apr 27** | May 11-18 |

`tryclymb.com` reserved as Clymb's corporate identity (landing page, contact form), not a sending domain for niche outreach.

### Copy architecture

**Two-gate approval:**

```
HUMAN GATE (Kirsten) — LOW FREQUENCY, HIGH STAKES
  • New templates (v1) and version bumps
  • Campaign launches and kill/scale decisions
  • Positive-reply response drafts (until QA calibration proven)
  • QA agent rubric changes
  • Autonomy ladder promotions
  Volume: ~5-15 approvals/week
                    ▲
                    │ (escalations, weekly rollup)
QA AGENT GATE (AI, Haiku) — HIGH FREQUENCY, PER MESSAGE
  Runs on EVERY rendered draft before send.
  Runs on EVERY inbound-reply draft before send.
  Rubric checks: voice, factuality, relevance, completeness,
    truncation, grammar, tone, length, CTA, hallucinations.
  Retry guidance returned on fail.
  3 retries fail → escalate to Kirsten.
```

**Template structure** (pre-approved by Kirsten, immutable once approved):

```
---
template_id: agencyos_offer_a_v1
niche: agencies
offer: A — pipeline pain
version: 1
approved_by: kirsten
approved_at: 2026-04-24
---

Hey {{first_name_casual}},

{{icebreaker}}

{{bridge}}

Short version: we install AgencyOS — a system that fills your pipeline...
[rest of approved body, verbatim]

{{cta}}
```

**Placeholder types (all AI-filled, all logged as decisions):**

| Placeholder | AI task | Decision logged | Example |
|---|---|---|---|
| `{{first_name_casual}}` | Research name + casualise | `name_casualisation` | "Alexander" → "Alex" |
| `{{icebreaker}}` | Scrape LinkedIn/website, find specific reference | `icebreaker_research` | "Saw your post yesterday about churn on the $50K MRR plateau" |
| `{{bridge}}` | Connect icebreaker → offer grammatically + tonally | `bridge_rendering` | "That's basically what AgencyOS solves — from the top of funnel." |
| `{{cta}}` | Pick from approved CTA variants based on contact profile | `cta_selection` | "Open to a quick 15?" vs. "Happy to send a 2-min Loom" |

**AI never invents main body sentences.** The body is Kirsten's approved copy, verbatim. AI fills slots only.

### QA agent rubric

Runs on every rendered draft. Returns structured verdict:

```
{
  "pass": bool,
  "failures": [ {criterion, reason, severity} ],
  "confidence": float,
  "retry_guidance": str
}
```

Criteria:
1. Voice conformance (voice.md rules)
2. Icebreaker factuality (cited fact ∈ research_sources)
3. Icebreaker relevance (connects to offer naturally)
4. Placeholder completeness (no unfilled `{{ }}`)
5. Truncation check (no mid-sentence cuts)
6. Grammar + tone match
7. Length within template spec
8. CTA clarity
9. Hallucination absence (no claims outside template/research)

On failure: log reason → regenerate with retry_guidance → retry up to 3x → escalate if still failing.

### Progressive autonomy (tied to QA calibration)

| Phase | Outbound sends | Positive replies | QA calibration metric |
|---|---|---|---|
| 1 — launch | QA-approved → auto-send | Kirsten approves via web app | Kirsten spot-checks 20% for 2 weeks |
| 2 — ~week 3-4 | QA auto-send, 5% spot-check | Kirsten approves, QA surfaces suggestions | Agreement with spot-checks ≥ 90% |
| 3 — ~week 6-8 | QA auto-send, exception spot-check | Kirsten approves positive-reply drafts; routine acks auto-send after QA | Agreement ≥ 95% for 2 weeks |
| 4 — post-June 15 | Full autonomy on both | Strategic responses only | Sustained 95%+ + reply/bounce within targets |

**Three invariants across all phases:**
1. Template changes always require Kirsten's explicit approval.
2. QA agent runs on every single rendered message — outbound and inbound-reply — no exceptions.
3. Every QA verdict is a logged decision so pattern_matcher can learn which template + placeholder combinations trip QA most.

### Kill/scale thresholds (per cell)

| Metric | Threshold | Action |
|---|---|---|
| Reply rate after 300 sent | < 1% | kill_template recommendation |
| Reply rate after 300 sent | > 4% | scale_template recommendation |
| Bounce rate after 50 sent | > 2% | pause_template auto |
| Spam complaint rate after 100 sent | > 0.1% | pause_campaign auto |
| QA rejection rate sustained 3 days | > 15% | flag_template for review |

Every kill/scale/pause event is itself a decision logged with outcome tracking.

---

## Section 3 — Scout pipeline + BaseSystem conformance

### Pipeline stages

```
  Pull  →  Score  →  Screen  →  Enrich  →  Research  →  Render  →  QA  →  Send
                                                                           │
                                                                           ▼
                                                                  (Smartlead webhook)
                                                                           │
                                                                           ▼
                                                            Classify Reply  →  Draft Response  →  QA  →  Send / Escalate
```

| # | Stage | Module | Key decision type(s) | Autonomy-gated? |
|---|---|---|---|---|
| 1 | Pull | `pipeline/pull.py` | — (just data load) | no |
| 2 | Score | `pipeline/score.py` | `icp_threshold` | no (internal) |
| 3 | Screen | `pipeline/screen.py` | `screen_filter` | no (rule-based) |
| 4 | Enrich | `pipeline/enrich.py` | `enrichment_strategy` (provider + budget/contact) | no (internal) |
| 5 | Research | `outreach/research.py` | `research_strategy` (signals + sources for placeholders) | no (internal) |
| 6 | Render | `outreach/renderer.py` | `template_assignment`, `placeholder_fill` | no (internal) |
| 7 | QA | `outreach/qa_agent.py` | `qa_verdict` | **yes — mandatory gate** |
| 8 | Send | `outreach/send.py` | `send_timing` | **yes — `send_outbound` autonomy** |
| 9 | Classify | `inbound/classifier.py` | `reply_classification` | no (internal) |
| 10 | Respond | `inbound/responder.py` | `response_template_assignment`, `response_placeholder_fill`, QA verdict | **yes — `send_response` autonomy (stricter)** |

### BaseSystem conformance pattern

Every stage's `run_for_contact` method follows:

```python
async def run_for_contact(self, client_id: str, contact_id: str):
    # 1. MANDATORY — load foundation
    await self.load_foundation(client_id, task_query=f"stage:{self.stage_name}")

    # 2. Check past decisions via pattern_matcher
    past = await self.find_similar_decisions(
        client_id,
        decision_type=self.decision_type,
        current_context=contact_context,
    )

    # 3. Retrieve relevant knowledge
    knowledge = await self.retrieve_knowledge(client_id, query=self.stage_query)

    # 4. Check autonomy IF this stage acts externally
    if self.is_external:
        level = await self.check_autonomy(client_id, self.action_type)

    # 5. Do the stage's work
    result = await self._do_work(contact, past, knowledge)

    # 6. MANDATORY — log decision
    await self.log_decision(
        client_id=client_id,
        decision_type=self.decision_type,
        context={...},
        decision=result.decision,
        reasoning=result.reasoning,
        confidence=result.confidence,
    )

    return result
```

### Migration from base-camp-agents

| Source script | Destination | Migration type |
|---|---|---|
| `pull_leads.py` | `systems/scout/pipeline/pull.py` | wrap, add foundation calls |
| `score_contacts.py` | `systems/scout/pipeline/score.py` | wrap, add decision log |
| `screen_contacts.py` | `systems/scout/pipeline/screen.py` | wrap, add decision log |
| `enrich_contacts.py` + `verify_emails.py` | `systems/scout/pipeline/enrich.py` | merge, wrap, budget-gate |
| `generate_outreach.py` | **REPLACED** by `systems/scout/outreach/renderer.py` (new template architecture) | rewrite |
| `send_outreach.py` | `systems/scout/outreach/send.py` | wrap, add autonomy gate |
| `recycle_contacts.py` | `systems/scout/pipeline/recycle.py` | wrap |
| `weekly_report.py` | `systems/scout/reporting/weekly.py` | wrap, adapt to foundation |
| `analyze_performance.py` | `systems/scout/reporting/analyze.py` | wrap |
| `optimise_outreach.py` | becomes "AI flags conversion improvements" loop | rewrite around decision_log |
| `load_context.py` | `scripts/load_context.py` (deployment) | copy |
| `setup_client.sh` | `scripts/setup_client.sh` | copy, update for new structure |

### New modules (no migration source)

- `systems/scout/outreach/templates/` — markdown + YAML, 9 approved templates + CTA variants + response templates
- `systems/scout/outreach/research.py` — per-contact placeholder research
- `systems/scout/outreach/renderer.py` — template fill engine
- `systems/scout/outreach/qa_agent.py` — Haiku rubric runner + retry loop
- `systems/scout/inbound/classifier.py` — reply intent classification
- `systems/scout/inbound/responder.py` — response draft + QA + escalation

### Autonomy rule seeding (deployment)

```sql
INSERT INTO autonomy_rules (client_id, action_type, level) VALUES
  ('clymb', 'send_outbound',          'act_notify'),
  ('clymb', 'send_response',          'suggest'),
  ('clymb', 'apply_template_change',  'suggest'),
  ('clymb', 'kill_template',          'draft'),
  ('clymb', 'scale_template',         'draft'),
  ('clymb', 'icp_threshold',          'autonomous'),
  ('clymb', 'enrichment_strategy',    'autonomous'),
  ('clymb', 'research_strategy',      'autonomous'),
  ('clymb', 'placeholder_fill',       'autonomous'),
  ('clymb', 'reply_classification',   'autonomous');
```

Promotions follow CLAUDE.md rule: 50+ decisions, 80%+ success rate, 30+ days, explicit human approval.

### Triggers

Pipeline runs triggered by:
- Scheduler (nightly cron: pull → score → screen → enrich → research → render → QA → queue for send)
- API endpoint `/api/pipeline/trigger` (manual)
- Smartlead webhook `/api/webhooks/smartlead` (reply events → classify → respond)
- Web app commands (Kirsten's operator console)

---

## Section 4 — Client portal + operator console

**Two distinct interfaces, one backend:**

```
                     ┌─────────────────────────────────┐
                     │       FastAPI + Supabase        │
                     │   (one API, RBAC-enforced)      │
                     └─────────────────────────────────┘
                              │               │
                ┌─────────────┘               └────────────────┐
                ▼                                              ▼
   ┌─────────────────────────────┐           ┌─────────────────────────────┐
   │   CLIENT PORTAL             │           │   OPERATOR CONSOLE          │
   │   (web app, branded)        │           │   (same web app, role=op)   │
   │                             │           │                             │
   │   Next.js + shadcn/ui       │           │   Plus: Telegram fallback   │
   │   Hosted at                 │           │   for mobile-on-the-go      │
   │   app.tryclymb.com (or      │           │   push approvals            │
   │   per-client subdomains)    │           │                             │
   │                             │           │                             │
   │   Views:                    │           │   Views:                    │
   │   • Live pipeline           │           │   • All client pipelines    │
   │   • Today's drafts pending  │           │   • QA rejection queue      │
   │     their approval          │           │   • Template library +      │
   │   • Replies needing answer  │           │     version history         │
   │   • Meetings booked +       │           │   • Autonomy promotion      │
   │     prep briefs             │           │     controls                │
   │   • Weekly reports          │           │   • Performance by cell     │
   │   • Performance (their      │           │     across all clients      │
   │     niche, their campaigns) │           │   • Escalation feed         │
   │   • Strategy recommendations│           │   • SOP library + version   │
   │   • Improvement requests    │           │     log                     │
   │                             │           │   • Backlog management      │
   │   No: other clients' data.  │           │   • Monthly margin review   │
   │   No: Kirsten's operator    │           │                             │
   │   internals.                │           │   Alerts via Telegram +     │
   │                             │           │   web push                  │
   └─────────────────────────────┘           └─────────────────────────────┘
                ▲                                              ▲
                │                                              │
                └─────────── Slack integration ────────────────┘
                   (optional per client, mirrors key events;
                    postponed to W6)
```

### UX bar (the "good UX experience" requirement)

- **Dashboard-first.** Opens to "here's what's happening in your pipeline right now." Not settings.
- **One-click approvals.** Positive-reply responses as cards: prospect's reply on top, AI draft below, `approve` / `edit` / `reject` buttons.
- **Transparent AI decisions.** Every AI-drafted message shows `research_sources` ("I cited this LinkedIn post — [link]") so client can verify factuality.
- **Clean performance views.** Charts by niche × template × week. Reply rate, meeting rate, cost per meeting. Export to PDF.
- **Mobile-responsive.** Most approvals happen on the couch.
- **Branded per client.** `app.{clientname}.com` with client's logo + colors from `context/brand/`.

### Tech stack

- Next.js 14 (App Router) + TypeScript
- Supabase for auth + realtime subscriptions (drafts pushed live to UI)
- shadcn/ui + Tailwind
- Tanstack Query
- Recharts for performance charts
- Supabase Auth magic links (no passwords)
- Hosted on Vercel

### Webhooks + scheduler surface

**Webhooks:**
- `/api/webhooks/smartlead` (reply, bounce, open, click, unsubscribe, sent)
- `/api/webhooks/calendly` (meeting booked / cancelled / no-show / completed)
- `/api/webhooks/telegram` (operator bot callback)

All HMAC-verified. Idempotency keys on every event. Webhook failures still write events to DB; notifications retry from queue.

**Scheduler (Railway cron → HTTP):**

| Cron | Endpoint | Purpose |
|---|---|---|
| `0 2 * * *` | `POST /api/pipeline/nightly` | pull + score + screen + enrich overnight |
| `0 6 * * *` | `POST /api/pipeline/render-qa` | research + render + QA overnight batch |
| `*/15 9-17 * * 1-5` | `POST /api/pipeline/send-window` | send-window trickle |
| `0 8 * * 1` | `POST /api/reports/weekly` | weekly rollup |
| `0 8 * * *` | `POST /api/reports/digest` | daily digest |
| `0 * * * *` | `POST /api/pipeline/reconcile` | reconcile Smartlead events |
| `0 2 1 * *` | `POST /api/reports/margin-review` | monthly margin review |

Every cron hits a POST endpoint with `X-Cron-Secret` header for auth.

### Slack integration (postponed to W6)

- `/aios` slash command for quick approvals in-channel
- Webhook posts for: positive reply, meeting booked, weekly report summary, QA escalation
- Deep links back to web app for detail
- Per-client Slack workspace or shared Slack Connect channel

### Telegram scope

- Kirsten-only during early weeks (fast mobile push, tested)
- Becomes redundant once web app has push notifications (PWA install)
- Can be retired from the template after web app covers all her workflows

---

## Section 5 — Infrastructure + deployment

### Stack per deployment

```
┌─────────────────────────────────────────────────────────┐
│  Railway (one project per client)                       │
│    • FastAPI app (api/main.py)                          │
│    • Scheduler worker (Railway cron → HTTP trigger)     │
│    • Background queue for QA retries + send buffer      │
└─────────────────────────────────────────────────────────┘
                         │
      ┌──────────────────┼───────────────────┐
      ▼                  ▼                   ▼
┌────────────┐  ┌──────────────┐  ┌──────────────────┐
│  Supabase  │  │  Smartlead   │  │  Anthropic API   │
│  (client)  │  │  (client)    │  │  (client key)    │
│  Postgres  │  │  3 inboxes × │  │  Haiku: pipeline │
│  + pgvector│  │   3 niches   │  │  Sonnet: replies │
│  + RLS     │  │  warmup+API  │  │                  │
│  + auth    │  │  + webhooks  │  │                  │
└────────────┘  └──────────────┘  └──────────────────┘
      │
      ▼
External services (cheap/free):
 Anymail Finder + ZeroBounce (enrichment, rebilled 2.5×)
 Voyage AI (embeddings, shared Kirsten key)
 Cloudflare DNS (free)
 Zoho Mail (per sending domain)
 Calendly, Telegram
```

**Clymb gets full isolation** (separate Supabase + Railway) so it's treated like a real client and dogfoods the deployment SOP.

### Database schema additions beyond `001_foundation.sql`

New migration `scripts/sql/002_scout.sql`:

| Table | Purpose |
|---|---|
| `contacts` | leads with niche + campaign_id + scoring tier + status |
| `icp_definitions` | per-niche ICP rules (industry, titles, size, geo, blacklist) |
| `client_config` | per-client Scout config (sending windows, daily caps, target cells) |
| `campaigns` | `(client_id, niche, template_id, status)` — one per test cell |
| `templates` | versioned templates (niche, offer, approved_by, approved_at, status) |
| `outreach_drafts` | rendered drafts + QA verdict + status |
| `outreach_sent` | sent log (smartlead_message_id, sent_at, inbox, campaign_id) |
| `activity_log` | opens, clicks, replies, bounces, unsubs — raw event stream |
| `replies` | normalised reply events + classification + response_draft_id |
| `response_drafts` | AI-drafted replies + QA verdict + approval state |
| `meetings` | Calendly events (booked, completed, no-show) |
| `qa_runs` | per-message QA verdicts (draft_id, rubric_version, verdict, failures, confidence) |
| `outcomes` | materialised view joining decisions → outcomes |
| `cost_budgets` | per-(client, service, period) soft/hard/pause thresholds |
| `cost_events` | append-only log of every chargeable operation |
| `cost_alerts` | alerts fired, acknowledged state, escalation path |
| `overage_approvals` | client-approved overages with amount, expiry, signed_at |
| `tier_limits` | default budgets per tier (seed data) |
| `improvement_backlog` | improvement tracking (source, status, scores, outcomes) |

Every table carries `client_id`. RLS enforces isolation per client.

### `.env.example` template (new in `config/`)

```bash
# === Client identity ===
CLIENT_ID=clymb
CLIENT_DISPLAY_NAME="CLYMB Co."

# === Database ===
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ANON_KEY=

# === AI ===
ANTHROPIC_API_KEY=
VOYAGE_API_KEY=

# === Email sending ===
SMARTLEAD_API_KEY=
SMARTLEAD_WEBHOOK_SECRET=

# === Enrichment (rebilled 2.5× to client) ===
ANYMAIL_FINDER_API_KEY=
ZEROBOUNCE_API_KEY=

# === Communication ===
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_CHAT_ID=
CALENDLY_WEBHOOK_SECRET=

# === Internal ===
CRON_SECRET=
API_PUBLIC_URL=
LOG_LEVEL=INFO
```

### Repo structure additions

```
api/
├── __init__.py
├── main.py                    # FastAPI app, mounts routers
├── deps.py                    # auth, DB session, system registry wiring
├── routers/
│   ├── pipeline.py            # /api/pipeline/*
│   ├── webhooks.py            # /api/webhooks/smartlead|calendly|telegram
│   └── reports.py             # /api/reports/*
└── middleware/
    └── verify_signatures.py   # HMAC verify for webhooks

config/
├── .env.example
├── railway.toml               # migrated from base-camp-agents
├── Procfile                   # migrated
└── pyproject.toml             # migrated + updated deps

scripts/
├── setup_client.sh            # migrated from base-camp-agents
├── load_context.py            # migrated
├── load_knowledge.py          # new (embeds data/knowledge/*)
├── seed_autonomy_rules.py     # new
├── seed_cost_budgets.py       # new
└── sql/
    ├── 001_foundation.sql     # exists
    └── 002_scout.sql          # new

web-app/                       # new repo or subdirectory
├── app/                       # Next.js App Router
├── components/                # shadcn/ui based
├── lib/                       # Supabase client, types
└── README.md

systems/scout/                 # expanded from stub
├── skill.py                   # existing, routes messages
├── sql/
│   └── migrations.sql         # symlink to scripts/sql/002_scout.sql
├── pipeline/
│   ├── pull.py
│   ├── score.py
│   ├── screen.py
│   ├── enrich.py
│   └── recycle.py
├── outreach/
│   ├── templates/             # 9 approved + CTA variants + response templates
│   ├── research.py
│   ├── renderer.py
│   ├── qa_agent.py
│   └── send.py
├── inbound/
│   ├── classifier.py
│   └── responder.py
└── reporting/
    ├── weekly.py
    ├── analyze.py
    └── margin_review.py       # new in W5-6

data/reference/sops/           # SOP library (see dedicated section below)
```

### Deployment SOP update (after migration)

`data/reference/client-deployment-sop.md` needs updates:
1. Step 6 — `load_context.py` + `load_knowledge.py` now exist in blueprint
2. Step 8 — add `seed_autonomy_rules.py` as a step
3. Step 8b (new) — `seed_cost_budgets.py` based on client's tier
4. Step 9 — replace script names with new paths
5. Step 11 — QA agent calibration sampling setup (first 2 weeks: 20% spot-check, then 5%)
6. Step 12 — verify budget caps live via synthetic test charge

---

## Section 6 — Timeline (quality-gated, date-flexible)

**Operating principle:** dates are targets. Gates decide. When a gate fails, the delay is the right call.

### Week 1 (Apr 20-26) — Foundation + infra + domains

| Workstream | Deliverable |
|---|---|
| Design + planning | Spec committed, plan written, SOP library scaffolded |
| Domains | Clymb's own Supabase + Railway provisioned. `tryfractionalos.com` + variants registered (Apr 21). |
| Migration | `pull.py`, `score.py`, `screen.py`, `enrich.py` migrated + BaseSystem-wrapped. SOPs written alongside. |
| Send | `send.py` migrated, Smartlead API integrated (dry-run only). |
| Templates | Kirsten writes 3 Agencies templates. Approved into DB. Template-writing SOP committed. |

**Exit criteria:** Pipeline can take a contact from DB → rendered draft (no QA yet, no send). Foundation integration in place. Agencies templates approved.

### Week 2 (Apr 27-May 3) — QA agent + webhooks + agencies launch

| Workstream | Deliverable |
|---|---|
| Domains | `tryadvisoryos.com` + variants registered (Apr 27). Fractional domains in warmup week 2. |
| QA agent | `qa_agent.py` built with Haiku + rubric. Calibrated against 100 Kirsten-labelled samples. |
| Retry + escalate | Retry loop + 3-fail escalation wired up |
| Web app MVP | Next.js scaffold, Supabase auth, operator view with pipeline + QA queue + template library |
| Inbound | `classifier.py` + `responder.py` for replies. Full webhook flow functional. |
| **Apr 30 — G1 gate** | End-to-end dry run: 10 contacts → QA ≥8/10 pass → Kirsten approves |
| **Fri May 1** | **🚀 AGENCIES LAUNCH** — 50 emails/day on 3 offer variants via tryclymb.com |

### Week 3 (May 4-10) — Calibrate + Fractional prep + web app v1

- Agencies running; daily digest in web app; QA rubric tuned from real Kirsten spot-checks
- Scrape Fractional data (2K+ contacts); build Fractional ICP; Kirsten writes 3 Fractional templates by Fri
- Web app v1: performance dashboard, template management, approval queue, reply inbox
- Pipeline SOPs + QA-calibration SOP committed
- First agencies replies likely → test inbound classifier + responder live

### Week 4 (May 11-17) — Fractional launch + Consulting prep

- **G2 gate (May 10):** Fractional templates + domains + data
- If G2 passes: **🚀 Fractional launches** — 30/day ramping to 50 on tryfractionalos.com
- Web app v1.1: client-facing views + per-campaign metrics + meeting prep briefs
- First agency meetings likely this week
- Consulting prep (scrape, ICP, 3 templates)

### Week 5 (May 18-24) — Consulting launch + first analytics + close kit start

- **G3 gate (May 17):** Consulting ready
- If G3 passes: **🚀 Consulting launches** — full 3×3 matrix active
- First analysis run (Fri May 22): performance per cell, first kill/scale recommendations
- QA calibration at ~95% → Phase 3 autonomy (spot-check on exception only)
- Start building `margin_review.py`

### Week 6 (May 25-31) — Double down + close kit + Slack integration

- Scale winners, kill losers
- Close kit: proposal generator, Stripe invoicing, MSA/DPA/SLA contracts
- Web app v1.2: client portal branding polish, Slack integration prototype
- First discovery calls possible; first positive reply → first meeting → first pitch could land

### Week 7 (Jun 1-7) — Harden blueprint for fork

- First monthly margin review runs June 1 (Clymb is the first "client" reviewed)
- Document gaps Clymb's pilot exposed → update every affected SOP
- Deployment SOP dry-run against a fresh fork (by Kirsten or VA) to test repeatability
- Record walkthrough videos per deployment SOP stage
- `scripts/setup_client.sh` tested end-to-end against a fresh fork

### Week 8 (Jun 8-14) — Close + first external onboarding

- **G4 gate (Jun 10):** Deployment SOP dry-run <4hrs, close kit proven, at least one signed LOI/contract
- If G4 passes: **🚀 First external client's 72-hour sprint** on day-of-signature
  - Day 0: onboarding call, context gathered
  - Day 1: blueprint forked, Supabase + Railway provisioned, 2K+ leads pulled
  - Day 2: templates approved (reusing Clymb's winning offers with client voice adjustments)
  - Day 3: first emails sent

### Critical path + parallel tracks

```
CRITICAL PATH:
  Infra deploy → Scout migration → Template system → QA agent →
  Send + webhooks → Go/No-Go gate → Agencies launch

PARALLEL TRACK A (Templates — Kirsten writes, doesn't block engineering):
  W1: Agencies × 3  →  W3: Fractional × 3  →  W4: Consulting × 3

PARALLEL TRACK B (Domains + data):
  W1: Register fractional + advisory domains
  W1-2: Warmup
  W3: Scrape fractional data
  W4: Scrape consulting data

PARALLEL TRACK C (post-W5): Close kit
PARALLEL TRACK D (post-W6): Deployment SOP hardening for fork
PARALLEL TRACK E (post-W4): Margin review + improvement backlog systems
```

### Go/No-Go gates

| Gate | Target date | Criterion | Fallback |
|---|---|---|---|
| **G1: Agencies ready** | Apr 30 | 10-contact dry run ≥8/10 QA pass on first try; web app MVP operational | Reduce volume to 10/day, shadow-mode QA, delay 3-7 days |
| **G2: Fractional ready** | May 10 | Templates approved, domains warmed, data enriched | Delay to May 15-20 |
| **G3: Consulting ready** | May 17 | Same as G2 | Delay; sequence behind stronger-performing niche |
| **G4: Blueprint fork-ready** | Jun 10 | Deployment SOP dry-run <4hrs; close kit proven; contracts ready | Push first external to Jun 22 |

### Risk call-outs (no sugar-coating)

- W1-W2 scope is aggressive. If anything slips, May 1 becomes May 3-5. Fallback (reduced-volume + shadow QA) is honestly a cleaner debut than full-volume day one.
- "First external client by Jun 15" depends on at least one agencies reply converting by end of May. Can't manufacture a sales cycle on an empty pipeline.
- QA agent is the riskiest unknown. Calibration harness in W1 lets us fail fast on this specific risk.
- Domain warmup is tight. Fractional domains must be registered Apr 21.

---

## Section 7 — Error handling, autonomy promotion, testing

### Error handling matrix

| Failure mode | Detection | Response |
|---|---|---|
| Smartlead API down | HTTP 5xx / timeout | Retry w/ exponential backoff → after 3 fails, pause send queue, alert Kirsten |
| Supabase connection failure | Connection error | Circuit-break, queue writes locally, retry every 30s |
| Anthropic API rate limit | HTTP 429 | Exponential backoff, prioritise QA over render if quota tight |
| QA agent returns invalid JSON | Parse fail | Treat as QA fail, log, retry with stricter prompt format |
| Webhook signature mismatch | HMAC fail | Reject with 401, log, alert after 5 in an hour |
| Scout draft 3-retry failure | retry counter | Escalate to Kirsten via web app |
| Calendly webhook missing | cron reconciler hourly | Back-fill from Calendly API, alert if gap > 24h |
| Three QA failures on same draft | retry counter | Per CLAUDE.md — stops retrying, notifies Kirsten |
| Cost budget breach | budget gate | Auto-pause service, notify Kirsten + client, require overage approval |

### Hard rules from CLAUDE.md (always apply)

1. Three QA failures on anything = escalate, don't retry forever
2. Never contact opted-out contacts — enforced at DB level via screen.py + RLS
3. Every outreach fact must exist in `research_sources` — enforced at QA gate

### Autonomy promotion thresholds

Promotion from one level to the next requires ALL of:

1. 50+ decisions at current level for the `action_type`
2. ≥ 80% success rate (per CLAUDE.md)
3. ≥ 30 days at current level
4. Explicit Kirsten approval via web app
5. For `send_outbound`: QA agreement rate ≥ 95% over rolling 2 weeks

Promotions are one-level jumps. Quarterly autonomy review SOP triggers the conversation.

### Testing approach

| Layer | Tests | Who writes |
|---|---|---|
| Foundation modules | Unit tests (pytest), mocked Supabase | migration |
| Each pipeline stage | Unit + integration tests against local Supabase | migration |
| QA agent | Calibration harness: 100 labelled samples, measure agreement | QA agent build |
| Renderer | Template golden files | renderer build |
| End-to-end Scout | Full pipeline dry-run on 10 real contacts, `dry_run=true` | G1 requirement |
| Web app | Playwright smoke tests | web app build |
| Webhooks | Signature verification + replay tests | webhook build |
| Deployment | Fresh-fork dry-run per SOP — must complete <4hrs | G4 requirement |

### Observability

- Structured logging (JSON) for every decision, send, QA verdict, webhook event
- Daily digest materialised from logs
- Weekly rollup materialised view
- Sentry (or similar) for unhandled exceptions
- Supabase query performance dashboards

### Security

- Every webhook endpoint HMAC-verified
- Every admin endpoint behind Supabase Auth role check
- RLS policies on every table; `client_id` derived from authenticated session
- API keys never in source, always `.env` → Railway env vars → Supabase vault
- Client data fully isolated (separate Supabase per client)

---

## Section 8 — Metrics framework

**North star:** qualified meetings booked per client per month.

### Funnel metrics

**Stage 1 — Pipeline quality (pre-send):** lead volume, enrichment success rate, ICP tier distribution, cost per verified contact, cost per A-tier.

**Stage 2 — Deliverability:** open rate, bounce rate (pause at 2%), spam complaint rate (pause at 0.1%), unsubscribe rate, inbox placement rate, domain reputation score, warmup status, sending cap utilisation.

**Stage 3 — Engagement:** total reply rate, positive reply rate (scale at 4%+), negative reply rate, objection rate, Loom watch rate, Loom completion rate, follow-up engagement by sequence position, reply-time distribution (p50/p90).

**Stage 4 — Conversion:** reply → meeting booked rate, meeting booking rate end-to-end, meeting show rate, no-show rate, cancellation rate, reschedule rate, meeting → proposal rate, proposal → close rate, close rate end-to-end.

**Stage 5 — Speed:** speed to lead, time to meeting, time to close, QA latency, retry turnaround.

**Stage 6 — Retention + LTV:** churn rate (monthly, annual), gross revenue retention, net revenue retention, average client lifetime, LTV, expansion revenue, revenue per niche, revenue per system.

### System quality metrics

QA rejection rate first-try (flag at 15%+), QA retry success rate, QA escalation rate, QA agent agreement rate with Kirsten (95% autonomy gate), decision volume, pattern match hit rate, autonomy level distribution, template lifecycle velocity, time from signal to action.

### Financial / unit economics

CAC, LTV:CAC ratio (target ≥ 3:1), payback period, ARPU, MRR growth rate, gross margin per client, tier mix, revenue attribution by source.

### Operational / SLA

Client response SLA (4hr business-hour), weekly report delivery rate, incident rate, first-week retention, client health score, client NPS, 72-hour sprint success rate.

### Composite / derived metrics

- **Cost per qualified meeting (CPQM)** — total cost / meetings booked
- **Cost per closed deal** — total cost / deals closed
- **Funnel efficiency** — sent → close rate
- **Niche ROI** — revenue(niche) / cost(niche)
- **Template ROI** — revenue_attributed(template) / cost(template)
- **Client health score** — composite of engagement + results + NPS - churn_risk
- **OS maturity score** — composite of autonomy_distribution + qa_agreement + decision_volume + pattern_hit_rate

### Dashboard rollout

**Day 1 (W2-W3 MVP):**
- Deliverability by cell
- Reply rates (total, positive, negative) by cell
- QA rejection rate by template
- Today's approvals queue
- Pipeline volume counters
- Warmup / domain health

**Day 1 alerts:** bounce >2%, spam >0.1%, QA rejection >15%, new positive reply.

**W3-4 additions:** meeting funnel, Loom metrics, follow-up engagement, cost per verified contact.

**W5-6 additions:** conversion chain, time-to-close, revenue attribution, CPQM.

**Post first external:** CAC, LTV, LTV:CAC, churn, niche ROI, client health score, OS maturity score.

### Implementation approach

- Event sourcing at data layer (every send, open, click, reply, meeting, invoice is a row)
- Materialised views for expensive aggregations (daily per-cell, weekly per-niche, monthly financial)
- Real-time subscriptions for critical-few (bounce, spam, QA rejection)
- Kirsten's spot-check sampling: web app serves random drafts, captures verdict, auto-computes agreement weekly

---

## Section 9 — Cost management + margin protection

### Cost categories

| Category | Examples | Who pays | Margin risk |
|---|---|---|---|
| Client-paid (direct) | Anthropic API, Supabase, Smartlead, Zoho, Railway | Client's own keys | Low |
| Clymb-absorbed / rebilled 2.5× | Twilio SMS, Anymail Finder, ZeroBounce, Voyage AI | Clymb → rebill | **HIGH** |
| Clymb-only | Shared tools, monitoring | Clymb | Small but constant |

### Tier-based monthly cap defaults (USD)

| Service | Founding | Standard | Growth | Premium |
|---|---|---|---|---|
| AI tokens (total) | $50 | $150 | $400 | $1,000 |
| Emails (Smartlead) | included | included | included | included |
| SMS (Twilio) | $50 | $150 | $400 | $1,000 |
| Enrichment (Anymail Finder) | $100 | $300 | $800 | $2,000 |
| Verification (ZeroBounce) | $30 | $80 | $200 | $500 |
| Embeddings (Voyage) | $10 | $30 | $80 | $200 |
| **Total absorbed monthly cap** | $240 | $710 | $1,880 | $4,700 |

Stored in `cost_budgets` per client — adjustable without code changes.

### Three gates per service per period

- **70% → soft alert** (Kirsten web app notification)
- **90% → hard alert** (Kirsten + client email + web app)
- **100% → auto-pause** (halted until monthly rollover OR explicit overage approval)

### Per-contact and per-action sub-budgets (prevent loop runaways)

| Constraint | Limit |
|---|---|
| SMS per contact per day | 1 |
| SMS per contact per 7 days | 3 |
| Enrichment cost per contact | $0.05 max |
| Verification cost per contact | $0.01 max |
| AI tokens per render | ~$0.01 target |
| AI tokens per QA run | ~$0.005 target |
| AI tokens per response draft | ~$0.02 max |
| Total AI cost per contact (full pipeline) | $0.30 max |

Every chargeable call site runs `check_budget(client_id, service, amount, contact_id)` before executing. Failure aborts operation and logs `decision_type="budget_blocked"`.

### Overage workflow

1. Client (or Kirsten) requests overage via web app
2. Request specifies service, additional amount, reason
3. System shows cost including 2.5× markup + projected end-of-month total
4. Client confirms in writing (signed timestamp)
5. `overage_approvals` row created with temporary expanded cap + expiry
6. Alert fires 24h before overage expiry

### Tier-upgrade triggers

- 3 of last 4 weeks ≥ 80% on any service cap
- Overage approved 2+ times in a quarter
- Expansion pushes past tier's total absorbed cap

Upgrade recommendations surface in Kirsten's Monday rollup and the client's web app (framed as value, not pressure).

### Dashboard additions

**Operator — cost dashboard per client:** today's spend vs cap, MTD vs cap with pace line, top 5 cost drivers this week, overage approval queue, tier-upgrade recommendations.

**Client view — transparent cost panel:** their usage in plain language, tier allowance remaining, projected month-end, upgrade CTA when warranted.

### Integration with Scout pipeline

Each pipeline stage wraps chargeable calls in `check_budget()`:

| Stage | Chargeable operations | Gate |
|---|---|---|
| Enrich | Anymail Finder, ZeroBounce | before each call |
| Research | Scraping + LLM signals | before research run |
| Render | LLM placeholder fills | before render |
| QA | Haiku rubric | before run |
| Send | Smartlead (client-paid, tracked) | before dispatch |
| Respond | Sonnet reply draft | before draft |
| Future LinkedIn SMS/DMs | Twilio SMS | hard-gated |

### Metrics additions

Cost per client per service, absorbed cost per client, margin per client, cost per verified contact, cost per meeting (CPM), cost per closed deal, % clients within cap, % clients on suitable tier, overage frequency, runaway prevention rate.

---

## Section 10 — Monthly margin review (value-first efficiency engine)

**Mandate:** improve margin while maintaining or growing client-experienced value. Never cost-cuts that degrade outcomes.

### Decision hierarchy

```
1. Quality-parity efficiency     ← preferred: same value, less cost
2. Value expansion                ← more value, justified cost
3. Tier alignment (upgrade)       ← usage outgrew tier
4. Configuration tightening       ← minor waste removal
5. Service reduction              ← last resort, client sign-off required
```

### Recommendation types

**Type 1 — Quality-parity efficiency:** route classification to Haiku if 97%+ agreement with Sonnet; enable Anthropic prompt caching on rubric; batch overnight enrichment; deduplicate enrichment calls; switch to cheaper model variant on new release with parity.

**Type 2 — Value expansion:** add LinkedIn Outreach when engagement signals warrant; add Beacon when inbound volume grows; add Reporting when ad-hoc requests rise; upgrade to Premium with exclusivity benefit.

**Type 3 — Tier alignment:** upgrade conversations triggered by 3 of last 4 weeks ≥ 80% on any cap; multi-system usage on Starter; repeated overages.

**Type 4 — Configuration tightening:** lower send caps on cells that never hit them; retire killed templates from research context; expire stale prospects; consolidate Railway replicas.

**Type 5 — Service reduction** (last resort, client approval): drop unused domains; restrict verification to higher tiers.

### Monthly review workflow

Runs 1st of month per client:

1. Pull last month's cost_events, outcomes, decisions
2. Compute absorbed cost, margin, CPM, quality metrics per model/service, tier fit
3. `margin_review.py` analyzes + surfaces candidate recs across all 5 types
4. For efficiency recs requiring evidence: check threshold met, else propose A/B test
5. For expansion recs: check usage signals, estimate revenue impact + confidence
6. Rank by (expected margin Δ × confidence - value risk), pick top 3-5
7. Generate report with trade-off math
8. Web app presents to Kirsten with apply / A/B test / reject / defer buttons

Applied changes get experiment tracking (pre/post state), auto-rollback trigger if quality drops >10% in 7 days, outcome logged to decision_log, pattern_matcher learns.

### Evidence thresholds

| Change category | Evidence required |
|---|---|
| Model swap on any task | ≥ 500 side-by-side samples, ≥ 95% agreement |
| Vendor swap | ≥ 1,000-contact head-to-head, outcome parity |
| Prompt trim | A/B with quality regression test |
| Routing rule change | Shadow mode 1 week |
| Batch vs real-time | Confirm SLA still met |

### Protection against runaway optimization

1. Auto-rollback if quality metric drops > 10% vs baseline within 7 days
2. Max 1 Type-1 efficiency change per week per client (prevents masking effects)
3. Client-visible changes require client notification before, not after

### Hard-coded safety invariant

```python
# margin_review.py — final filter
def filter_recommendations(recs: list[Recommendation]) -> list[Recommendation]:
    filtered = []
    for rec in recs:
        if rec.client_value_delta < 0 and rec.type != "client_approved_reduction":
            continue
        filtered.append(rec)
    return filtered
```

### Metrics additions

Margin per client (monthly), margin trajectory (3-month rolling), CPM trend, quality-adjusted cost, model routing distribution, efficiency recommendations applied, rec success rate, auto-rollback rate, tier upgrade conversion.

### Timeline

- Build in W5-6 (after 4-6 weeks of Clymb data)
- First review runs June 1 against Clymb's own data
- Available for first external client by July 1
- SOP: `data/reference/sops/client-management/monthly-margin-review.md`

---

## Section 11 — Continuous improvement backlog

**Mandate:** every piece of feedback flows into a structured backlog. Triage, prioritize, build, measure.

### Five sources

| Source | Capture path |
|---|---|
| Client-stated | Web app "Request improvement" button; NPS surveys; call notes tagged `feedback` |
| Client-observed | Web app telemetry (bounces, unused features, repeated errors) |
| Operator-observed | Kirsten's Friday review SOP; `/feedback` Telegram command |
| System-surfaced | `pattern_matcher` monthly auto-generation |
| Strategic | Quarterly business planning |

### Data model (`improvement_backlog` table)

Fields: id, title, description, source, source_detail, category, scope, affected_systems, impact_score (1-10), confidence_score (1-10), ease_score (1-10), rice_score (computed), status, requested_by, timestamps for each lifecycle stage, plan_ref, target_metric, target_delta, outcome_measured, outcome_success, blocking_dependencies, tags.

### Three cadences

**Weekly triage (15-30 min, Friday review):** categorize new items, de-duplicate, apply rough scores, move new → triaged.

**Monthly prioritization (60 min, aligned with margin review):** refine scores with latest data, pick top 10 for build queue, surface 2-3 strategic themes.

**Quarterly roadmap (half-day, aligned with autonomy review):** review shipped outcomes, identify failed improvements + why, plan next quarter's themes, commit to major initiatives.

### Triage invariant

Every backlog item must have a `target_metric`. If no metric: bounced back with "what success looks like before we build."

### Build loop

```
triaged → prioritised → planned (writing-plans) → in_build → shipped → measuring (30-day) → closed
```

Non-trivial items (3+ steps) go through `superpowers:writing-plans` before in_build. Plans archived to `data/plans/archive/{item_id}.md`.

### Outcome measurement (closing the loop)

30 days after ship: query target_metric before/after, compute actual delta. If ≥ 80% of target: `outcome_success = true`. Pattern_matcher learns which category + scope + source combos produce successes. Future prioritization biases toward high-success categories.

### Web app surface

**Operator:** inbox for new items, Kanban by status, priority matrix (impact vs ease), monthly dashboard, quarterly planner, pattern view of rec success rates.

**Client view:** "Requested" tab with their open requests + ETA, "What's new this month" with shipped improvements affecting them, "Request an improvement" structured form, no other clients' requests.

### SOPs

- `client-management/capture-client-feedback.md`
- `client-management/weekly-backlog-triage.md`
- `client-management/monthly-prioritization.md`
- `client-management/quarterly-roadmap-planning.md`
- `pipeline/system-surfaced-recommendations.md`
- `pipeline/outcome-measurement.md`

### Meta-metrics

Backlog intake rate, triage latency (target ≤ 7 days), ship rate per month, outcome success rate, time-to-ship by category, client-sourced ship rate, system-sourced ship rate, quarterly learning velocity.

### Timeline

- W2-3: `improvement_backlog` table + basic RLS, web app capture form, weekly triage SOP
- W5-6: Full operator view (Kanban, priority matrix), monthly prioritization flow, `/feedback` Telegram command, system-surfaced integration
- W7+: Client view, 30-day outcome automation, pattern_matcher learning from backlog outcomes, quarterly roadmap export

---

## SOP library structure

Every SOP uses the fixed template below. Organised semantically by function.

```
data/reference/sops/
├── README.md                       # Manifest: list, owners, versions, last-reviewed
├── _templates/
│   ├── sop-template.md             # Meta-SOP
│   ├── checklist-template.md
│   └── runbook-template.md
│
├── deployment/
│   ├── 00-pre-deployment-checklist.md
│   ├── 01-fork-blueprint.md
│   ├── 02-setup-supabase.md
│   ├── 03-setup-railway.md
│   ├── 04-configure-env.md
│   ├── 05-onboarding-call-guide.md
│   ├── 06-load-context.md
│   ├── 07-setup-email-infrastructure.md
│   ├── 08-configure-scout.md
│   ├── 09-first-pipeline-dryrun.md
│   ├── 10-go-live-checklist.md
│   ├── 11-qa-calibration-setup.md
│   └── 12-seed-cost-budgets.md
│
├── pipeline/
│   ├── scrape-new-niche.md
│   ├── write-approve-template.md
│   ├── calibrate-qa-agent.md
│   ├── analyze-weekly-performance.md
│   ├── kill-template-decision.md
│   ├── scale-template-decision.md
│   ├── reply-handling-playbook.md
│   ├── system-surfaced-recommendations.md
│   └── outcome-measurement.md
│
├── client-management/
│   ├── daily-intelligence-brief.md
│   ├── weekly-report-generation.md
│   ├── friday-review-session.md
│   ├── monthly-strategy-call.md
│   ├── monthly-margin-review.md
│   ├── quarterly-autonomy-review.md
│   ├── escalation-handling.md
│   ├── capture-client-feedback.md
│   ├── weekly-backlog-triage.md
│   ├── monthly-prioritization.md
│   └── quarterly-roadmap-planning.md
│
├── business/
│   ├── discovery-call-script.md
│   ├── proposal-generation.md
│   ├── contract-signing.md
│   ├── payment-setup.md
│   ├── client-handover.md
│   └── handover-plus-training.md
│
└── incident/
    ├── domain-burn-rotation.md
    ├── smartlead-api-outage.md
    ├── supabase-rls-failure.md
    ├── qa-agent-drift.md
    ├── three-failures-escalation.md
    └── budget-overage-response.md
```

### Standard SOP template

```markdown
# SOP: [Name]
Version: X.Y
Last reviewed: YYYY-MM-DD
Owner: [Kirsten / VA / Junior / AI / Automated]

## Purpose
Why this SOP exists and what problem it solves.

## Trigger
When or what initiates this procedure.

## Inputs
- Input 1
- Input 2

## Outputs
- Output 1
- Output 2

## Steps
1. [Atomic, verifiable action]
2. [Atomic, verifiable action]

## QA — how to verify it's done right
- Check 1
- Check 2

## Common errors + fixes
| Error | Cause | Fix |
|---|---|---|

## Escalation
When to stop and ask for help.

## Automation notes
- Fully automated: [list]
- Partially automated: [what human does vs AI does]
- Not automatable (and why): [list]

## Change log
- v1.0 — YYYY-MM-DD — initial
```

### SOP discipline in build plan

- Every new module or workflow generates its SOP in the same PR as the code
- No workflow ships without its SOP
- SOP manifest reviewed monthly for freshness

---

## Scope summary

### In scope

1. AIOS Blueprint four-layer architecture
2. Scout system (10 stages, BaseSystem-conformant, migrated from base-camp-agents)
3. Template architecture + AI-filled placeholders + QA agent + retry/escalate
4. 3 niches × 3 offers test matrix (Agencies + Fractional + Consulting)
5. Two-gate approval (human strategic + QA tactical)
6. Progressive autonomy ladder with explicit promotion criteria
7. Web app (operator console + client portal) as primary UX
8. Webhook surface (Smartlead, Calendly, Telegram) with signature verification
9. Per-client Supabase + Railway (Clymb gets its own)
10. SOP library covering deployment, pipeline, client management, business, incident
11. Timeline with four quality-gated milestones, flexible dates
12. Kill/scale rules, autonomy thresholds, error handling, testing
13. Metrics framework (funnel, system quality, financial, operational, composite)
14. Cost management: tier-based budgets, 3-gate caps, overage workflow
15. Monthly margin review (value-first efficiency engine)
16. Continuous improvement backlog (5 sources, 3 cadences, outcome measurement)

### Out of scope (roadmap, not May/June)

- Beacon (dedicated inbound system) — inbound reply handling lives inside Scout for now
- LinkedIn Outreach (Signal) — later system
- Ads, Content OS, Reporting as standalone systems — post first external client
- DealOS (M&A deal sourcing) — Tier 2 niche, separate system entirely
- AI Proposal Writer (DMCs, M&A) — Tier 2
- Multi-client operator console — one-client-at-a-time for now
- Slack integration — postponed to W6
- Autonomy promotion past `act_notify` for `send_outbound` — conservative through June
- Fine-tuned QA model — Haiku rubric sufficient for Phase 1-3
- Handover code/data packaging — later offering
- Beacon as a standalone system — replies handled inside Scout for now

### Open items (TODOs)

- Finalise the 9 concrete copy templates (Kirsten writes during W1, W3, W4), each scored against the 27-constraint offer framework before approval
- Create expert knowledge files in W2-3: `hormozi-offers.md`, `lara-acosta-linkedin.md`, `matt-walsh-linkedin.md`, `brunson-funnels.md`, `shelby-sapp-sales.md` — following the existing format in `data/knowledge/nick-saraev-ai-positioning.md`
- Decide on web app tenant-routing strategy (subdomain per tenant vs path-based) — single codebase either way per Section 0
- Confirm Railway cron vs APScheduler choice (recommended: Railway cron for simplicity)
- Contracts (MSA, DPA, SLA, NDA) need lawyer review before external client signing

### Productisation compliance checklist (gate for every build item)

Before any feature ships, answer yes to all:
- [ ] Does this go into the blueprint repo, not a client-specific location?
- [ ] Is per-client behavior driven by config/data, never by code differences?
- [ ] Can an unmodified fork of the blueprint run this feature given only the right data loaded?
- [ ] Is the SOP for operating this feature the same for every client?
- [ ] If disabled, does it remain inert in a client that hasn't opted in?

---

## Open questions for Kirsten before implementation plan

1. Any metrics from Section 8 that should land Day 1 vs later — different from what's proposed?
2. Cost cap tiers in Section 9 — are the default amounts right, or should they be tuned per actual vendor pricing?
3. Web app: build in this repo (subdirectory `web-app/`) or separate repo? Recommendation: separate repo for cleaner deployment, single origin for static hosting.
4. SOP writing cadence: Kirsten writes key SOPs (discovery call, proposal, handover) vs. AI drafts → Kirsten edits. Recommendation: AI drafts, Kirsten edits, she signs off.

---

## References

- `CLAUDE.md` — master AIOS instructions
- `context/projects/clymb/*.md` — Clymb's business context
- `context/projects/clymb/strategy.md` — niche priorities, offer structure
- `context/projects/clymb/research/customer/pain-buckets-and-offers.md` — niche pain research
- `data/knowledge/nick-saraev-*.md` — copywriting frameworks
- `data/reference/client-deployment-sop.md` — existing deployment SOP (to be updated)
- `data/reference/outbound-system-spec.md` — existing Scout spec
- `systems/base.py` — BaseSystem contract
- `os/foundation/*.py` — decision loop modules
- `/home/kirsten/01_PERSONAL/10_PERSONAL_PROJECTS/base-camp-agents/` — migration source
