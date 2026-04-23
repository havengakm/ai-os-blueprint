# SOP: Component Variant Authoring
Version: 1.0
Last reviewed: 2026-04-23
Owner: Kirsten / VA

## Purpose

Author and ship component variants for the six types the Composer bandits over: `subject_line`, `icebreaker`, `pain_hook`, `offer_frame`, `cta`, `signature`. Variants live as YAML files under `data/reference/sequences/{niche}/components/{component_type}/` and sync into the `component_variants` table via [scripts/load_components.py](../../../scripts/load_components.py).

Composer picks variants using epsilon-greedy selection (default ε=0.1). Approved variants with higher `win_rate` win more often; a slice of traffic always explores newer variants.

## Trigger

- Adding a new (niche, offer) pair to a client deployment.
- Adding a new variant to an existing (niche, offer) so the bandit has something fresh to explore.
- Replacing a "bootstrap placeholder" variant with production copy.

## Inputs

- Niche slug (snake_case), e.g. `cro_growth_ugc_agency`.
- Offer label (snake_case), e.g. `pipeline_audit`.
- Component type: one of `subject_line | icebreaker | pain_hook | offer_frame | cta | signature`.
- Expert framework anchor for the scorecard (e.g. Hormozi value-stack, Saraev-signal-first).
- A real sample contact row to test placeholder resolution against.

## Outputs

- One YAML file per variant at `data/reference/sequences/{niche}/components/{component_type}/{variant_key}.yaml`.
- A `component_variants` row per variant after sync, with `status = 'draft'` until promoted.

---

## Directory layout

```
data/reference/sequences/
└── {niche}/
    └── components/
        ├── subject_line/
        │   ├── v1_question_hook.yaml
        │   └── v2_numbers_hook.yaml
        ├── icebreaker/
        ├── pain_hook/
        ├── offer_frame/
        ├── cta/
        └── signature/
```

One file per variant. `variant_key` is the YAML-author-controlled stable handle (snake_case, includes a version prefix like `v1_` for easy iteration).

## YAML schema

Mirror the structure at [data/reference/sequences/cro_growth_ugc_agency/components/subject_line/v1_question_hook.yaml](../../../data/reference/sequences/cro_growth_ugc_agency/components/subject_line/v1_question_hook.yaml).

```yaml
---
variant_key: "v1_question_hook"            # stable handle, snake_case
component_type: "subject_line"             # must match enum (see below)
niche: "cro_growth_ugc_agency"             # snake_case niche slug
offer_label: "pipeline_audit"              # snake_case offer slug
variant_content: |
  quick question about {{company_name}}'s {{pain_hook_reference}}
status: "draft"                            # draft | approved | paused | killed
metadata:
  author: "Kirsten"
  notes: "rationale, what this variant tests"
  framework_anchor: "Hormozi curiosity-gap"
ab_epsilon: 0.1                            # per-variant override (optional, default 0.1)
```

### `component_type` enum (CHECK constraint)

Must be exactly one of (see [scripts/sql/006_component_registry.sql](../../../scripts/sql/006_component_registry.sql)):

```
subject_line | icebreaker | pain_hook | offer_frame | cta | signature
```

Typo = CHECK violation on sync.

### `status` lifecycle

```
draft      → variant authored, not yet bandit-eligible on prod
approved   → bandit picks from the approved pool
paused     → temporarily excluded from selection
killed     → permanently retired; row stays for attribution history
```

New variants START at `draft`. Promotion to `approved` is a separate, deliberate step (see "How variants flow into the bandit" below).

---

## Placeholder conventions

Placeholders use Handlebars-style `{{placeholder_name}}`. Valid placeholder names depend on component type. The composer's research selector fills them from the contact's enriched data.

| Component type | Valid placeholders |
|---|---|
| `subject_line` | `{{company_name}}`, `{{pain_hook_reference}}`, `{{first_name}}` |
| `icebreaker` | `{{specific_observation}}`, `{{trigger_event_reference}}`, `{{first_name}}` |
| `pain_hook` | `{{key_pain_point}}`, `{{buying_signal_reference}}`, `{{company_size_band}}`, `{{conversion_stage_reference}}` |
| `offer_frame` | `{{offer_name}}`, `{{time_commitment}}`, `{{specific_outcome}}`, `{{niche_label}}` |
| `cta` | `{{calendar_link}}`, `{{reply_prompt}}` |
| `signature` | `{{operator_name}}`, `{{operator_title}}` |

A variant that references a placeholder not in the contact's research data will be skipped at compose time with `ComposerSkip(reason='placeholder_missing')`. Enrich the contact first, then retry compose.

---

## Writing rules

Every variant MUST pass the global writing guardrails. Reference: `rules/global-writing-guardrails.md` (bookmark; full rules authored in a later task). Until that file lands, enforce these hard rules manually:

