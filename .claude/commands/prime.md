# Prime — Continuous Improvement Loop

Research, implement, measure, learn, improve. Repeat forever. This is what makes the system better every week.

## The Prime cycle

```
1. RESEARCH  — What could be better?
      ↓
2. PLAN      — How to improve it? (/create-plan)
      ↓
3. IMPLEMENT — Make the change (/implement)
      ↓
4. MEASURE   — Did it work? Check metrics, decision outcomes
      ↓
5. LEARN     — Log outcome to decision_log. Update knowledge_base if new pattern found.
      ↓
6. REPEAT    — Next improvement cycle
```

## What to prime (priority order)

1. **Reply rates** — The north star. Everything serves this.
2. **Meeting booking rate** — Replies that convert to calls.
3. **Icebreaker quality** — SKIP rate should be under 5%.
4. **Screening accuracy** — Are we excluding good prospects? Including bad ones?
5. **Enrichment coverage** — What % get full data?
6. **Avatar classification** — Are contacts categorised correctly?
7. **ICP scoring weights** — Do the weights predict actual conversion?
8. **Signal freshness** — Are we using the most relevant, timely signals?
9. **Copy templates** — Which produce best reply rates?
10. **System performance** — Speed, cost, error rates

## Research sources

- **Decision log** — Which decisions led to positive outcomes? Which patterns repeat?
- **Activity log** — Open rates, reply rates, meeting rates by segment
- **Reddit/forums** — Real language from target audience (update quarterly)
- **Competitor analysis** — What are others doing differently?
- **Customer/prospect feedback** — What do replies actually say?
- **Knowledge base** — What do the experts recommend for this situation?

## Review cadence

| Frequency | What | Who |
|---|---|---|
| Daily | Check reply rates, flag anomalies (via intelligence brief) | System auto |
| Weekly (Friday) | Kill campaigns under 1% reply. Scale over 3%. Rewrite 1-3%. | Kirsten reviews |
| Fortnightly | Detailed copy analysis, A/B test results, recommendations | System generates, Kirsten acts |
| Monthly | Full funnel analysis, ICP weight review, avatar accuracy | Kirsten + system |
| Quarterly | Niche research refresh, offer positioning review, new swipe files | Kirsten leads |

## How improvements flow

```
Improvement discovered
      ↓
Check autonomy level (/decide)
      ↓
├── suggest  → Surface recommendation via Telegram. Human decides.
├── draft    → Prepare the change. Human approves.
├── act_notify → Apply the change. Notify human after.
└── autonomous → Apply, log, move on.
```

## Swipe file updates

When a new winning pattern emerges:
1. Document it in `data/knowledge/` as a new chunk
2. Embed and load into knowledge_base
3. Tag with: source, category, metrics that prove it works
4. It automatically gets retrieved for future decisions

## Anti-patterns (never do these)

- Don't change what's working just because something else might work better
- Don't A/B test more than one variable at a time
- Don't draw conclusions from less than 200 sends
- Don't auto-apply improvements without checking autonomy level
- Don't optimise for opens at the expense of replies
- Don't rewrite templates that are performing above 3% reply rate
- If an improvement causes negative outcomes, revert immediately and escalate
