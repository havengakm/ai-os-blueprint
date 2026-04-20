# Decision: Reject AI Voice Agent for High-Ticket Closing

**Date:** 2026-04-20
**Decided by:** Kirsten
**Status:** Accepted

## Context

The Victoria + Vapi + Make.com video (captured as input at `data/reference/design_inputs/2026-04-20-multichannel-outbound-methodology.md`) proposed a Vapi voice agent calling prospects 60 to 120 seconds after a positive reply to confirm phone number and text a Calendly link.

This was provisionally added to the roadmap as Plan 3 "Voice" scope, with items 17 and 18 in `docs/superpowers/plans/follow-ups-plan1.md` capturing the build and the vendor research (Vapi vs Dan Martell's product vs Bland / Retell / Synthflow / ElevenLabs).

## Decision

**Drop the AI voice agent from the roadmap entirely.** Do not build Plan 3 Voice. Do not research voice vendors. Do not budget for voice per-minute cost.

## Reasoning

1. **Call volume is too low to justify the build.** AIOS is a productised service targeting a narrow tier of high-ticket buyers. Total annual call volume across all clients is measured in dozens to low hundreds, not thousands. The per-call cost of a voice agent (build + vendor + maintenance) does not amortise at that volume.

2. **High-ticket closing needs a human.** $5k to $25k+ sales close on trust, not efficiency. A prospect who just replied positively to a cold outbound message is warm but skeptical. An AI voice agent that fumbles an objection, mispronounces a name, or can't answer a pricing nuance burns the warm lead. Shelby Sapp's methodology (captured at `data/knowledge/shelby-sapp-sales.md`) is explicit: tension management, identity selling, and silence-after-the-drop are human skills. An AI agent optimised for booking speed undermines the tension that drives the close.

3. **Downside risk exceeds upside.** Best case: an AI voice agent shaves 24 hours off time-to-book. Worst case: it turns a warm, positive-reply prospect into a lost deal by sounding robotic or mishandling an objection. For a low-volume high-ticket book, the downside is larger than the upside.

## What replaces it

**The Beacon reply handler (Plan 2) sends the Calendly link directly on a positive reply.** No voice step between reply and calendar. A human closer takes the Calendly meeting. Shelby Sapp's six-step close arc runs live on the call.

This is the system Kirsten actually wants:
1. Scout sends AI-personalised outbound (email, and later LinkedIn)
2. Prospect replies positively
3. Beacon's autoresponder sends the Calendly link, answers basic questions from the knowledge base
4. Prospect books
5. Human closer takes the call with the Shelby Sapp discovery and close script

## Implications

- Follow-up items 17 (Voice callback system) and 18 (Voice vendor decision) are REJECTED. Leave in the backlog but mark rejected with a pointer to this decision record.
- The multichannel design-input note's "Voice callback" section is REJECTED scope, not future scope. Add an amendment at the top.
- Shelby Sapp knowledge file must NOT reference voice agent integration. Update the "Integration notes for AIOS" and Principle 5 sections to describe human closers only.
- Memory: add `feedback_voice_agent_rejected.md` so future subagent dispatches do not propose AI voice.

## Reversal conditions

This decision is revisited only if:
- Total annual call volume exceeds ~1000 qualified bookings across all clients (not expected within Plan 1-4 scope)
- A voice vendor ships objection-handling capability at parity with a trained human closer on high-ticket sales (not expected at current model capabilities)
- A specific client needs and pays for voice qualification as a bolt-on (handle as custom work, not product)

Absent these, do not revisit.
