---
name: generate-outreach-angles
description: Generate 3-5 distinct outreach angles for a given {icp_profile, offer}. Each angle names a specific pain, a specific trigger, and the hook sentence that weaponises it. Used before writing any cold message.
tier: capability
category: outbound
tags: [outreach, sales, cold-email, research]
input: icp_profile, offer
output: angles (3-5 objects with {angle_name, pain, trigger, hook_sentence, best_for_segment})
requires_skills:
  - skills/meta/validate-writing.md
requires_tools: []
references:
  - rules/global-writing-guardrails.md
  - data/knowledge/experts/saraev/
when-to-use: Before writing first lines, email bodies, or LinkedIn DMs. The output is the input to write-personalised-first-line and generate-cold-email.
---

# generate-outreach-angles

Follow rules/global-writing-guardrails.md.

## Purpose

Produce distinct angles of attack for outreach. One angle = one pain + one trigger + one hook. Without this, every cold message defaults to the same generic angle and reply rates collapse.

## Inputs

- `icp_profile` (required): firmographic + role + top pains from `skills/market-intelligence/extract-icp-traits.md` or a hand-written profile.
- `offer` (required): what you are selling, the transformation it produces, the price point.

## Steps

1. **Load context.**
   - Read `data/knowledge/experts/saraev/cold-email.md` (if present) for angle patterns.
   - Read `data/knowledge/company/` for offer-specific proof, case studies, positioning.

2. **Extract the ICP's top 5 pains.** Prefer pains directly from the ICP profile. If missing, infer from the offer (what problem does it solve: that's the pain).

3. **Name 5 candidate trigger events** that make a lead buy NOW rather than later. Examples: new hire, funding round, tech-stack signal, job posting, competitor move, seasonal pressure, failing KPI.

4. **Pair each trigger with one pain.** Not every pair works. Keep the pairs where the trigger clearly surfaces the pain.

5. **Draft one hook sentence per pair.** One sentence. Under 20 words. Leads with the trigger, names the pain as a consequence, implies the solution is inside. Example: "You just posted a third BDR role: which usually means your current team is burning out on the same 500 accounts."

6. **Filter to 3-5 distinct angles.** If two angles point at the same pain, keep the stronger trigger. If an angle needs context the ICP won't have, drop it.

7. **Tag each angle** with the ICP segment it fits best (e.g., `founder_led_small`, `vp_marketing_midmarket`).

8. **Validate hook sentences** via `skills/meta/validate-writing.md` with `context=cold_email`. Any hook that fails: rewrite, re-validate.

## Output

```yaml
angles:
  - angle_name: "post-third-BDR-role"
    pain: "current team overloaded, reply rates dropping"
    trigger: "posted a third BDR role on LinkedIn in last 30 days"
    hook_sentence: "You just posted a third BDR role, which usually means the current team is burning through the same 500 accounts."
    best_for_segment: "founder_led_small"
  - angle_name: "series-a-new-cmo"
    pain: "inherited funnel, unclear attribution"
    trigger: "CMO started less than 90 days ago after Series A"
    hook_sentence: "Your CMO started 60 days after the Series A, which is when the old attribution stack usually starts hiding where leads actually come from."
    best_for_segment: "series_a_post_cmo"
  # ... 1-3 more
```

## Quality gate

- Every hook under 20 words, one idea, no filler.
- Zero overlap in underlying pain across angles.
- Each angle is specifically useful for its named segment.
- All hooks passed `validate-writing`.

## Escalation

If fewer than 3 distinct angles emerge after 2 passes, the ICP profile is too thin. Escalate: request more pain/trigger data from the user or run `skills/market-intelligence/extract-pain-points-from-transcripts.md`.
