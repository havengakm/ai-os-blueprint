# Analysis skills

Skills that interpret outputs — replies, scoring, outcomes, campaign performance.

## Planned skills

- `handle-reply.md` — Beacon's reply handler: classify a reply (positive / neutral / negative / opt-out), match against source decision_log entry, route to autoresponder / operator queue / DND. (Plan 2)
- `classify-objection.md` — deeper reply analysis for non-positive replies: match against Sapp's 6-objection playbook, propose the correct reframe, surface for operator approval (or auto-send if act_notify). (Plan 2)
- `explain-scoring-decision.md` — operator-facing: "why did contact X score 45 instead of 80?" walks through the fit/reach/recency/intent breakdown, shows which signals hit or missed, suggests improvements. (Plan 1 Task 17)
- `explain-composition-decision.md` — "why did Scout send this icebreaker variant instead of another?" walks through the bandit selection logic, shows win rates per variant, explains the current exploration/exploitation state. (Plan 7)
- `investigate-low-conversion-niche.md` — when a niche × offer combination has consistently poor conversion, run a diagnostic: ICP misfit? Offer misfit? Sequence issues? Component drift? (Plan 7)
- `weekly-report-narrative.md` — generate the narrative portion of the Optimizer's weekly report: top wins, top losses, proposed changes, client-level trend summary. Feeds operator dashboard. (Plan 7)
