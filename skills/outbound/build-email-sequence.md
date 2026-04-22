---
name: build-email-sequence
description: Build a 4-email cold sequence for one lead from their initial cold email + angle. Each follow-up adds a new angle or new proof, never re-pitches. Respects cool-off and round-based re-entry rules.
tier: capability
category: outbound
tags: [outreach, sales, cold-email, sequencing]
input: lead_profile, offer, initial_email, angles_backlog, send_cadence
output: sequence (ordered list of 4 emails with {slot, send_after_days, subject, body, references_angle})
requires_skills:
  - skills/meta/validate-writing.md
requires_tools: []
references:
  - rules/global-writing-guardrails.md
  - skills/outbound/generate-cold-email.md
  - data/knowledge/experts/saraev/cold-email.md
when-to-use: After generate-cold-email has produced email 1. Output populates the send queue.
---

# build-email-sequence

Follow rules/global-writing-guardrails.md.

## Purpose

Most of the reply volume comes from emails 2 through 4. This skill builds the follow-ups so each one earns attention with a new angle or new proof, not a re-pitch.

## Inputs

- `lead_profile` (required): `{name, title, company}`.
- `offer` (required): same as `generate-cold-email`.
- `initial_email` (required): output of `generate-cold-email`.
- `angles_backlog` (required): the full `angles` list from `generate-outreach-angles` (so emails 2-4 can draw from unused angles).
- `send_cadence` (optional): `{slot_2_days: 3, slot_3_days: 5, slot_4_days: 7}`. Defaults to `{3, 5, 7}`.

## Steps

1. **Pull the used angle.** The initial email burned one angle. Mark it used. Emails 2-4 draw from the remainder.

2. **Assign one angle per follow-up slot.**
   - Slot 2: a DIFFERENT angle, same pain family (keeps the conversation coherent).
   - Slot 3: a PROOF-DRIVEN email. Zero angle-switching; instead, a client case study or a hard outcome number that contradicts the objection the lead is likely forming.
   - Slot 4: a BREAK-UP email. One sentence acknowledging silence, one sentence stating what you'll stop doing, one sentence offering the door to be re-opened on a specific trigger.

3. **Draft each follow-up body.** Constraints per slot:
   - Slot 2: under 60 words. Leads with a micro-observation or a new fact. No "just following up." No quoting of the previous email.
   - Slot 3: under 80 words. Structure: one-line context, one concrete number or client name, one clear ask.
   - Slot 4: under 45 words. Clean close. No guilt-trip, no passive aggression.

4. **Generate subject lines.** Reuse the initial email's thread (RE: prefix via the send tool). Slot 4 gets a fresh subject that signals finality, under 4 words.

5. **Enforce sequence rules.**
   - No follow-up may repeat an angle already used in an earlier slot.
   - No follow-up may re-state the offer's mechanism: only add new proof or a new angle.
   - Total sequence word count under 260.
   - At most one `?` in each email.

6. **Validate every body** via `skills/meta/validate-writing.md` with `context=cold_email`. Rewrite as needed.

7. **Log the sequence composition** with tags: `sequence_id`, `angles_used`, `slot_count`.

## Output

```yaml
sequence:
  - slot: 2
    send_after_days: 3
    subject: "RE: third BDR post"
    body: |
      Quick add on yesterday: your CRO just posted about "scaling pipeline without scaling headcount" two days before the BDR req went up.

      The gap between those two posts usually means someone gets asked to produce 40% more pipeline with the same 3 reps.

      Want the specific accounts we'd work first?
    references_angle: "cro-pipeline-gap"

  - slot: 3
    send_after_days: 8
    subject: "RE: third BDR post"
    body: |
      Skipping the usual follow-up.

      Last month Greenhaus (similar stage, 14-person RevOps team) had us take the bottom 300 accounts of their Salesforce. 11 booked meetings in 30 days, two closed inside 60.

      Worth 15 minutes to see if the list looks the same?
    references_angle: "proof_greenhaus"

  - slot: 4
    send_after_days: 15
    subject: "closing the loop"
    body: |
      Going to stop the follow-ups.

      If the BDR ramp hits a wall in the next quarter, reply with the word "accounts" and I'll send the working list.

      Otherwise, good luck with the hire.
    references_angle: "break_up_conditional_reopen"
total_word_count: 186
```

## Quality gate

- No angle repeated across slots.
- No offer-mechanism repeated across slots (only proof or angle changes).
- Every body passed `validate-writing`.
- Sequence total under 260 words.

## Escalation

If `angles_backlog` has fewer than 2 unused angles, sequence cannot be built. Return `sequence_build_failed` and call `generate-outreach-angles` again with a broader pain set.

## Interaction with cool-off and round logic

Per `feedback_surround_sound_architecture` memory: sequences respect 90-day cool-off on explicit opt-out and round-based re-entry rules. This skill produces the body content only. The scheduler (Beacon, Plan 2) owns send timing and cool-off enforcement.
