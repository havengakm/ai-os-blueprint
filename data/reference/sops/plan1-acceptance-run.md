# SOP: Plan 1 Acceptance Run
Version: 1.0
Last reviewed: 2026-04-23
Owner: Kirsten / VA

## Purpose

Gate the `plan1-foundation-scout` branch merge to `main`. The acceptance
run proves the full 7-stage Scout pipeline fires under the foundation
loop against a real Supabase project, logs every decision, composes at
least one complete draft, and contains zero fabricated content.

Until this SOP passes for at least one seeded client, Plan 1 does NOT
merge.

## Trigger

Run ONCE before merging `plan1-foundation-scout` to `main`. Also re-run
when:

- A new migration lands that touches decision_log, component_variants,
  business_context, client_facts, or autonomy_rules.
- The foundation loop in `systems/base.py` changes shape.
- Scout's `_prime_foundation` in `systems/scout/skill.py` changes.

## Inputs

- Supabase project with migrations `001_foundation.sql` through
  `006_component_registry.sql` applied.
- One seeded client: `clients` + `client_config` + `business_context`
  + `client_facts` + `autonomy_rules` + `component_variants` + at
  least 10 pipeline-eligible contacts. Exact requirements enforced by
  `scripts/plan1_acceptance_preflight.py` - run that first.
- `.env` with all four keys: `SUPABASE_URL`,
  `SUPABASE_SERVICE_ROLE_KEY`, `VOYAGE_API_KEY`, `ANTHROPIC_API_KEY`.

## Outputs

- `data/reports/plan1-acceptance-{timestamp}.md` - full evidence
  report, emitted by `plan1_acceptance_verify.py`.
- Go / no-go call logged in this SOP's change log or the Plan 1
  merge PR description.

---

## Pre-run prerequisites checklist

The preflight script enforces all 8 below. Manual validation is
optional when the script is available.

1. `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `VOYAGE_API_KEY`,
   `ANTHROPIC_API_KEY` present in `.env`.
2. All 10 critical tables reachable: `clients`, `client_config`,
   `contacts`, `outreach_drafts`, `decision_log`, `business_context`,
   `client_facts`, `knowledge_base`, `autonomy_rules`,
   `component_variants`.
3. `clients.status='active'` + `client_config` row exists for the
   target `client_id`.
4. `business_context` has >= 1 row for the client.
5. `client_facts` has >= 1 row for the client.
6. `knowledge_base` has >= 1 row globally.
7. `autonomy_rules` covers every pipeline decision_type:
   `source_selection`, `score_contact`, `screen_contact`,
   `identity_lookup`, `enrich_contact`, `render_draft`,
   `research_contact`.
8. `component_variants` has at least one `(niche, offer_label)`
   pairing with all 6 approved component types: `subject_line`,
   `icebreaker`, `pain_hook`, `offer_frame`, `cta`, `signature`.
9. `contacts` has >= 10 rows in pipeline-eligible statuses
   (`new` / `screened` / `ready` / `enriched`).

---

## Running the acceptance test

Single command:

```bash
./scripts/plan1_acceptance.sh <client-id>
```

This chains three steps internally:

1. `plan1_acceptance_preflight.py --client-id=<id>`
2. Capture `STARTED_AT` + run
   `run_daemon_once.py --client-id=<id> --dry-run`.
3. `plan1_acceptance_verify.py --client-id=<id>
   --started-at=$STARTED_AT`.

Exit codes:

| Exit | Meaning | Action |
|---|---|---|
| 0 (verify=0 or 2) | Automated checks green | Operator reads the report, ticks the hallucination probe, proceeds. |
| 1 | Preflight failed / daemon errored / verify auto-failed | Fix the root cause per the report, re-run. Do NOT merge. |
| 2 | Env missing | Fix `.env`, re-run. |

Individual steps can be run in isolation:

```bash
# Just preflight
uv run python scripts/plan1_acceptance_preflight.py --client-id=<id> [--json]

# Verify only (after a manual run_daemon_once)
uv run python scripts/plan1_acceptance_verify.py \
    --client-id=<id> \
    --started-at=2026-04-23T00:00:00Z \
    --output=data/reports/plan1-acceptance-manual.md
