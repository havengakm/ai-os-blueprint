---
name: write-personalised-first-line
description: Write one cold-email or LinkedIn first line for a specific lead. Personalisation must reference one verified fact about the lead or company and tie directly to the angle's pain. Under 20 words.
tier: capability
category: outbound
tags: [outreach, sales, cold-email, personalisation]
input: lead_profile, angle, verified_facts
output: first_line (string, under 20 words)
requires_skills:
  - skills/meta/validate-writing.md
requires_tools: []
references:
  - rules/global-writing-guardrails.md
  - data/knowledge/experts/saraev/cold-email.md
when-to-use: As the first step of composing any cold email or LinkedIn DM. Output feeds generate-cold-email.
---

# write-personalised-first-line

Follow rules/global-writing-guardrails.md.

## Purpose

The first line is the make-or-break. If it sounds generic or forced, the rest of the email dies unread. This skill produces one line that makes the lead think "this is about me."

## Inputs

- `lead_profile` (required): `{name, title, company, role_context, tenure_days}`.
- `angle` (required): one angle object from `generate-outreach-angles` (angle_name, pain, trigger, hook_sentence).
- `verified_facts` (required): list of facts retrieved from enrichment (LinkedIn post, job posting, funding announcement, tech stack signal, podcast appearance). Each fact must have a source URL or a decision_log reference.

## Steps

1. **Reject the empty-personalisation path.** If `verified_facts` is empty, return `null`. Do not write a first line from nothing. Escalate to `identify_verified_signal` first.

2. **Rank facts by angle-fit.** The best fact is the one that already contains the trigger from the angle. A "posted a third BDR role" fact beats a generic "their company raised $10M" fact when the angle is about hiring strain.

3. **Pick the top-ranked fact.** If no fact fits the angle within a reasonable stretch, return `null` and escalate.

4. **Draft one line** that:
   - Leads with the fact (concrete, specific, dated if possible).
   - Bridges to the pain using one clause.
   - Does not mention the offer yet. That's the second line's job.
   - Is under 20 words.
   - Does not contain em dashes, filler, buzzwords, or generic praise.

5. **Forbidden patterns** (hard fail, retry):
   - "I saw you…" as the opening.
   - "Congrats on…" as the opening.
   - "Hope you are well" or any variant.
   - "Loved your recent post" without naming which post.
   - Any line that could be sent to any other lead with one word swapped.

6. **Validate** via `skills/meta/validate-writing.md` with `context=cold_email`. If it fails, rewrite up to 2 more times.

## Output

```yaml
first_line: "Your job post for a third BDR on 14 Apr suggests the current team is drowning in the same 500 accounts."
source_fact: "LinkedIn job posting 2026-04-14, url: https://..."
```

## Quality gate

- Under 20 words.
- Contains one verified, dated, specific fact.
- Bridges to the angle's pain without naming the product.
- Would NOT make sense if sent to a different lead.

## Escalation

Two consecutive null returns → flag the enrichment pipeline; verified signals are too thin for this segment. Three consecutive validation failures → flag for human review per CLAUDE.md.
