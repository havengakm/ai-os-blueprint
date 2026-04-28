# Objection-Handling Framework (cold-email reply context)

## Goal

**SELL THE MEETING. NOT THE PRODUCT.**

Every reply to an objection has one job: get a calendar booking. Don't try to close the deal in email. Don't quote prices. Don't list features. Get them on a 30-min call where the real conversation happens.

## Two-layer defence

### ARA — first-layer (default response)

- **Acknowledge** their concern in one short line. No mocking, no fake empathy, no "I totally understand". Just acknowledge the point.
- **Reassert** why a 15-30 min call is worth their time anyway. Tie back to what they'd GET, not what we'd say. Use ROI math, the stacked guarantee, or one specific data point.
- **Advance** to the calendar. Ask for the meeting directly. Drop the Calendly link.

### ACE — second-layer (only when ARA doesn't land)

- **Ask** a smart question to surface the real reason behind the objection.
- **Clarify** the underlying assumption they're operating on.
- **Expand** to build credibility (one specific data point or named outcome).

In email v1, every reply-response template at `data/reference/sequences/<niche>/components/reply_responses/` is an ARA template. ACE is the follow-up if the prospect rejects the meeting offer a second time. v1 routes ACE-needed cases to the operator's manual triage queue via the escalation runtime (Phase 3 Task 2.3.3).

## Email vs cold call (key reframe)

Cold call: ARA fires reflexively, no time to think.
Email reply: **the prospect chose to reply, so they're already partly open.** Use that. Be more direct + more confident than the cold-call version. They've self-qualified by engaging.

## Objection map → template

| Objection variants seen in the wild | Bucket | Our template |
|---|---|---|
| "We don't have budget" / "What's the cost?" / "Send me pricing" | Pricing | `objection_pricing.md` |
| "Not a priority" / "Follow up next quarter" / "Not changing this year" | Timing | `objection_timing.md` |
| "Not the right person" / "Talk to my COO" / "Go up the chain" | Authority | `objection_authority.md` |
| "Already have ABC" / "Tried before, fell through" / "Too small" / "Handle in-house" / "Have you worked with companies like ours?" | Other | `objection_other.md` |
| "Send me a calendar invite" | Direct | `meeting_request.md` |
| "Yes, interested" | Direct | `positive_interest.md` |

## ARA in 4 lines

1. **Acknowledge:** "Fair question." / "Got it." / "Hear you."
2. **Reassert:** ROI math, stacked guarantee, or one specific upside data point.
3. **Advance:** "Want to grab 15 minutes? Pick any time:"
4. **Calendar link.**

That's the spine. Length scales with the load-bearing content (pricing reply needs ROI math; timing reply just needs a one-line reassert).

## What goes wrong

- **Acknowledging then arguing.** "Got it BUT actually..." — keep "but" out. The shift is invisible to the prospect.
- **Selling the product instead of the meeting.** Listing features in the reply doesn't move the meeting closer.
- **Three CTAs.** One CTA: book the call.
- **Long hedging clauses.** "I just wanted to mention that we might possibly be able to..." — cut all of it.
- **Forgetting they replied.** Email-reply prospects are already engaged. Don't write like they ignored you.
- **Dodging the question.** "I keep numbers off email" sounds like company policy. "I won't quote blind because it depends on what you're trying to fix" frames it as protecting the prospect from a wrong-fit number. Same answer; very different tone.

## Reference material

- `data/knowledge/experts/saraev/cold-email.md` — outbound first principles + risk-reversal framing
- `data/knowledge/company/strategy.md` — stacked 4-part guarantee + ROI math per niche
- `data/reference/frameworks/allbound-system.md` — signal-first methodology
- Connor Murray "Top 25 Sales Objections" YouTube (`youtube.com/watch?v=_0tdFL3A5aA`) — origin of the ARA / ACE pattern (cold-call context). 10 worked examples per objection class.

## When this framework applies

- Generating new reply-response templates per niche (creative_branding today; future agency-client niches tomorrow).
- Operator review of AI-generated drafts: does the body follow A → R → A? If not, rewrite.
- Future copy-grader skill (Phase 5 Task 2.5.4): grade against this framework.
