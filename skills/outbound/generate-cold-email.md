---
name: generate-cold-email
description: Generate one complete cold email from {lead_profile, offer, angle, first_line}. Under 75 words total. One idea, one ask. Output is ready to send after validator pass.
tier: capability
category: outbound
tags: [outreach, sales, cold-email, writing]
input: lead_profile, offer, angle, first_line
output: {subject, body}
requires_skills:
  - skills/meta/validate-writing.md
requires_tools: []
references:
  - rules/global-writing-guardrails.md
  - data/knowledge/experts/saraev/cold-email.md
when-to-use: After generate-outreach-angles and write-personalised-first-line have run for this lead. Output feeds build-email-sequence (for follow-ups) or a send queue directly.
---

# generate-cold-email

Follow rules/global-writing-guardrails.md.

## Purpose

Compose one cold email that goes in slot 1 of the sequence. The first line does the hook work; this skill wraps a bridge, an offer-teaser, and a single ask around it.

## Inputs

- `lead_profile` (required): `{name, title, company}`.
- `offer` (required): transformation + mechanism + proof point.
- `angle` (required): full angle object from `generate-outreach-angles`.
- `first_line` (required): output of `write-personalised-first-line`.

## Steps

1. **Build the structure.**
   - Line 1: the personalised first line (input, do not rewrite).
   - Line 2: bridge: one clause that names the pain consequence the lead is already feeling.
   - Line 3: offer teaser: one clause, mechanism-first, no adjectives. Example: "We place one SDR-quality AI agent on those same accounts for $X/mo, measured on booked calls."
   - Line 4: one proof point: a number, a client name the lead would recognise, or a specific outcome with a timeframe.
   - Line 5: one ask: a question with a clear yes/no answer. Not a meeting pitch.

2. **Draft the subject line.**
   - Under 5 words.
   - References the angle's trigger or pain, not the offer.
   - Looks like a forwarded internal thread, not a marketing email.
   - Examples: "third BDR post", "after the Series A", "those 500 accounts".

3. **Enforce hard counts.**
   - Total body word count under 75.
   - Single `?` in the whole body (the ask).
   - Zero em dashes.
   - Zero buzzwords (see `rules/global-writing-guardrails.md` section 2).

4. **Insert a signature placeholder.** `{sender_name}`, `{sender_role}`, `{sender_company}`. No photo, no banner, no "P.S." by default.

5. **Validate** via `skills/meta/validate-writing.md` with `context=cold_email`. On fail, rewrite. Max 3 attempts before escalation.

6. **Log the composition** via `aios/foundation/decision_logger.py` with tags: `stage=compose`, `angle_name`, `first_line_source_fact`, `segment`. This is how the Optimizer learns which components win.

## Output

```yaml
subject: "third BDR post"
body: |
  Your job post for a third BDR on 14 Apr suggests the current team is drowning in the same 500 accounts.

  Usually that's when reply rates crash and the new hire gets handed a list that nobody warmed up.

  We place one SDR-quality AI agent on those accounts for $1.8k/mo, measured on booked calls only.

  Acme Co booked 11 meetings in the first 30 days on a list their team had stopped working.

  Open to a 15-minute look?

  {sender_name}
  {sender_role}, {sender_company}
word_count: 68
```

## Quality gate

- Under 75 words.
- One idea (the angle's pain), one ask.
- Personalised line verifiable against `first_line.source_fact`.
- Proof point is specific and checkable.
- Passed `validate-writing`.

## Escalation

Three validation failures on the same lead → archive the lead as `compose_failed`, surface to human. Do not silently send a generic fallback.
