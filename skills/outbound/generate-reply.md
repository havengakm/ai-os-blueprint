---
name: generate-reply
description: Generate a reply to one inbound cold-email reply, given the classification, objection code, and thread context. Matches the sender's energy, addresses the specific objection, moves the thread one step.
tier: capability
category: outbound
tags: [outreach, sales, reply-handling, writing]
input: reply_text, classification, objection_code, thread_context, lead_profile
output: {subject, body, requires_human_review}
requires_skills:
  - skills/meta/validate-writing.md
requires_tools: []
references:
  - rules/global-writing-guardrails.md
  - skills/outbound/classify-replies.md
  - data/knowledge/experts/sapp/
when-to-use: After classify-replies returns anything except opt_out_explicit, auto_reply, or interested_book_call. Interested_book_call routes to human, not this skill.
---

# generate-reply

Follow rules/global-writing-guardrails.md.

## Purpose

Reply to inbound objections and soft-yeses in a way that sounds like a calm human who has had this conversation a hundred times. No re-pitching. No defensive language. Move the thread one step.

## Inputs

- `reply_text` (required): the raw inbound reply (stripped of quotes).
- `classification` (required): one of the 8 classes from `classify-replies`.
- `objection_code` (required when classification starts with `objection_`).
- `thread_context` (required): `{previous_slot, angle_used, offer_mentioned, proof_mentioned}`.
- `lead_profile` (required): `{name, title, company}`.

## Steps

1. **Refuse the route for non-reply classes.** If classification is `opt_out_explicit`, `auto_reply`, or `interested_book_call`, return `{requires_human_review: true, reason: "<class routes elsewhere>"}` and do not draft.

2. **Match the energy.** Read the tone of `reply_text`:
   - Curt → match curt. Under 40 words.
   - Warm → match warm. Up to 70 words.
   - Hostile (but not DND) → neutral, short, no defence.

3. **Handle by classification.**

   - **objection_price**:
     - Acknowledge the number the lead named.
     - Offer ONE of: pilot-scoped version, payment spread, or ROI-framed comparison with their current tool.
     - One ask: "would any of those work, or is it off the table entirely?"

   - **objection_fit**:
     - Ask one question that tests the fit objection. Example: "Is it that you already have a team on the bottom-tier accounts, or that the AI-SDR category itself is the wrong shape for you?"
     - No defence of the offer.

   - **objection_channel**:
     - Apologise briefly (one clause), do not repeat.
     - Offer the preferred channel.
     - Close the email thread explicitly.

   - **interested_send_info**:
     - Attach the one-pager (call `skills/operations/send-asset.md`: future skill) and write ONE line under the attachment.
     - Propose the next step on a specific date.

   - **interested_but_timing**:
     - Confirm the window the lead named.
     - State exactly what you'll do when it arrives (one line).
     - Nothing else.

4. **Pull objection-response patterns** from `data/knowledge/experts/sapp/` (objection-handling playbook if present) and apply the closest-matching response structure.

5. **Enforce constraints.**
   - Zero re-pitches of the mechanism the lead already saw.
   - Zero adjectives of praise for the lead's message.
   - One ask.
   - Word count matches the energy match in step 2.

6. **Validate** via `skills/meta/validate-writing.md` with `context=generic`. Rewrite up to 2 times.

7. **Set `requires_human_review`.**
   - `true` if: hostile tone, legal language, mentioned competitor name by letter-of-agreement, or the response contains any number above $10k.
   - `false` otherwise.

8. **Log** with tags: `reply_class`, `objection_code`, `response_strategy`, `requires_human_review`.

## Output

```yaml
subject: "RE: third BDR post"
body: |
  Fair. $1.8k/mo is 4x your current spend.

  Two options: we can run a 30-day pilot on 100 accounts for $800 flat, or keep the $1.8k shape and only bill on meetings that get held.

  Which one is worth a conversation, or neither?
requires_human_review: false
```

## Quality gate

- Correct class-specific structure applied.
- Word count within the energy-match band.
- Zero re-pitch of the mechanism.
- `requires_human_review` correctly set.

## Escalation

- Any legal, regulatory, or press-risk language in the inbound reply → `requires_human_review: true`, no auto-send.
- Three consecutive validation failures on the same thread → flag for human.
