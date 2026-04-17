# CLYMB Co. — Metrics & KPI Tracking

## North Star Metrics

| Metric | Current | Target (Q2 2026) | Target (Q4 2026) |
|---|---|---|---|
| MRR | $0 | $10,000 | $30,000 |
| Active clients | 0 | 3 | 8-10 |
| Meetings booked (own outbound) | 0 | 15/month | 30/month |

---

## Revenue Metrics

| Metric | Definition | How to track | Current |
|---|---|---|---|
| MRR | Monthly recurring revenue from retainers | Stripe / manual | $0 |
| ARR | MRR x 12 | Calculated | $0 |
| Average revenue per client | Total MRR / active clients | Calculated | Target: $2,500-3,500 |
| Setup revenue | One-time setup fees collected | Stripe / manual | $0 |
| LTV | Average revenue per client x average client lifetime | Calculated | Target: $30-70K |
| Revenue per system | Revenue attributed to each system type | Tag by system | TBD |

---

## Client Economics

| Metric | Definition | Target |
|---|---|---|
| CAC (Customer Acquisition Cost) | Total sales + marketing cost / new clients acquired | Under $500 |
| LTV:CAC ratio | Lifetime value / acquisition cost | Above 5:1 |
| Payback period | Months to recoup CAC | Under 1 month |
| Churn rate (monthly) | Clients lost / total clients | Under 5% |
| Churn rate (annual) | 1 - (1 - monthly churn)^12 | Under 45% |
| Net revenue retention | Revenue from existing clients this month / last month | Above 110% (expansion) |
| Gross margin | (Revenue - direct costs) / revenue | Above 60% |

---

## Outbound Pipeline Metrics (Own + Client)

### Email Performance

| Metric | Definition | Benchmark | How to track |
|---|---|---|---|
| Emails sent/day | Daily send volume across all inboxes | 100-200 | Smartlead dashboard |
| Open rate | Unique opens / emails delivered | 40-60% | Smartlead tracking |
| Reply rate | Replies / emails delivered | 3-5% (good), 5%+ (great) | Smartlead + webhook |
| Positive reply rate | Positive replies / total replies | 40-60% of replies | Manual classification |
| Bounce rate | Bounced / emails sent | Under 2% | Smartlead |
| Unsubscribe rate | Unsubscribes / emails delivered | Under 0.5% | Smartlead + compliance_log |
| Spam complaint rate | Complaints / emails delivered | Under 0.1% | Smartlead |

### Pipeline Conversion

| Metric | Definition | Benchmark | How to track |
|---|---|---|---|
| Lead-to-reply | Replies / contacts entered pipeline | 3-5% | activity_log |
| Reply-to-meeting | Meetings booked / positive replies | 30-50% | activity_log + Calendly |
| Meeting-to-proposal | Proposals sent / meetings held | 50-70% | Manual |
| Proposal-to-close | Deals closed / proposals sent | 20-30% | Manual |
| Lead-to-close | Deals closed / contacts entered | 0.3-0.5% | Calculated |
| Time-to-reply | Hours from email sent to first reply | Track in activity_log | activity_log |
| Time-to-meeting | Days from first reply to meeting booked | Under 5 days | activity_log + Calendly |
| No-show rate | No-shows / meetings booked | Under 20% | Calendly |

### Per-Niche Tracking

| Metric | Shopify/eCom | CRO/Growth | Creative/Branding |
|---|---|---|---|
| Contacts in pipeline | | | |
| Open rate | | | |
| Reply rate | | | |
| Meeting rate | | | |
| CAC | | | |
| Best performing template | | | |
| Best performing framework | | | |

---

## Multi-Channel Metrics (Surround Sound)

| Channel | Metric | Benchmark | How to track |
|---|---|---|---|
| Email | Reply rate | 3-5% | Smartlead |
| SMS | Reply rate | 5-10% | Twilio logs |
| LinkedIn | Connection accept rate | 30-50% | Manual |
| LinkedIn | DM reply rate | 10-20% | Manual |
| Voicemail | Callback rate | 2-5% | Slybroadcast |
| Handwritten letter | Response rate | 5-15% | Manual |

---

## Ad Performance Metrics (Future - when Ads system is built)

| Metric | Definition | Benchmark |
|---|---|---|
| Ad spend | Total spent across platforms | Track per platform |
| CPM | Cost per 1,000 impressions | $5-30 depending on platform |
| CPC | Cost per click | $1-10 |
| CTR | Click-through rate | 1-3% |
| CPL | Cost per lead | Track per campaign |
| ROAS | Return on ad spend | Above 3:1 |
| CAC from ads | Ad spend / clients acquired from ads | Compare to outbound CAC |

---

## System Health Metrics

| Metric | Definition | Alert threshold |
|---|---|---|
| Enrichment coverage | % of contacts with full enrichment | Below 70% |
| Icebreaker SKIP rate | % of contacts where icebreaker was skipped | Above 10% |
| QA pass rate | % of drafts passing quality gate first try | Below 80% |
| Decision log volume | Decisions logged per day | Below 10 (system not learning) |
| Outcome backfill rate | % of decisions with outcomes recorded | Below 60% |
| Domain reputation | Smartlead deliverability score | Below 90% |
| API error rate | Failed API calls / total calls | Above 5% |
| Pipeline processing time | Time from contact import to draft generated | Above 24 hours |

---

## Weekly Scorecard Template

Track every Friday:

```
Week of: [date]
Emails sent: ___
Open rate: ___%
Reply rate: ___%
Positive replies: ___
Meetings booked: ___
No-shows: ___
Proposals sent: ___
Deals closed: ___
Revenue this week: $___
MRR: $___

Best performing:
  Niche: ___
  Template: ___
  Framework: ___
  Subject line: ___

Action items:
  Kill: [campaigns under 1%]
  Scale: [campaigns above 3%]
  Test: [new variant this week]
```

---

## Benchmarking Sources

| Source | What they provide |
|---|---|
| Nick Saraev | 4,000 leads → 19 meetings (~0.475% lead-to-meeting) |
| Smartlead benchmarks | Industry average open/reply rates |
| Own historical data | decision_log outcomes over time |
| Client performance | Per-client metrics for comparison |

---

## Cost Tracking Per Client

Track monthly to maintain 60%+ margin:

| Cost | Jan | Feb | Mar | Apr |
|---|---|---|---|---|
| Kirsten's time (hours x $50) | | | | |
| Enrichment (Anymail/Prospeo) | | | | |
| ZeroBounce verification | | | | |
| Twilio SMS | | | | |
| Slybroadcast voicemail | | | | |
| Handwrytten letters | | | | |
| **Total cost** | | | | |
| **Revenue (retainer)** | | | | |
| **Margin** | | | | |
| **Margin %** | | | | |

Alert if margin drops below 60% for any client.

<!-- This file should be updated weekly with actual numbers once campaigns are live -->
