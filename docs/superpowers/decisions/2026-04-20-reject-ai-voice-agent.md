# Decision: AI Voice Agent — Narrow Rejection (Closer = NO, Booking Agent = YES)

**Date:** 2026-04-20 (original) / 2026-04-21 (amended with narrower scope)
**Decided by:** Kirsten
**Status:** Amended — narrow rejection only

> **AMENDMENT 2026-04-21:** The original 2026-04-20 decision rejected AI voice agents ENTIRELY. That was based on a misreading of the use case. The correct scope of the rejection is narrower: AI voice agents CLOSING high-ticket sales = rejected; AI voice agents BOOKING appointments into a human closer's calendar = accepted and on the roadmap. See "Amended scope" section below. The original reasoning is preserved for context.

---

## Amended scope (authoritative as of 2026-04-21)

### REJECTED: AI voice agent as sales closer

An AI conducting the actual sales call — discovery, objection handling, pricing conversation, close — is rejected. High-ticket sales ($5k-$25k+) close on trust, tension management, and identity-led selling (Shelby Sapp framework). Human-only.

### ACCEPTED: AI voice agent as appointment booker

A voice agent whose entire job is to book a prospect who has already replied positively into a human closer's Calendly slot. Scope:

1. **Trigger:** prospect replies positively on email / LinkedIn / SMS / WhatsApp.
2. **Call:** voice agent (VAPI or similar) calls within ~60 seconds to 2 minutes.
3. **Script:** confirm interest, confirm phone number, offer specific Calendly times, book the meeting.
4. **Output:** Calendly invite sent via SMS or email after booking.
5. **Post-booking nurture:** T-24h reminder, T-1h reminder to reduce no-show rate.

Quality bar is fundamentally lower than closing: "confirm interest + drop a Calendly link" vs "navigate pricing objections on a $15k deal." VAPI-level voice quality is adequate for this job.

## Where voice-booking agent fits in the roadmap

Placed as a MODULE in the surround-sound architecture (decision `2026-04-21-outbound-architecture-surround-sound.md`). Each outbound channel is a module — email, LinkedIn, SMS, voicemail, WhatsApp, letters, voice-booking. Clients enable which channels they want per their compliance posture and audience preferences.

Voice-booking as a module:
- Fires only in response to positive reply events (not as cold outbound)
- Respects global DND / opt-out list
- Post-booking nurture sequence is itself a small multi-step flow in the sequence engine

## Historical reasoning (original 2026-04-20 rejection, preserved)

The original rejection rested on three claims:

1. **Call volume is too low to justify an AI closer build.** Still true for a closer. Not true for a booking agent — a booking agent is cheap to wire (VAPI credit model) and drops the time-to-book lag from hours to seconds.

2. **High-ticket closing needs a human.** Still true. The human closer takes the Calendly call and runs the Shelby Sapp discovery + close arc. The AI booking agent does NOT replace that.

3. **Downside risk exceeds upside (for an AI closer).** Still true for closers — a fumbled objection at the close burns a warm lead. Not true for a booking agent — the downside of a fumbled booking call is low (prospect gets the Calendly link via follow-up SMS/email anyway), the upside is measurably faster booking and higher show-up rate via automated reminders.

## What still replaces the closer

**Human closer, always.** Shelby Sapp methodology (Three Buckets discovery → Drop & Silence → Objection Playbook → 6-Step Close Arc) is the canonical spine. The booking agent exists to put prospects on the closer's calendar, not to do any part of the closer's job.

## Implications

- Follow-up item 17 (Voice callback system): reclassified from REJECTED to **Plan 5 scope** (voice-booking-agent module). Scope narrowed to booking + reminder use case only.
- Follow-up item 18 (Voice vendor decision): reclassified from REJECTED to **research required before Plan 5**. Evaluate VAPI, Bland, Retell, Synthflow on booking-specific quality bar (low sophistication bar, high latency sensitivity, good Calendly integration) — NOT on closing sophistication.
- `data/reference/design_inputs/2026-04-20-multichannel-outbound-methodology.md`: voice section is NOT rejected scope — update amendment.
- `feedback_voice_agent_rejected` memory: rename / rewrite to reflect narrow rejection.
- Shelby Sapp knowledge file (`data/knowledge/shelby-sapp-sales.md`): continues to describe human closers only. The voice-booking agent does not use Sapp methodology — it has a different job.

## Reversal conditions (for the narrow rejection on closers)

The "AI can't close high-ticket" position is revisited only if:

- A voice vendor ships objection-handling capability at demonstrable parity with a trained human closer on high-ticket sales (not expected at current model capabilities).
- A specific client pilot shows AI-closed deals at equal or better close-rate than human-closed deals on matched prospect cohorts (experiment required, not assumed).

Absent these, human closers remain the rule.
