---
name: filter-icp-list
description: Filter a CSV of prospects against a client's ICP using LLM judgment. Returns the same CSV annotated with two new columns (icp_fit, icp_reasoning). Operator-interactive — runs via Claude Code sub-agent on Max-plan credits, no Anthropic API spend.
tier: capability
category: operations
tags: [optimizer, icp-filter, list-cleanup, max-credits]
input: csv_path (string) — path to a CSV with at minimum: company, description, website. Optional columns: title, employees, industry, geography. Plus client_id (string) so client_config.icp can be loaded.
output: annotated CSV at <csv_path>.icp-filtered.csv with two new columns appended — icp_fit ∈ {"yes", "maybe", "no"} and icp_reasoning (one-line string). Original rows preserved.
requires_skills: []
requires_tools: [Read, Write, Bash, Agent]
references:
  - data/reference/frameworks/allbound-system.md
when-to-use: After scraping a fresh prospect list (Apollo / Clutch / manual). Before importing into the daemon via `scripts/ingest_preresolved_contacts.py`. Plan 2 Phase 5 Task 2.5.6.
---

# filter-icp-list

Cleans a raw prospect list against a client's ICP definition using a Claude Code sub-agent. Operator imports the surviving rows (`fit=yes`) into the daemon.

## Purpose

The Scout pull stage is rule-based — it accepts any contact that matches the client's filter. That's a coarse net. Before a new list goes into the daemon, this skill applies LLM judgment to weed out poor fits the rule-based filter missed (wrong industry adjacency, off-strategy company stage, mismatched geography intent). Operator does this once per fresh list; the surviving subset gets ingested.

## Steps

1. **Validate inputs.**
   - Read the CSV. Confirm `company` + `description` + `website` columns are present.
   - Confirm `client_id` provided. Look up `client_config.icp` from Supabase (operator runs this from the AIOS repo so the client identity is authoritative).
   - If the ICP block has no `positive_examples` / `negative_examples`, log a warning and proceed with the textual ICP definition only — the sub-agent will be less calibrated.

2. **Load the ICP context.**
   - Pull `client_config.icp` fields: titles, geographies, employee_min, employee_max, industries, positive_examples, negative_examples.
   - Read `data/reference/frameworks/allbound-system.md` for signal-first list-cleaning principles (don't filter out signal-having contacts on a soft mismatch).

3. **Dispatch row-by-row to a sub-agent.**
   - Use the `Agent` tool with `subagent_type=general-purpose` once per row (or in batches of 10 to keep the sub-agent's context tight).
   - Prompt structure: ICP definition + the row's company/description/website/optional fields. Demand JSON: `{"icp_fit": "yes"|"maybe"|"no", "icp_reasoning": "<one-line, no jargon>"}`. Forbid preamble + code fences.
   - Cap reasoning at 120 characters. Reject longer responses + retry once.

4. **Aggregate + write the annotated CSV.**
   - Append two columns to each row: `icp_fit`, `icp_reasoning`.
   - Write to `<original_csv>.icp-filtered.csv` (sibling file; never overwrite the source).
   - Print summary: counts of yes/maybe/no.

5. **Operator follow-up.** Operator reviews the `maybe` rows manually, decides which to promote to `yes`, then imports the surviving rows via `scripts/ingest_preresolved_contacts.py`.

## Output annotated CSV columns

The original columns plus:

| Column | Values | Notes |
|---|---|---|
| `icp_fit` | `yes` / `maybe` / `no` | LLM verdict |
| `icp_reasoning` | string | one-line rationale, ≤120 chars |

## Calibration

Per `feedback_allbound_framework`: signal-first means "don't filter out a signal-having contact on a soft fit mismatch". Sub-agent prompt should reflect this — a contact with a recent funding round or expansion signal that's a 'maybe' on industry should still come back as `maybe`, not `no`.

## What this skill does NOT do

- Does NOT call the Anthropic API directly. All inference runs via the Claude Code Agent tool on Max-plan credits per `feedback_max_credits_vs_api_boundary`.
- Does NOT mutate the source CSV — the annotated output is a sibling file.
- Does NOT auto-import surviving rows. Operator runs `ingest_preresolved_contacts.py` manually after reviewing the `maybe` bucket.
- Does NOT replace the daemon's screen stage. The screen stage applies hard blacklist rules; this skill is a pre-ingest LLM-judged sift.

## Cost note

Per row sub-agent call ≈ 1-2c on Sonnet equivalent — but routed through Max-plan credits, not the Anthropic API. A 500-row list grades for free under the operator's existing subscription. If the list is huge (>2000 rows) consider pre-filtering via the rule-based Scout pull first.
