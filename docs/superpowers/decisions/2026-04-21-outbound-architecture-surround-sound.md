# Decision: Outbound Architecture — Surround-Sound Multi-Channel with Cross-Channel State Coordination

**Date:** 2026-04-21
**Decided by:** Kirsten
**Status:** Accepted

## Context

Plan 1 is shipping a single-channel (email) prospecting + drafting pipeline. The original Plan 2 roadmap was email-only reply handling. Session 2026-04-20 / 2026-04-21 surfaced that a single-channel outbound system significantly undersells the AIOS product:

- Response rates on cold email alone have been declining year-over-year.
- High-ticket B2B buyers (fractional CFOs, agency owners, consultants) live in multiple channels, not one. Email alone misses them.
- Buying-signal-driven outreach (funding events, hiring, product launches) is the strongest response-rate driver in B2B and requires multi-channel orchestration to capitalise on quickly.

## Decision

Build AIOS outbound as a **surround-sound multi-channel system** with:

1. **Pluggable channel modules** — each channel (email, LinkedIn, SMS, voicemail, WhatsApp, letters, voice-booking) is a self-contained module. Per-client config enables or disables each.
2. **Cross-channel state coordination** — a single contact-state machine; a reply or opt-out on any channel pauses ALL other sequences immediately.
3. **Buying-signal-driven content** — real intent data (Trigify LinkedIn triggers + Claude multi-page research extraction) feeds per-contact personalisation. Signals are required, not optional.
4. **YAML-defined conditional sequences** — non-linear, DAG-shaped outbound flows that branch on events (connection accepted, reply received, link clicked, time elapsed). Sequences authored in YAML, productised per niche, per round.
5. **90-day cool-off + round-based re-entry** — contacts who complete a full sequence without replying go to a 90-day cool-off, then re-enter with a materially different sequence (different angle, hook, offer) for up to 3-4 rounds total.
6. **Global DND on explicit opt-out** — any channel's explicit opt-out (keyword match or toxic-severity reply) pauses ALL channels for that contact.

## Reasoning

### Why channels-as-modules (vs monolithic send service)

**Client variability.** A client in California is regulation-cautious on SMS; a client in the EU can't use WhatsApp without explicit opt-in; a client in a handshake-driven industry values handwritten letters for tier-A prospects. Monolithic "send" logic bakes in assumptions about what channels exist. Modular lets each client configure their compliance-and-audience mix.

**Vendor swap agility.** Email ESP swaps (SendGrid → Postmark → SES) should not touch LinkedIn logic. SMS provider swaps (Twilio → Telnyx) should not touch Email. A channel module owns its vendor integration, templates, rate limits, and compliance gates; the rest of the system talks to the `ChannelModule` Protocol.

**Incremental rollout.** Ship email (Plan 1/2) first. Add LinkedIn (Plan 3). Add SMS (Plan 4). Each plan adds one channel without destabilising the others.

### Why cross-channel state coordination is non-negotiable

A prospect replies on LinkedIn at 9:00 AM. The email sequence has a step queued for 9:05 AM. If we don't pause, they get a sequence email five minutes after replying. That looks unprofessional, damages trust, and burns the warm lead.

