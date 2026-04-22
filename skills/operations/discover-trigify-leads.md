---
name: Discover high-intent leads via Trigify social listening
description: Pull lead engagers from pre-configured Trigify monitors (intent keywords + competitor engagement + thought-leader engagement + own-brand mentions). Qualify posts by engagement threshold (default 10 likes). Extract engagers, build RawCompanyContact rows with engager info in raw_data, pipe to PullOrchestrator. Run daily at 02:30 client-tz by Scout daemon, OR operator-invoked ad-hoc. Do NOT invoke if client_config.trigify_search_ids is empty — operator must run configure-trigify-monitors first. Skip posts below engagement threshold — they'll cook and qualify on a future run. Subset the search by passing --search-subset=intent|competitor|thought_leader|brand.
when-to-use: Scout daemon daily cron (Task 16.6) OR operator ad-hoc discovery pass.
trigger: Scout daemon `02:30 client-tz` OR operator invocation via `/discover-trigify-leads <client-id>`.
---

# Discover high-intent leads via Trigify social listening

Pull engagers from pre-configured Trigify monitors and hand them to the Scout
pull stage as `RawCompanyContact` rows. Runs daily as part of the Scout
daemon, or ad-hoc when the operator wants an on-demand discovery pass.

The companion skill `configure-trigify-monitors` provisions the monitors this
one consumes. This skill is PULL-ONLY — it never creates monitors.

---

## Preconditions

Before invoking, verify:

1. Monitors provisioned via `configure-trigify-monitors` (Task 1.5.9a).
2. `client_config.trigify_search_ids` populated (TEXT[] non-empty).
3. `client_config.trigify_discovery_config` exists (migration 009 sets the
   default JSONB — per-client overrides are operator-tunable).
4. `TRIGIFY_API_KEY` set in the client's `.env`.
5. Migration `009_trigify_discovery_config.sql` applied.

If `trigify_search_ids` is empty: halt with an operator-facing message
pointing to `configure-trigify-monitors` — do NOT attempt discovery.

---

## Execution

Invoke `TrigifyDiscoverySource.pull()` with:

- `client_id` — required
- `max_companies` — caller cap (default 100; combined with per-client
  `max_leads_per_run` via `min(...)`)
- `dry_run` — `True` for read-only preview; False for the full run (default
  False — all GETs are free regardless)
- `search_subset` — optional: one of `"intent"`, `"competitor"`,
  `"thought_leader"`, `"brand"`. When absent, all enabled subsets fire.

```python
from systems.scout.sources.trigify_discovery import TrigifyDiscoverySource

source = TrigifyDiscoverySource(storage=discovery_storage)
contacts = await source.pull(
    client_id=client_id,
    max_companies=100,
    dry_run=False,
    search_subset=None,  # or "intent" etc.
)
summary = source.last_summary
```

Per Max Mitcham webinar 2026-04-22 defaults (migration 009):
- `min_engagement_to_pull = 10` — posts below threshold are skipped so they
  "cook" and qualify on a future run.
- `cook_time_hours = 24` — emergent from the daily cadence, no explicit timer.
- `max_leads_per_run = 100`.
- `search_subsets_enabled = ["intent","competitor","thought_leader","brand"]`.

Overrides go in `client_config.trigify_discovery_config` JSONB. Partial
overrides are supported (missing keys inherit defaults).

---

## Output

`pull()` returns `list[RawCompanyContact]` for the pull stage. The
`PullOrchestrator.run()` contract (Task 9d) handles cross-source +
cross-run dedup + persistence, and emits its own `source_selection`
decision_log entries.

Each `RawCompanyContact` carries engager info in `raw_data`:

```json
{
  "engager_linkedin_url": "https://linkedin.com/in/jane-doe",
  "engager_name": "Jane Doe",
  "engager_title": "VP Marketing",
  "post_id": "trigify_post_id",
  "post_url": "https://linkedin.com/posts/...",
  "post_topic": "social signals",
  "post_engagement_total": 42,
  "monitor_type": "intent_keyword",
  "monitor_search_id": "sid-abc",
  "engaged_at": "2026-04-21T14:30:00Z"
}
```

`company` = engager's employer (required; engagers without determinable
employer are skipped + logged to `decision_log` with
`decision=engager_skipped:no_employer`).

Identity lookup (Task 9.5) resolves `raw_data.engager_linkedin_url` into a
contact row — that integration is a follow-up backlog item, not this task.

---

## Summary

`source.last_summary: DiscoverySummary` exposes counters:

- `searches_queried` — monitors that returned results
- `posts_scanned` — total posts inspected
- `posts_below_threshold` — skipped, will cook
- `posts_qualified` — ≥ threshold, engagers pulled
- `engagers_extracted` — raw engagers returned by Trigify
- `engagers_skipped_no_employer` — couldn't determine employer
- `leads_returned` — final `RawCompanyContact` count
- `errors` — HTTP errors across searches/posts (non-fatal; run continues)
- `by_monitor_type` — `{monitor_type: lead_count}` for Plan 7 attribution

When invoked with `--dry-run`, write a summary to
`data/reports/trigify-discovery-{timestamp}.md` for operator review.

---

## Escalation

Any single search returning 0 results across 7+ consecutive runs → flag the
monitor for operator review (likely stale or mis-configured). That detection
logic belongs to the Scout daemon's weekly prime loop, not this skill.

Three consecutive pulls with HTTP errors > 50% of searches → escalate to
operator (potential API outage or auth issue).
