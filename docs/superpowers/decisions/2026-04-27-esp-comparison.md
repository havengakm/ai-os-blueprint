# ESP Comparison — Instantly vs Smartlead vs PlusVibe.ai

**Decision required:** which Email Service Provider does Beacon (Plan 2 Phase 2) build against?
**Decision owner:** Kirsten
**Decision target date:** before Plan 2 Phase 2 kickoff
**Status:** ✅ **DECIDED 2026-04-27 — Instantly Growth ($47/mo)** — see "Operator decision" section at the bottom

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

## Open questions for operator (RESOLVED 2026-04-27)

1. **Smartlead pool warming duration?** → 10 days (started Apr 17). Low sunk cost.
2. **Have you exercised Smartlead's Pro tier API ($94)?** → No.
3. **"Smartlead API is better" — hands-on or marketing impression?** → Marketing impression. Operator hadn't used the API hands-on, only the warming free trial.
4. **Multi-client volume cap concern?** → Each client gets its own sub-account at agency level. Per-client volume cap, not per-org. 5K/mo Growth tier = 1 client; agency scaling moves to Hypergrowth $97 (100K/mo) which still beats Smartlead Smart $174.

## Mid-decision technical validation: programmatic campaign creation

Operator raised a critical concern late in the eval: **"can you push email campaigns using Instantly API, or do campaigns have to be pre-built with merge fields?"** Validated against both APIs:

**Instantly v2 API supports the full Beacon + Plan 4 autoresearch loop:**

| Need | Endpoint |
|---|---|
| Create campaign | `POST /api/v2/campaigns` |
| Update sequence step content (email body) | `PATCH /api/v2/campaign-subsequences/:id` |
| Add leads (1000 per request) | `POST /api/v2/leads/bulk` |
| Launch / resume | `POST /api/v2/campaigns/:id/activate` |
| Pull replies + emails | `GET /api/v2/emails` |
| Send a reply | `POST /api/v2/emails/:id/reply` |

**Smartlead API parity** (from their llms.txt index): `POST /campaigns/create`, `POST /campaigns/{id}/sequences`, `POST /campaigns/{id}/leads`, `PATCH /campaigns/{id}/status`. Reply-pull endpoint not surfaced in the public index but likely exists deeper.

**Reference proof point:** Nick Saraev's autoresearch orchestrator (the inspiration for Plan 4) deploys baseline + challenger campaigns autonomously via Instantly's API — the pattern is validated working.

**The merge-fields concern is half-true:** Yes, Instantly campaigns use templates with `{{firstName}}` placeholders. But the template body itself can be created + updated programmatically via `PATCH /api/v2/campaign-subsequences/:id`. So Plan 4 autoresearch's auto-generated challengers can land as new campaigns + sequence content via API without any UI touch.

## Operator decision (2026-04-27)

- [x] **Final ESP choice: Instantly**
- [x] **Tier picked: Growth ($47/mo)** — covers MVP volume + API + webhooks + unlimited warmup. Upgrade to Hypergrowth ($97/mo) when agency scales to 5+ clients.
- [x] **Reasoning:** API parity at $47 vs Smartlead Smart $174 (3.7× cheaper). Operator's "Smartlead API better" was marketing impression, never hands-on validated. Max Mitcham reference value (Trigify ↔ Instantly patterns + Saraev's working orchestrator). 10 days of Smartlead warming is recoverable.
- [x] **Sunk-cost decision on Smartlead pool:** Keep warming as backup for 30 more days; pause adding NEW domains there. Start fresh Instantly warming pool. Switch send activity Instantly once it's fully warmed (~30 days from start).
- [x] **Decision date:** 2026-04-27.

Next steps unblocked:
- Plan 2 plan doc references updated from "the chosen ESP" → "Instantly".
- `memory/INDEX.md` decision row added.
- `feedback_esp_evaluation_pending` harness memory marked resolved.
- Phase 2 (Beacon email foundation) starts; Beacon adapter targets Instantly v2 API.

## What this doc does NOT do

- Does not commit to an architecture for `Beacon` — that's Plan 2 Phase 2 task work.
- Does not pre-build adapters for both — operator decision rule: build against Instantly first; abstract only if a second ESP is needed later.
- Does not run a hands-on API sandbox spike — operator chose to lock in based on doc + Saraev's working orchestrator as proof points. If unexpected gaps surface during Phase 2, revisit.