**Mechanism:** single `contacts.status` field owned globally. Reply ingestion (any channel's webhook) writes `status=replied` in the same transaction it records the reply. The sequence engine re-reads `status` with a row-level lock immediately before firing any step. Only stale window: step already in transit at the telco / ESP (seconds, not minutes). Acceptable for the professional bar.

### Why buying signals are required, not optional

Forrester research: first vendor to engage after a trigger event wins 35-50% of the time. An email referencing "congrats on the Series B" lands differently than a generic pitch. Generic personalisation (industry + size inference) reads as cold reading; specific trigger-referenced outreach reads as attention.

**Signal sources:** Trigify (LinkedIn-surfaced funding, leadership changes, product launches — $0.012/credit or $149/mo) + Claude multi-page research (scraped website + LinkedIn company page, extracts hiring signals, expansion signals, tooling mentions, citable case studies). Both feed `research_data.trigger_events[]` + `research_data.buying_signals[]`.

Signals drive TWO things:
- **Content (primary):** template placeholders `{{trigger_hook}}`, `{{signal_reference}}`, `{{citable_detail}}` turn generic templates into specific outreach
- **Scoring (secondary):** score_v2 intent bucket flags `has_active_buying_signal` for prioritisation

### Why YAML conditional sequences

Linear sequences (step 1, wait 3d, step 2, wait 2d, step 3) break on contact with reality. Real flows branch:
- If LinkedIn connection request accepted → send LinkedIn message
- If not accepted after 3d → fallback to email, reference "tried on LinkedIn"
- If message sent but no reply in 1d → cross-channel nudge on email
- If reply received at any point → STOP all channels

YAML + state-machine executor matches `feedback_productised_not_custom`: non-engineers author sequences as config, not code. Engine is one piece of code; every client's sequences are data. Victoria-style.

### Why 90-day cool-off + round-based re-entry

Contacts who complete a full outbound sequence without replying are not necessarily disqualified — they may be busy, mid-quarter, or in an unfortunate timing window. A hard "dead" status after one round throws away future pipeline.

Pattern:
- Round 1 complete, no reply → `cooling_off` for 90 days → re-enter with Round 2 sequence (different angle / hook / offer)
- Round 2 complete, no reply → cool-off → Round 3 (new angle again)
- Round 3-4 complete, no reply → `dead` (or operator extends via UI)

**Critical:** each round uses materially different:
- Pain angle (Round 1: pipeline; Round 2: retention; Round 3: team capacity)
- Hook (Round 1: case study led; Round 2: trigger event led; Round 3: provocation led)
- Offer (Round 1: full AIOS; Round 2: AIOS lite; Round 3: workshop or done-with-you consult)

Matches `feedback_offer_score_framework` — every offer iteration scored on the 27-constraint rubric.

Re-entry **re-runs enrich** (fresh buying signals) and **re-scores v2** (intent changes in 90 days). Does NOT re-run v1 (firmographics are stable). If v2 drops below archive_floor, mark dead.

### Why global DND on explicit opt-out (vs per-channel)

**Legal letter:** SMS opt-out does not technically require email opt-out in most jurisdictions. But operationally: if a prospect hates us enough to type STOP or "fuck off," continuing to email them is the kind of brand damage we don't recover from. Global DND is safer and simpler, and operators can override per-channel via manual action if a legitimate case arises.

**Opt-out detection:** two-signal:
- **Keyword matcher** (regex, fast, deterministic): STOP, UNSUBSCRIBE, REMOVE ME, OPT OUT, DO NOT CONTACT, "take me off", "stop emailing" → immediate DND.
- **Toxicity / highly-negative classifier** (Claude, for "fuck off" class): severity score 0-10. Severity ≥ 8 → auto-DND. Below → just `replied`, routed to human review.

## Roadmap impact

| Plan | Scope |
|---|---|
| Plan 1 (current, in progress) | Scout prospecting: pull → score → screen → identity → enrich → render drafts. No change. |
| Plan 2 (next) | Beacon: reply ingestion (email) + reply classifier + Calendly link handler + cross-channel state machine + YAML sequence engine (linear + conditional) + 90-day cool-off scheduler |
| Plan 3 | Channels framework (`ChannelModule` Protocol) + LinkedIn module (highest-value second channel) |
| Plan 4 | SMS module (Twilio or Telnyx) |
| Plan 5 | Voicemail / ringless voicemail module + voice-booking agent module (VAPI or similar, per `2026-04-20-reject-ai-voice-agent` amended scope) |
| Plan 6 | WhatsApp module + handwritten letters module (Postalytics / Letter) |
| Plan 7+ | Dashboards, analytics, weekly reports, per-client sequence library authoring UI |

## Critical-systems defenses baked in

Per `feedback_simplicity_over_complexity` critical-systems exception, every channel module has mandatory defenses:

- **Compliance SOP per channel** (`data/reference/sops/{channel}-compliance.md`). Matches existing `phone-sms-compliance.md` pattern.
- **Consent basis verification** before every send — channel-specific (email: legitimate interest + unsubscribe link; SMS: prior explicit consent; WhatsApp: opt-in confirmation; voicemail: jurisdiction-specific).
- **Tier budget caps** with auto-pause at 100% of client's per-tier spend (reuses `tier_budgets_cents` config already in 003_client_config_extensions.sql).
- **Every paid API call** logs measured cost to `decision_log` (reuses `EnrichResult.cost_cents` pattern from Task 12a).
- **Opt-out processing** within ≤60 seconds of reply ingestion, globally across all enabled channels.

## Open questions deferred to plan-authoring time

- **Sequence DSL specifics:** exact YAML grammar, supported event types, supported wait predicates. Design in Plan 2.
- **Channel-specific identifier schema:** inline columns on `contacts` vs `contact_channels` table. Design in Plan 3 when second channel (LinkedIn) lands.
- **Operator dashboard shape:** fuzzy-match review queue, manual cool-off adjustment, sequence rotation override. Plan 7+.

## Reversal conditions

This architecture is revisited if:

- Operator review after first 3-6 months of production shows cross-channel coordination is causing more harm than help (e.g., cascading false-positive opt-outs). Unlikely, but worth a periodic review.
- A single channel dominates so strongly in measured conversion that multi-channel complexity isn't justified. Would have to be overwhelming evidence.
- A vendor ships a truly-integrated multi-channel platform at a price we can't match in-house. We are productised specifically to own this layer, so the bar is high.

Absent these, the architecture stands.
