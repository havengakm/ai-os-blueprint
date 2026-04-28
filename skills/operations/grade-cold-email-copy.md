---
name: grade-cold-email-copy
description: Predict the reply rate of a cold-email draft or variant before sending. Returns predicted reply rate (0.0-1.0), tier (A/B/C/D), and a 3-line critique covering what works, what doesn't, and what to change. Operator-interactive — runs via Claude Code sub-agent on Max-plan credits, no Anthropic API spend.
tier: capability
category: operations
tags: [optimizer, copy-grading, pre-send-qa, max-credits]
input: target — either a path to a YAML variant file under data/reference/sequences/ OR a draft_id (UUID) referencing outreach_drafts. Optional: client_id (string) for ICP context.
output: {predicted_reply_rate: float, tier: "A"|"B"|"C"|"D", critique: [string, string, string], graded_at: ISO-8601 string}
requires_skills: [validate-writing]
requires_tools: [Read, Bash, Agent]
references:
  - rules/global-writing-guardrails.md
  - data/reference/frameworks/allbound-system.md
  - data/knowledge/experts/saraev/outbound.md
when-to-use: Before approving a new variant for live sending. Also on-demand to QA a rendered draft before manual send. Plan 2 Phase 5 Task 2.5.4.
---

# grade-cold-email-copy

Operator-driven QA for cold-email copy. Predicts reply rate + tier + 3-line critique. No Anthropic API spend; runs purely via the Claude Code Agent tool against Max-plan credits.

## Purpose

The bandit doesn't learn until it has data. Before a new variant joins the live pool, this skill grades it against the writing rules + Saraev/Allbound playbooks + the client's ICP, predicts a reply rate, and surfaces 3 lines of critique. Operator decides whether to ship the variant.

When run on a persisted draft (draft_id), the verdict writes to `outreach_drafts.predicted_grade` (JSONB column added by migration 023). When run on a variant YAML before approval, the verdict writes to `data/captures/copy_grades/<variant_key>-<timestamp>.yaml` so it stays under git.

## Steps

1. **Resolve the target.**
   - If `target` is a file path under `data/reference/sequences/`, Read the YAML and extract the `text` field.
   - If `target` is a UUID, query `outreach_drafts` via `scripts/_lib/draft_lookup.py` (or operator-side SQL) to fetch the rendered subject + body.

2. **Load context.**
   - Read `data/knowledge/experts/saraev/outbound.md` for outbound-copy first principles.
   - Read `data/reference/frameworks/allbound-system.md` for signal-first messaging rules.
   - If `client_id` provided, read `client_config.icp` for the target persona + offer.

3. **Validate against writing rules.** Invoke the `validate-writing` skill on the body. If it fails hard rules (em-dash / banned words / banned diagnostic phrases), short-circuit with `tier="D"` + critique line 1 = the rule violation.

4. **Dispatch to a sub-agent.** Call the `Agent` tool with `subagent_type=general-purpose` and a prompt that:
   - Describes the framework (Saraev's "objection in the subject" pattern; Allbound's signal-first rule).
   - Includes the resolved subject + body + ICP context.
   - Demands a JSON response with: `predicted_reply_rate` (float 0.0-1.0), `tier` ("A" if >= 0.10, "B" if >= 0.05, "C" if >= 0.02, "D" otherwise), `critique` (exactly 3 short lines: "what works", "what doesn't", "what to change").
   - Forbids preamble, code fences, or extra fields.

5. **Parse + persist.**
   - When target was a draft_id: write the JSON (plus `graded_at`) to `outreach_drafts.predicted_grade`.
   - When target was a variant file: write to `data/captures/copy_grades/<variant_key>-<YYYY-MM-DDTHH-MM-SSZ>.yaml`.

6. **Output to the operator.** Print the JSON + a one-line summary like "Tier B (predicted 6.2% reply rate). Critique: ...".

## Output schema

```json
{
  "predicted_reply_rate": 0.062,
  "tier": "B",
  "critique": [
    "Subject hooks on a real signal (funding round). Strong opener.",
    "Body asks for a demo too early; no proof point first.",
    "Move the demo CTA to a Touch 2 and lead with one specific case study."
  ],
  "graded_at": "2026-04-27T12:34:56Z"
}
```

## What this skill does NOT do

- Does NOT call the Anthropic API directly. All inference runs via the Claude Code Agent tool on Max-plan credits per `feedback_max_credits_vs_api_boundary`.
- Does NOT auto-approve / auto-ship variants. Operator decides based on the grade.
- Does NOT replace bandit feedback. Once a variant is live, the actual reply rate overrides the prediction.

## Calibration loop

The companion daemon job `systems/optimizer/grader_calibration.py` (Plan 2 Phase 5 Task 2.5.5, daemon-side) compares predicted vs actual reply rates over a rolling 30-day window and surfaces calibration drift in the Optimizer weekly report. Operator approves recalibration before the grader's tier thresholds shift.