- No em dashes. Use commas, colons, parentheses, or short sentences.
- No buzzwords (leverage, synergy, seamless, robust, game-changing, actionable insights, best-in-class, etc.).
- Outbound copy stays under 75 words total per send (subject + body).
- Plain words. Active voice. No vague openers ("I hope this finds you well").
- No hallucinated facts. Every specific claim must be fillable from verified research data, not baked into the template.

Run [skills/meta/validate-writing.md](../../../skills/meta/validate-writing.md) (when present) on every variant before promoting to `approved`.

## Offer-score scorecard

Per `feedback_offer_score_framework.md`: every variant scores against a 27-constraint scorecard. Target is 5/5 on every constraint.

Score against `data/knowledge/experts/hormozi/offer-scorecard.md` (when present) or the operator's internal offer scorecard. Attach the per-constraint score in `metadata.scorecard` before promoting:

```yaml
metadata:
  author: "Kirsten"
  notes: "..."
  framework_anchor: "Hormozi value-stack"
  scorecard:
    specificity: 5
    quantified_deliverable: 5
    time_commitment: 5
    risk_reversal: 4       # <-- flag: below target, iterate before promotion
    # ... remaining 23 constraints
```

Below-target constraints = iterate before promotion. Do not promote a variant scoring below 5/5 without a documented reason in `metadata.notes`.

---

## How variants flow into the bandit

1. Operator authors YAML under `data/reference/sequences/{niche}/components/{type}/`.
2. Operator runs `uv run python scripts/load_components.py --client-id=<id> --dry-run` to preview.
3. Sync writes: `uv run python scripts/load_components.py --client-id=<id>`.
4. Row lands with `status = 'draft'`. Composer DOES include drafts during the Plan 1 warm-up, but promotion to `'approved'` is the signal that a variant has passed the scorecard + validate-writing checks.
5. Promotion is a Supabase write (operator-scoped): `UPDATE component_variants SET status='approved' WHERE id='...'`. Wrap this in a skill once the client-config skill layer lands.
6. Composer picks approved variants via epsilon-greedy. Default ε=0.1 (10% exploration). Override per-variant via `ab_epsilon` in the YAML.

---

## QA

Before promoting any variant to `approved`:

1. **Dry-run sync passes:** `uv run python scripts/load_components.py --client-id=<id> --dry-run` reports zero errors.
2. **Placeholders resolve:** compose against a real enriched contact sample; no `ComposerSkip(reason='placeholder_missing')`.
3. **Writing guardrails pass:** manual check against the hard rules above (until `validate-writing` skill lands).
4. **Scorecard 5/5:** per the offer-score framework, or documented justification for any below-target.
5. **Framework anchor named:** `metadata.framework_anchor` populated.

After sync, confirm the row exists:

```sql
SELECT id, variant_key, status, niche, offer_label
FROM component_variants
WHERE client_id = '<client-id>'
  AND component_type = '<type>'
  AND variant_key = '<key>';
```

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `CHECK constraint violation: component_type` | Typo in `component_type` field. | Must be exactly: `subject_line`, `icebreaker`, `pain_hook`, `offer_frame`, `cta`, `signature`. |
| `variant_content empty / NOT NULL violation` | YAML parse error (indentation under `variant_content: |`). | Ensure the block-scalar body is indented under the `|`. |
| `ComposerSkip(reason='placeholder_missing')` | Placeholder in variant not present in contact's research data. | Enrich the contact first, or edit the variant to only reference placeholders always available. |
| `UNIQUE violation on (client_id, niche, offer_label, component_type, variant_key)` | Two YAMLs share the same `variant_key` under the same (niche, offer, type). | Rename the new variant's key (e.g. bump the `v2_` prefix). |
| Sync reports zero variants loaded | Sequences root empty or wrong `--root` path. | Check `data/reference/sequences/{niche}/components/` is populated; default root is `data/reference/sequences/`. |

## Escalation

- Three consecutive placeholder-missing skips on the same variant: retire the variant (set `status='killed'`) or fix the placeholder set.
- Scorecard constraint repeatedly below 5 across multiple variants in the same niche: escalate to `/prime` review; the niche's framework anchor may be wrong.
- Sync error on a live client deployment mid-campaign: do not hot-patch. Author the fix, dry-run, promote in the next scheduled sync.

## Automation notes

- **Fully automated:** YAML-to-DB sync (preserves learned `win_rate` + `sample_size` per Item-62 invariant), variant selection at compose time.
- **Operator-driven:** variant authoring (judgment-heavy), promotion from `draft` to `approved` (QA gate).
- **Not automated:** offer scorecard scoring itself (done by operator against the scorecard knowledge base).

## Change log

- v1.0, 2026-04-23, initial (Task 18).
