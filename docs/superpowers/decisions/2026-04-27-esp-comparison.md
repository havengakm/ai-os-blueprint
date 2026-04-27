# ESP Comparison — Instantly vs Smartlead vs PlusVibe.ai

**Decision required:** which Email Service Provider does Beacon (Plan 2 Phase 2) build against?
**Decision owner:** Kirsten
**Decision target date:** before Plan 2 Phase 2 kickoff
**Status:** **DRAFT — operator decision pending** (see "Operator decision" section at the bottom)

## Context

Plan 2's email full-loop ships against ONE ESP first. Three candidates surfaced during the 2026-04-26 + 2026-04-27 alignment work:

- **Smartlead** — operator's current warming destination + first-pass API impression
- **Instantly** — Max Mitcham's primary tool (per `feedback_cold_email_stack_reference`)
- **PlusVibe.ai** — Max's experimental tool (per 2026-04-27 operator note)

Building against the wrong ESP costs: re-warming a fresh pool of domains (~30 days), rewriting Beacon's adapter layer, replanning Phase 2-3 schedule. So this decision is high-leverage; the bar to flip from operator's current state (Smartlead warming) is genuinely material API or deliverability gap.

## Decision criteria

Per `feedback_esp_evaluation_pending`, in order:

1. **API quality** — concrete method coverage for Beacon's needs (campaign create, sequence step add, send pacing, reply pull, webhook subscribe).
2. **Deliverability + warming** — table-stakes; all three should pass.
3. **Cost** at MVP volume (3-5 accounts × 20 emails/day = 60-100 sends/day per client).
4. **Cadence engine flexibility** — Instantly's was strong per the Hans/Max webinar; verify Smartlead + PlusVibe match.

**Decision rule** (tiebreakers in order):
1. If a candidate is pre-MVP / unstable / lacks a developer API → drop from contention.
2. If multiple candidates meet deliverability + cadence parity → API quality is the tiebreaker.
3. Smartlead has the warming head-start. Switching costs reputation. Flip to another candidate only if the API gap is material **or** the Max-Mitcham reference value (Trigify ↔ Instantly integration patterns already documented) tips the scale.

## Per-vendor evaluation

### Instantly

| | |
|---|---|
| Pricing (relevant tier) | **Growth $47/mo** — 5K emails/mo, unlimited accounts, **API + webhooks included**, unlimited warmup |
| Next tier | Hypergrowth $97/mo — 100K emails/mo |
| API access | ✅ **Across all paid tiers from $47/mo** |
| Webhook support | ✅ Mentioned across all plans |
| Warmup | ✅ Unlimited warmup across all tiers (built-in pool) |
| Deliverability infra | ✅ SISR (automatic server/IP rotation) |
| Cadence engine | ✅ Strong per Hans/Max webinar reference |
| Reference value | ✅ **Max Mitcham's primary tool**; Trigify ↔ Instantly integration patterns documented in `feedback_cold_email_stack_reference` |
| API quality (per docs) | TBD — Claude has not exercised the API; assess against Beacon's needs in a 1-day spike |
| Verdict | **In contention** — strong all-rounder; $47 entry tier clears API access |

### Smartlead

| | |
|---|---|
| Pricing (relevant tier) | **Base $39/mo** — 6K emails/mo, **NO API, NO warmup pool** |
| Next tier with API | **Pro $94/mo** — 90K emails/mo, CRM; API still TBD per their pricing page |
| Tier with full API | **Unlimited Smart $174/mo** — 150K emails/mo, warmup pool, "full API access" |
| API access | ⚠️ **Effectively starts at $174/mo for the Beacon use case** |
| Webhook support | TBD — needs operator confirmation; not surfaced in pricing page |
| Warmup | ❌ Not in Base; ✅ Smart + Prime tiers only |
| Deliverability infra | ✅ Smart tier + dedicated SmartServers in Prime |
| Cadence engine | TBD — operator's first-pass was favourable; needs concrete API method comparison |
| Reference value | ✅ Operator has domains warming there |
| Operator-stated preference | "API is better for our purposes" — but this comment was made about high-tier API; comparing at $47-vs-$39 entry tier, Smartlead's Base lacks API entirely |
| Verdict | **In contention with caveat** — at MVP volume the operator is paying $174 for API parity with Instantly's $47. Re-validate the "better API" claim at the price point we'd actually use. |

### PlusVibe.ai

