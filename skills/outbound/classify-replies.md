---
name: classify-replies
description: Classify one inbound reply to a cold email into one of 8 reply types, extract the objection or intent signal, and produce the state transition for the contact record.
tier: capability
category: outbound
tags: [outreach, sales, reply-handling, classification]
input: reply_text, lead_profile, thread_context
output: {classification, objection_code, intent_score, recommended_next_action, cool_off_until}
requires_skills: []
requires_tools: []
references:
  - rules/global-writing-guardrails.md
  - data/knowledge/experts/sapp/
when-to-use: Every time a reply lands in the inbox for a cold email thread. Runs before generate-reply so the reply skill has classified context.
---

# classify-replies

Follow rules/global-writing-guardrails.md.

## Purpose

Not every reply deserves a human touch, and not every reply is the same kind of signal. This skill sorts them so the downstream reply generator, the CRM, and the cool-off logic all get the correct instruction.

## Inputs

- `reply_text` (required): the raw body of the inbound email.
- `lead_profile` (required): `{name, title, company, previous_stage}`.
- `thread_context` (required): which email slot was sent last, and the angle used in that slot.

## Steps

1. **Strip signatures and quoted text.** Keep only the new content.

2. **Classify into one of 8 types.** Pick the strongest match:
   - `interested_book_call`: explicit yes to a meeting, or "send me the calendar."
   - `interested_send_info`: asking for the one-pager, case study, or deck.
   - `interested_but_timing`: engaged, naming a future window ("Q3", "after launch").
   - `objection_price`: pushback on cost, budget, ROI.
   - `objection_fit`: "we don't do this," "wrong person," "already have a solution."
   - `objection_channel`: "don't email me," "prefer LinkedIn," "we hate cold email."
   - `opt_out_explicit`: unsubscribe, "remove me," legal reference, hostile tone.
   - `auto_reply`: OOO, bounceback, autoresponder, no human signal.

3. **Extract the objection code** if the classification is `objection_*`. Use the shared objection taxonomy in `data/knowledge/experts/sapp/` if present. Example codes: `price_too_high`, `wrong_stakeholder`, `competitor_entrenched`, `timing_post_funding`, `internal_build_in_progress`.

4. **Score intent** on 0-100:
   - `interested_book_call`: 95
   - `interested_send_info`: 75
   - `interested_but_timing`: 55
   - `objection_price`: 40 (buying signal, just the wrong price)
   - `objection_fit`: 10
   - `objection_channel`: 5 (but do not lose the lead: re-route channel)
   - `opt_out_explicit`: 0 (and global DND flag)
   - `auto_reply`: null (no signal)

5. **Set cool-off.**
   - `opt_out_explicit` → permanent DND; no re-engage ever.
   - `objection_fit` → 180 days.
   - `objection_channel` → 0 days on new channel, 365 days on current channel.
   - `objection_price` → 90 days, re-enter on price-change or case-study proof.
   - `interested_but_timing` → reschedule send to the named window + 7 days.
   - `auto_reply` → 5 days.
   - Others → 0 days (handle this cycle).

6. **Recommend next action.**
   - `interested_book_call` → route to human closer + attach Calendly (per `feedback_voice_agent_rejected` memory, human-only close).
   - `interested_send_info` → trigger asset send + 3-day follow-up.
   - `interested_but_timing` → snooze.
   - Any `objection_*` → call `skills/outbound/generate-reply.md` to handle.
   - `opt_out_explicit` → mark DND, no reply.
   - `auto_reply` → no reply.

7. **Log the classification** with tags: `reply_class`, `objection_code`, `intent_score`, `cool_off_until`, `slot_that_was_sent`.

## Output

```yaml
classification: "objection_price"
objection_code: "price_too_high"
intent_score: 40
recommended_next_action: "call generate-reply with objection_code=price_too_high"
cool_off_until: "2026-07-21"   # 90 days from today
notes: "Lead engaged with proof point but flagged $1.8k/mo as too high vs. their current $400/mo spend."
```

## Quality gate

- Exactly one classification assigned.
- Cool-off date is a real date, not null, unless classification is `auto_reply` or `interested_*`.
- Objection code filled whenever classification starts with `objection_`.
- Hostile language correctly detected as `opt_out_explicit`, not as objection.

## Escalation

- Ambiguous classification (top two scores within 10 points) → flag for human, do not auto-reply.
- Legal language in reply (lawsuit, GDPR, regulator) → immediate human escalation, suspend all sends to domain.
