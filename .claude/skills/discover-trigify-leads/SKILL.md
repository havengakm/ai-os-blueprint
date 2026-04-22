---
name: discover-trigify-leads
description: "Run a Trigify discovery pass for an AIOS client. Pulls post engagers from configured monitors, qualifies by engagement threshold, produces RawCompanyContact rows, optionally pipes through PullOrchestrator. Default: daily cron via Scout daemon; operator ad-hoc OK too. Requires configure-trigify-monitors to have run first (client_config.trigify_search_ids populated). Canonical AIOS skill at skills/operations/discover-trigify-leads.md."
argument-hint: "<client-id> [--search-subset=intent|competitor|thought_leader|brand] [--max-companies=100] [--dry-run]"
allowed-tools: "Bash(uv run python scripts/run_trigify_discovery.py:*) Read(data/reports/**)"
---

# Discover High-Intent Trigify Leads

Runs a Trigify discovery pass by delegating to
`scripts/run_trigify_discovery.py`. The Python CLI owns argparse, the
Trigify pull, the optional `PullOrchestrator` handoff and the markdown
report. This skill is the operator-ergonomic entry point.

When the user invokes this skill:

1. Confirm the `client-id` and optional `--search-subset`. If the user
   hasn't specified `--dry-run`, default to a dry-run first for safety.

2. Run the discovery in dry-run mode:

   ```
   uv run python scripts/run_trigify_discovery.py --client-id=<id> --dry-run
   ```

   The CLI writes a report to `data/reports/trigify-discovery-*.md` and
   prints the path.

3. Read the generated report. Surface the summary counters
   (`leads_returned`, `by_monitor_type`) and the top-5 sample engagers to
   the user.

4. If the user confirms going live, re-run without `--dry-run`:

   ```
   uv run python scripts/run_trigify_discovery.py --client-id=<id>
   ```

   The CLI pipes the pulled contacts through `PullOrchestrator` so
   qualified rows land in the `contacts` table.

5. Summarise the final `DiscoverySummary`: `searches_queried`,
   `posts_qualified`, `engagers_extracted`, `leads_returned`, and the
   `by_monitor_type` breakdown.

## Failure modes

- `trigify_search_ids` empty → halt; point at `configure-trigify-monitors`.
- `TRIGIFY_API_KEY` unset → add to `.env`, then re-run.
- HTTP errors during pull → CLI logs them per-search; discovery continues
  on other monitors. `summary.errors` counter surfaces the total.
