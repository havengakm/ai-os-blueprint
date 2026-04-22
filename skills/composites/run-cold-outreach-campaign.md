---
name: run-cold-outreach-campaign
description: Orchestrate a complete cold outreach campaign for a batch of leads. Generates angles once for the ICP, then per-lead composes a first line, a cold email, a 4-slot sequence, and registers each thread in the send queue. Output is ready for Beacon (send scheduler).
tier: composite
category: outbound
tags: [outreach, sales, cold-email, campaign, sequencing]
input: icp_profile, offer, lead_list, send_cadence (optional)
output: campaign (campaign_id, angles_used, threads[]); threads is a list of {lead_id, subject, email_1, sequence[2..4], status=rendered}
requires_skills:
  - skills/outbound/generate-outreach-angles.md
  - skills/outbound/write-personalised-first-line.md
  - skills/outbound/generate-cold-email.md
  - skills/outbound/build-email-sequence.md
  - skills/meta/validate-writing.md
requires_tools: []
references:
  - rules/global-writing-guardrails.md
  - data/knowledge/experts/saraev/cold-email.md
when-to-use: After an ICP is defined, an offer is stable, and a verified lead list is staged. Runs once per batch, not per lead. Do NOT invoke for single-lead one-offs; use the atomic capabilities directly for those.
---

# run-cold-outreach-campaign

Follow rules/global-writing-guardrails.md.

## Purpose

A cold outreach batch has a predictable shape: ICP and offer are fixed, angles are shared across leads, first lines and emails are per-lead. This composite runs that shape end-to-end, calling one atomic capability per phase, so any atomic improvement (new validator rule, better angle prompt) propagates automatically.

## Inputs

- `icp_profile` (required): output of `skills/market-intelligence/extract-icp-traits.md` or a hand-written profile.
- `offer` (required): transformation, mechanism, proof, price point.
- `lead_list` (required): list of lead objects `{lead_id, name, title, company, verified_facts[]}`. Each lead must carry at least one verified fact, else the lead is skipped.
- `send_cadence` (optional): passed to `build-email-sequence`. Defaults to `{3, 5, 7}`.

## Orchestration

1. **Generate angles once for the ICP.** Call `skills/outbound/generate-outreach-angles.md` with `icp_profile` and `offer`. Store the returned 3 to 5 angles as `angles_backlog`. If fewer than 3 angles return, abort the campaign and escalate.

2. **Pick the starting angle.** Default: the angle tagged `best_for_segment` matching the largest segment of the lead list. Tie-break: highest estimated-reach angle.

3. **For each lead in `lead_list` (parallel-safe):**

   a. **Compose first line.** Call `skills/outbound/write-personalised-first-line.md` with the lead, the starting angle, and the lead's `verified_facts`. If it returns `null`, mark the lead `skipped_no_verified_signal` and move on.

   b. **Compose cold email.** Call `skills/outbound/generate-cold-email.md` with the lead, offer, angle, and first line. If it fails validation 3 times, mark the lead `compose_failed` and move on.

   c. **Build the sequence.** Call `skills/outbound/build-email-sequence.md` with the lead, offer, the initial email, the remaining `angles_backlog`, and `send_cadence`. If it cannot build (fewer than 2 unused angles), degrade to a single-email send and log `sequence_degraded`.

   d. **Assemble the thread.** Collect `{lead_id, subject, email_1, sequence[2..4]}` and mark `status=rendered`.

4. **Summarise the batch.** Count: rendered, skipped, failed, degraded. Log a single decision-log entry per lead (per `feedback_surround_sound_architecture`).

5. **Return the campaign object.** Do NOT send. Beacon (Plan 2) owns send timing, cool-off enforcement, and the send queue.

## Output

```yaml
campaign:
  campaign_id: "clymb-founder-led-2026-04-22"
  icp_segment: "founder_led_small"
  angles_used: ["post-third-BDR-role", "cro-pipeline-gap", "series-a-new-cmo"]
  threads:
    - lead_id: "lead_8421"
      status: "rendered"
      subject: "third BDR post"
      email_1: "<body>"
      sequence:
        - slot: 2, body: "...", send_after_days: 3
        - slot: 3, body: "...", send_after_days: 8
        - slot: 4, body: "...", send_after_days: 15
    - lead_id: "lead_8422"
      status: "skipped_no_verified_signal"
    # ...
  summary:
    rendered: 84
    skipped: 11
    compose_failed: 3
    sequence_degraded: 2
```

## Quality gate

- Every rendered thread passed every atomic skill's own quality gate.
- Zero rendered threads contain the same personalisation fact across two different leads (verified by hashing source_fact per lead).
- Summary totals match `len(lead_list)`.

## Escalation

- `compose_failed` rate above 15%: pause the campaign, surface a sample of the failed leads to the operator. Likely the ICP profile or offer is drifting from the angle set.
- `skipped_no_verified_signal` rate above 40%: pause. Enrichment pipeline is too thin for this segment.
- Any lead with the domain on `data/knowledge/company/blacklist.md`: skip at step 3a, mark `skipped_blacklist`, do not count as failure.

## Autonomy

This composite runs at `draft` autonomy per the Sales department manifest. Every rendered thread lands in `outreach_drafts` status=`rendered`, visible to the operator, before any send happens. Promotion to `act_notify` or `autonomous` requires the 50-decision, 80-percent-success bar per CLAUDE.md.