| | |
|---|---|
| Status | Generally available (rebranded from pipl.ai); 14-day free trial |
| Pricing | **Not publicly displayed** — requires demo booking |
| API access | ❌ **Not mentioned**; integrations limited to webhooks + Zapier + native connectors (HubSpot, Slack, Gmail, Outlook) |
| Webhook support | ✅ |
| Warmup | ✅ "Private warm-up pool" — claimed as a differentiator |
| Deliverability infra | Customer testimonials claim outperforms Smartlead + Instantly on warmup |
| Reference value | ⚠️ Max Mitcham is **experimenting** — not his primary tool |
| Verdict | **Drop from contention** per Decision Rule #1 — no developer API surfaced. Beacon needs programmatic campaign creation, sequence step injection, reply pull. Webhook + Zapier integrations don't substitute. |

## Side-by-side at MVP volume

3-5 accounts × 20 emails/day × 30 days = ~1,800-3,000 emails/month per client.

| Need | Instantly Growth ($47) | Smartlead Base ($39) | Smartlead Smart ($174) | PlusVibe |
|---|---|---|---|---|
| Email volume covered | 5,000/mo ✅ | 6,000/mo ✅ | 150,000/mo ✅ | n/a (no public API) |
| API for Beacon | ✅ | ❌ | ✅ | ❌ |
| Warmup | ✅ | ❌ | ✅ | ✅ |
| Webhooks | ✅ | TBD | ✅ | ✅ (limited) |
| Multi-account rotation | ✅ | ✅ | ✅ | ✅ |
| **Effective monthly cost for Beacon parity** | **$47** | n/a (no API) | **$174** | n/a (no API) |

## Tentative recommendation

**Instantly's Growth tier ($47/mo)** is the strongest candidate at MVP volume:

1. ✅ API + webhooks at the $47 entry tier — no jump to $174 to get parity.
2. ✅ Unlimited warmup at all tiers.
3. ✅ Max-Mitcham reference value: Trigify ↔ Instantly patterns already documented in our memory.
4. ✅ Cadence engine validated at Hans/Max webinar.

**Caveat:** the operator's domains are warming on Smartlead. Switching costs ~30 days of warming on a fresh pool. So the tiebreaker depends on:
- **If we need API NOW (Phase 2 ships in 2-3 weeks)** → Instantly wins; Smartlead at $174 is overpaying for parity at our volume.
- **If we can run Phase 2 manually for 30 days while a new Instantly pool warms** → still Instantly.
- **If operator's Smartlead pool is already 14+ days into warming** → flag as sunk cost; don't let it drive the decision.

**PlusVibe is dropped** — no developer API. Webhook/Zapier integrations don't cover Beacon's needs (programmatic campaign create, sequence step injection, reply pull).

## Open questions for operator

Before final decision:

1. **How many days has the Smartlead pool been warming?** If <14 days, switching is low-cost. If 21+, the warming sunk cost matters.
2. **Have you exercised Smartlead's Pro tier API ($94)?** Their pricing page lists "API access" on Pro but the docs are thin — the $174 Smart tier is where "full API access" is explicit. Worth a 30-min sandbox spike to confirm Pro tier covers Beacon's needs.
3. **Was the "Smartlead API is better" comment based on hands-on use or marketing impression?** Hands-on > marketing.
4. **Is there a 3-5 account multi-client need we'd hit on Instantly's Growth tier?** "Unlimited accounts" is true but the 5K monthly email cap might bite on the cohort scale Plan 2 Phase 2 needs.

## Operator decision

**To be filled in by Kirsten:**

- [ ] Final ESP choice: ☐ Instantly  ☐ Smartlead  ☐ PlusVibe.ai  ☐ Other
- [ ] Tier picked: __________
- [ ] Reasoning (1-2 sentences): __________
- [ ] Sunk-cost decision on existing Smartlead warming: ☐ keep warming as backup ☐ pause warming ☐ switch all to chosen ESP
- [ ] Decision date: __________

After operator fills this in, append a row to `memory/INDEX.md` Recent Decisions and update Plan 2 plan doc's references from "the chosen ESP" to the actual name.

## What this doc does NOT do

- Does not run a hands-on API sandbox spike. That's the next step if the doc-level analysis isn't enough to decide.
- Does not commit to an architecture for `Beacon` — that's Plan 2 Phase 2 task work.
- Does not pre-build adapters for both — per the operator decision rule, build against the picked ESP first; abstract later only if a second ESP is needed.
