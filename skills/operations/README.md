# Operations skills

Skills agents (and operators) invoke to run the system day-to-day.

## Planned skills (authored as the underlying code ships)

- `run-nightly-pipeline.md` — Scout daemon's main tick: advance all contacts through ready pipeline stages, log decisions, report tier distribution. (Plan 1 Task 16.6)
- `diagnose-stuck-contact.md` — investigate why a single contact is stalled in its current status, explain inputs that failed, propose resolution. (Plan 1 Task 17)
- `weekly-optimization-review.md` — Optimizer agent's weekly pass: analyse decision_log + outcomes, surface winners/losers per component + niche × offer, propose promotions for operator approval. (Plan 7)
- `rerun-cool-off-contacts.md` — scheduler task: identify contacts whose 90d cool-off has elapsed, re-run enrich + score_v2, assign to next round's sequence. (Plan 2)
- `pause-client.md` / `resume-client.md` — operator-invocable kill-switch + restore. (Plan 2)
- `inspect-daemon-state.md` — "what is AIOS doing right now?" — operator query that walks the in-flight queues per agent. (Plan 2)
