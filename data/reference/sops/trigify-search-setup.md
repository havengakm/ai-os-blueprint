# SOP: Trigify Search Setup (Per-Client Playbook)

**Scope:** Plan 2 operator task. Listed here now (end of "Real-Copy MVP Setup") so Client Zero's searches are already documented when Plan 2 begins. Not part of the MVP test — the MVP runs without Trigify hits, Tier-4 fallback handles everything.

## Purpose

Configure a client's Trigify searches so that the enrich pipeline's IcebreakerAdapter can fire Tiers 1, 2, and the Trigify-adjacent parts of Tier 3 (e.g. leadership-change posts). Without these, every contact degrades to Tier 4 (website citation) and loses the highest-performing icebreaker path.

## Owner

Operator (Kirsten for Client Zero; per-client operator for future deployments).

## Trigger

Any of:
- Client has just completed onboarding.
- Client has added new competitors, thought leaders, or intent topics to their ICP.
- A quarterly Trigify review finds searches that haven't produced hits in 30+ days.

## Inputs

- Client's ICP (from `context/{client_id}/icp.md`)
- Client's competitor list (3-5 named competitors)
- Client's thought-leader list (3-5 LinkedIn profile URLs)
- Client's intent keywords (5-10 topic phrases their ICP would post about)
- Trigify account + API key (shared across deployments for now; per-client in future)
- Supabase access (to write `client_config.trigify_search_ids`)

## Outputs

- 5-10 Trigify searches saved with distinctive names (format: `{client_id}:{search_type}:{slug}`)
- `client_config.trigify_search_ids` populated with the search IDs
- First-hit validation: at least one search returns ≥1 result within 24h of creation

## Steps

### 1. Pick the 4 search types (Hans/Max Trigify webinar pattern)

Per the webinar (2026-04-21, archive: `memory/reference_cold_email_stack_reference.md`), set up ONE of each type per client:

1. **Intent-based keyword searches (2-4 searches)**: topics the client's ICP would post about when experiencing the pain the client solves.
2. **Competitor-mention searches (1 per competitor, 3-5 total)**: anyone posting about a named competitor. LLM-classified at pipeline-time for sentiment — frustrated → Tier 1, neutral → Tier 2.
3. **Thought-leader engagement searches (1 per thought leader, 3-5 total)**: anyone engaging with a named industry authority's posts.
4. **Own-brand monitor (1)**: anyone engaging with the client's own LinkedIn posts.

Total: roughly 8-13 searches per client. Trigify pricing is pay-as-you-go; this fits inside Plan 2 MVP budget.

### 2. Author each search in the Trigify UI

For each search, set:
- **Search name:** `{client_id}:{search_type}:{slug}` (e.g. `kirsten-client-zero:intent:founder-led-sales`)
- **Platforms:** LinkedIn (primary), Reddit (secondary), YouTube/podcasts (tertiary)
- **Author filters:** decision-maker titles from the client's ICP (CEO, Founder, MD, Principal, Partner, CMO, Head of Marketing, etc.)
- **Keyword filters:** joined where relevant (e.g. "Apollo" AND "data enrichment" NOT "hiring") to narrow
- **Language:** English only (unless client serves non-English markets)

### 3. Save search IDs to `client_config.trigify_search_ids`

```sql
UPDATE client_config
SET trigify_search_ids = ARRAY[
  'search-id-intent-founder-led-sales',
  'search-id-intent-pipeline-referrals',
  'search-id-competitor-apollo',
  'search-id-competitor-instantly',
  'search-id-tl-sap-webinar',
  'search-id-own-brand-monitor'
]::TEXT[]
WHERE client_id = '{client_id}';
```

### 4. First-hit validation

- Wait 24h.
- Query Trigify for each search's result count.
- If any search returns 0 hits, tune the filters (keywords too narrow, or author filter too restrictive).

### 5. Per-pipeline-run behavior

The enrich orchestrator passes `trigify_search_ids` to the Trigify adapter via `contact["trigify_search_ids"]`. The adapter queries each search, filters to contacts matching the current prospect (profile > domain > name), and writes `trigger_events[]` to `research_data`. The IcebreakerAdapter (Tier 1/2) then reads `trigger_events` and picks the most recent/relevant one.

## QA

- After first live run: query `decision_log` for `enrich_contact:trigify:*`. Expect at least one `matched` result per 3-5 contacts.
- Weekly check: `icebreaker_tier` distribution in `decision_log.context`. Healthy distribution is roughly 20% Tier 1+2, 30% Tier 3, 50% Tier 4. Tier-4 dominance means Trigify searches need tuning.

## Error handling

| Symptom | Likely cause | Fix |
|---|---|---|
| No hits across any search for 72h | Keyword filters too narrow OR author filter too restrictive | Loosen filters; broaden keyword alternatives; reduce author filter to just top decision-maker titles |
| High hit count but 0 matched contacts | Profile/domain/name mismatch — contacts aren't in the Trigify author pool | Accept: Trigify is probabilistic. Focus on high-ICP contacts who are likely to appear. |
| Tier 1 fires but icebreakers feel off | Frustration-keyword regex false-positive (e.g. "pain point" treated as pain) | Tune the `_FRUSTRATION_PATTERN` in `systems/scout/enrich/icebreaker_adapter.py` or add the competitor-post context to the prompt. |
| Trigify budget consumed faster than expected | Monitor count too high OR unfiltered queries catching too much | Remove redundant competitor searches; tighten keyword joins; batch-process the daily cron instead of per-contact-at-enrich-time. |

## Escalation

If a Trigify search produces hits but none land in outreach after 30 days, escalate to:
1. Plan 1.5 cost audit (is Trigify cost justified given the lift?)
2. Plan 7 weekly optimizer (is the hit-rate trending up or down quarter-over-quarter?)

## Automation

For Plan 2: a per-client Trigify config YAML under `data/reference/trigify/{client_id}.yaml` can declare the 4 search types + parameters, and a loader script can create/update searches via Trigify API. Not in scope for MVP — start with manual UI setup and one hand-written SQL update.
