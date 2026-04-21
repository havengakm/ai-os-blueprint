# Analysis skills

Skills that interpret outputs — replies, scoring, outcomes, campaign performance.

## Planned skills (Plan 1 + 2 + 7 scope)

- `handle-reply.md` — Beacon's reply handler: classify (positive / neutral / negative / opt-out), match to source decision_log entry, route to autoresponder / operator queue / DND. (Plan 2)
- `classify-objection.md` — deeper reply analysis for non-positive replies: match Sapp's 6-objection playbook, propose the reframe. (Plan 2)
- `explain-scoring-decision.md` — operator-facing: "why did contact X score 45 instead of 80?" walk through fit/reach/recency/intent breakdown. (Plan 1 Task 17)
- `explain-composition-decision.md` — operator-facing: "why was this icebreaker variant selected?" — walks bandit selection logic + win rates. (Plan 7)
- `competitor-intel.md` — per-contact or per-niche competitor research skill Scout invokes as part of enrich. Uses Claude web-search tool to surface competitor product launches, pricing moves, positioning shifts. Informs template composition ("given competitor X moved to Y, reframe our offer as..."). (Plan 1 Task 14)
- `memory-recall.md` — cross-cutting skill: query `pattern_matcher` + `knowledge_store` for similar past decisions OR relevant expert-framework snippets for the current task. Used by Scout (composer, research module), Beacon (reply classifier), Optimizer (weekly report). Shared skill, multiple agent callers. (Plan 1 Task 16.5)
- `revenue-analysis.md` — Optimizer weekly skill: join `decision_log` × `outcomes` on `decision_id`, compute conversion rates per component × niche × offer × round, surface statistically significant winners and losers. (Plan 7)
- `ab-test-setup.md` — infrastructure skill: configure bandit parameters (epsilon, Thompson sampling prior), specify minimum sample size per variant before promotion eligibility, declare retirement thresholds. Referenced once per new variant type; not per-variant. (Plan 2 or Plan 7 — decision on timing)
- `analytics-tracking.md` — observability skill: ensure decision_log attribution tuples are complete, surface gaps (e.g., "20% of send decisions missing `niche` field last week"), alert on schema drift. (Plan 7)
- `investigate-low-conversion-niche.md` — diagnostic skill: when niche × offer combo has persistent poor conversion, run the full audit (ICP misfit / offer misfit / sequence issues / component drift / signal dry). (Plan 7)
- `weekly-report-narrative.md` — generate narrative portion of Optimizer's weekly report. Feeds operator dashboard. (Plan 7)

## Future-system skills

Authored when those systems ship. Cross-system analytics skills will reuse `memory-recall.md`, `analytics-tracking.md`, and `revenue-analysis.md` across Content OS / Ads / Landing Page OS without forking.
