# Outbound skills

Atomic skills that produce and process cold outreach. Every skill here follows `rules/global-writing-guardrails.md` and validates output via `skills/meta/validate-writing.md`.

## Skills (populated)

- `generate-outreach-angles.md`: produce 3-5 distinct angles (pain + trigger + hook) for an ICP + offer.
- `write-personalised-first-line.md`: write one verifiable, angle-aligned first line under 20 words.
- `generate-cold-email.md`: compose one complete cold email under 75 words, one idea, one ask.
- `build-email-sequence.md`: build the 4-email sequence (initial + 3 follow-ups) with unique angles per slot.
- `classify-replies.md`: sort inbound replies into 8 classes with objection codes and cool-off dates.
- `generate-reply.md`: reply to objections and soft-yeses without re-pitching.

## Skills (planned, from the atomic taxonomy)

- `audit-deliverability-risk.md`: domain warm-up state, inbox rotation health, spam-score check.
- `design-inbox-rotation.md`: distribute sends across sending domains and inboxes to stay under per-inbox caps.
- `generate-connection-message.md`: LinkedIn connection request copy (under 300 chars).
- `build-dm-sequence.md`: LinkedIn DM follow-up sequence post-connection.
- `merge-content-with-outbound.md`: pull a recent LinkedIn post or blog from the lead and thread it into outreach timing.

## Invocation order (typical cold email flow)

```
generate-outreach-angles
  └─ write-personalised-first-line   (per-lead)
       └─ generate-cold-email         (per-lead)
            └─ build-email-sequence   (per-lead)

<reply lands>
  └─ classify-replies
       └─ generate-reply              (if class warrants auto-reply)
```

## Knowledge sources

- `data/knowledge/experts/saraev/cold-email.md`: angle patterns, subject-line structure
- `data/knowledge/experts/saraev/ai-positioning.md`: how to position AI-SDR without the generic AI pitch
- `data/knowledge/experts/sapp/sales.md`: objection taxonomy for `classify-replies` + `generate-reply`
