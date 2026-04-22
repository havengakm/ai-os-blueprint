---
name: Configure Trigify monitors for a client's ICP
description: Interview operator for intent keywords + competitor LinkedIn URLs + thought-leader LinkedIn URLs + brand terms. Provision Trigify searches via POST /v1/searches. Store returned search_ids in client_config.trigify_search_ids. ONE-TIME per client at onboarding, OR when operator expands signal coverage. Do NOT run on every pipeline cycle — monitors persist. Explicit trigger only.
when-to-use: Client onboarding (Task 16) OR operator explicitly adding new competitors / thought leaders.
trigger: Operator invocation OR part of onboard-client.md orchestrator.
---

# Configure Trigify monitors for a client's ICP

Provision Trigify searches for a client so the Scout enrich stage can pull
behavioral signals during `/enrich`. Runs ONCE at onboarding, then only when
the operator expands signal coverage (new competitor, new thought leader,
brand misspelling discovered).

The daily discovery source adapter (Task 1.5.9b) will consume the search IDs
this skill writes.

---

## Preconditions

Before invoking, verify:

1. Client row exists in the `clients` table.
2. `client_config` row exists for this `client_id` (empty `trigify_search_ids` default is fine).
3. Migration `005_foundation_completion.sql` applied (adds `client_config.trigify_search_ids TEXT[]`).
4. `TRIGIFY_API_KEY` set in the client's `.env`.
5. Operator has Trigify workspace access for this client.

If any precondition fails: halt and report — do not attempt to create monitors.

---

## Interview

The skill walks the operator through authoring
`context/{client}/sourcing/trigify_monitors.yaml`. That YAML is operator-owned
and lives per-client (not in this repo's shared data).

For each of the four sections, prompt the operator:

### 1. Intent keywords (2-5)

> "What 2-5 intent keywords indicate a buyer for {client}'s offer?"

Examples: `"social signals"`, `"buying intent data"`, `"cold outbound that
actually works"`.

Each keyword becomes a `keyword` monitor on Trigify. Scope terms narrow the
match (per Max Mitcham webinar 2026-04-22, niche + use-case beats generic).

### 2. Competitors (3-10)

> "List 3-10 direct competitors' LinkedIn company URLs."

Each URL becomes a `company_engagement` monitor — Trigify watches engagement
on those companies' posts. Engagers are warm prospects.

### 3. Thought leaders (3-10)

> "List 3-10 thought leaders your ICP follows (LinkedIn profile URLs)."

Each becomes a `profile_engagement` monitor — same pattern, higher
authority-adjacency signal.

### 4. Brand terms + misspellings

> "What brand terms + misspellings should we monitor for own-brand engagement?"

Each becomes a `keyword` monitor. Capture misspellings (e.g. `Triggery` +
`TrggerFy`) because buyers type badly.

---

## Author YAML

Capture the answers in `context/{client}/sourcing/trigify_monitors.yaml`.
Schema (full example with comments in
`data/reference/sops/trigify-monitor-authoring.md`):

```yaml
intent_keywords:
  - phrase: "social signals"
    scope_terms: ["gtm", "outbound"]
    platforms: ["linkedin"]          # optional, defaults to [linkedin, x]
  - phrase: "buying intent data"

competitors:
  - name: "Clay.com"
    linkedin_url: "https://linkedin.com/company/clay-labs"

thought_leaders:
  - name: "Nick Saraev"
    linkedin_url: "https://linkedin.com/in/nicksaraev"

brand:
  - "Triggery"
  - "TrggerFy"
```

---

## Dry-run

Invoke `TrigifyMonitorCreator.provision_from_yaml(..., dry_run=True)`. No HTTP
calls. Surface the `dry_run_planned` list to the operator — one
`MonitorSpec` per would-be monitor, with:

- `name` — auto-built, `[{client_id}]-{type}-{slug}`
- `monitor_type` — one of `intent_keyword`, `competitor_engagement`,
  `thought_leader_engagement`, `brand_mention`
- `trigify_payload` — what gets POSTed to Trigify

Example Python invocation:

```python
import yaml
from systems.scout.sources.trigify_monitors import TrigifyMonitorCreator
from systems.scout.supabase_backends.enrich import SupabaseEnrichBackend  # or equivalent storage

client_id = "kirsten-client-zero"
yaml_path = f"context/{client_id}/sourcing/trigify_monitors.yaml"
spec = yaml.safe_load(open(yaml_path))

storage = ...  # backend implementing TrigifyMonitorStorage
creator = TrigifyMonitorCreator(storage=storage)

plan = await creator.provision_from_yaml(client_id, spec, dry_run=True)
for s in plan.dry_run_planned:
    print(s.name, s.monitor_type, s.trigify_payload)
```

Operator reviews the list. If anything looks wrong (wrong URL, wrong keyword
scope), edit the YAML and re-run the dry-run.

---

## Provision

On operator confirmation, re-invoke with `dry_run=False`:

```python
result = await creator.provision_from_yaml(client_id, spec, dry_run=False)
print("created:", result.created)
print("skipped_existing:", result.skipped_existing)
print("failed:", result.failed)
print("all_search_ids:", result.all_search_ids)
```

Expected outcome: every spec lands in either `created` or `skipped_existing`.
`failed` must be empty.

---

## Verify

Query `client_config.trigify_search_ids` and confirm:

```sql
SELECT trigify_search_ids FROM client_config WHERE client_id = '{client_id}';
```

Count must equal `len(result.created) + len(result.skipped_existing)`.

Also confirm via `GET /v1/searches` on the Trigify dashboard that every
monitor shows `[{client_id}]-...` in the name.

---

## Escalation

If `result.failed` is non-empty:

1. Do NOT retry automatically — operator inspects the error message.
2. Common causes: invalid LinkedIn URL, Trigify rejecting the payload schema,
   auth failure, rate limit.
3. Fix the YAML or the key, then re-invoke. Idempotency ensures already-
   created monitors are skipped on the retry.
4. After three failed retries, escalate to the platform owner per CLAUDE.md
   "Three QA failures = escalate to human, don't retry."

Trigify API non-2xx responses surface in `result.failed[i][1]` with the exact
status + response body (first 200 chars).

---

## Change notes

- This skill is ONE-TIME per client under normal operation. The Scout pipeline
  does NOT invoke it. Only an operator (or the `onboard-client` orchestrator)
  does.
- Adding new competitors / thought leaders later: edit the YAML, re-invoke.
  Idempotency makes this safe.
- The `description` field above is the matcher (per Max 2026-04-21 webinar
  pt2). Keep it narrow so the skill doesn't fire on every pipeline cycle.