```

---

## Reading the report

`data/reports/plan1-acceptance-{timestamp}.md` has 6 sections:

1. **Summary** - totals, foundation-loop marker, auto-pass verdict.
2. **Decision breakdown by type** - table of decision_type -> count.
3. **Foundation-loop trace** - per-stage row. Every pipeline
   decision_type should have >= 1 row. Empty rows = the stage
   did NOT execute, which fails automated checks.
4. **Drafts composed** - one entry per `render_draft` decision. A
   "complete" tuple covers all 6 component types. Skipped contacts
   (no approved variant for some component_type) are marked.
5. **Hallucination probe** - operator eyeball pass. Cross-reference
   each draft's `component_tuple` variant keys against the YAML
   sources + each contact's `raw_data` + `research_data` in Supabase.
6. **Recommendation** - `AUTO PASS`, `AUTO FAIL`, or `NEEDS OPERATOR
   REVIEW`.

What "good" looks like for the hallucination probe:

- Every `variant_key` resolves to an approved component in
  `component_variants` (check via Supabase or the loader YAML).
- Every `signals_referenced.source` is a real adapter that ran for
  the contact - Trigify, ZeroBounce, or an identity-adapter source.
- No placeholders in `fills_missing` are citable facts. Unfilled
  `{{icebreaker_content}}` rendering as empty = acceptable. Unfilled
  `{{pain_evidence}}` = reject: that's load-bearing content.
- Spot-check at least 3 drafts. If any is borderline, check 3 more.

---

## Go / No-Go decision

**GO (merge Plan 1 to main)** - all of:

- Automated checks green (`recommendation: NEEDS OPERATOR REVIEW` or
  `AUTO PASS`).
- Operator inspected at least 3 drafts and ticked the hallucination
  probe checkbox in the report.
- Zero fabricated content across inspected drafts.

**NO-GO (do NOT merge)** - any of:

- `recommendation: AUTO FAIL`.
- Any inspected draft contains a fabricated fact (name, claim, stat,
  company detail that does not trace back to raw_data or
  research_data).
- Preflight failed.
- `run_daemon_once` reported a stage error.

---

## QA

- GO: commit the report to the PR description, merge
  `plan1-foundation-scout` to `main`, proceed to Task 19.
- NO-GO: file a new backlog item under
  `data/knowledge/personal/improvement_backlog.md` with the failure
  mode + fix plan. Do NOT merge. Fix, re-run acceptance, repeat.

---

## Common errors

| Error | Cause | Fix |
|---|---|---|
| Preflight: `component_variants` fails | No (niche, offer_label) pairing has all 6 approved types. | Run `scripts/load_components.py --client-id=<id>` and seed at least one complete YAML pairing with `status: approved`. |
| Preflight: `autonomy_rules` fails | Not every pipeline decision_type seeded. | Run `scripts/seed_autonomy_rules.py --client-id=<id>`. |
| Preflight: `contact_count` fails | Fewer than 10 pipeline-eligible contacts. | Run pull stage once first (`scripts/run_daemon_once.py --client-id=<id> --stages=pull`) or insert fixture rows. |
| `decision_log` RLS errors | Service-role key missing or wrong table. | Check `.env:SUPABASE_SERVICE_ROLE_KEY`. Confirm migration 001 applied. |
| Voyage 401 | Embedder API key expired. | Rotate `VOYAGE_API_KEY`. |
| Anthropic 401 | Anthropic key invalid. | Rotate `ANTHROPIC_API_KEY`. |
| Verify: `no render_draft has complete tuple` | Every contact was skipped (no approved variant for some component type). | Re-check `component_variants` seed; verify niche + offer_label on contacts match a seeded pairing. |
| Verify: `missing foundation-loop evidence for stages` | Some stage did not fire. Usually means zero input contacts reached that stage's entry status. | Check contact counts per status; adjust fixture data. |

---

## Escalation

Three acceptance-run failures in a row on the same root cause =
stop, escalate to Kirsten. Do NOT retry blindly.

---

## Automation notes

- Fully automated: preflight checks, daemon dry-run, decision_log
  evidence collection, markdown report generation.
- Not automated: the hallucination eyeball pass + the final go/no-go
  call. Both are operator-only by design; the report exposes the
  inputs the operator needs.

---

## Deviation notes (Task 17D build vs spec)

- The spec referenced a `foundation_loaded=true` or
  `memory_context_summary` key in the decision_log context, to prove
  `_prime_foundation` ran. Neither exists in the current
  `systems/base.py::load_foundation` nor in
  `systems/scout/skill.py::_prime_foundation`. The verify script uses
  the next-best signal: presence of at least one decision_log row per
  pipeline decision_type within the cycle window. Because Scout's
  `run_<stage>` gates every dispatch through `_prime_foundation` first,
  presence-of-decision implies foundation-loop-fired by code path.
  Upgrade path: add a lightweight `foundation_summary` key to
  `_prime_foundation`'s side-effect that inner stages propagate into
  their decision context. Tracked as a future prime-review item.
- `render_draft` decision context does NOT include a `draft_preview`
  key (spec asked for side-by-side draft vs raw_data). The composer
  trims the subject into the `decision` string (60 chars) and stores
  `component_tuple`, `signals_referenced`, `fills_missing`. Full
  subject + body are emitted to `outreach_drafts` ONLY when
  `dry_run=False`. The hallucination probe operates on the
  components + signals available, with the operator cross-referencing
  YAML + Supabase directly.
- Drafts-delta check is observational: in dry-run,
  `composer.persist_draft` is guarded by `if not dry_run`, so
  `outreach_drafts` never grows. The real evidence is render_draft
  decision_log rows with complete component_tuples.

---

## Change log

- v1.0 - 2026-04-23 - initial (Task 17D).
