# CLYMB Co. — Operations & Service Delivery

---

## Service Delivery Process

### Client Lifecycle

```
Lead → Discovery Call → Proposal → Signed → Onboarding → Go-Live → Retainer → Growth → (Handover or Renewal)
```

### Weekly Client Touchpoints

| Touchpoint | When | What | Time |
|---|---|---|---|
| Intelligence brief | Daily (auto) | Pipeline status, replies, signals | 0 min (automated) |
| Draft review | As needed | Approve/reject outreach drafts via Telegram | 5-10 min |
| Weekly report | Monday morning (auto) | Performance metrics, trends, recommendations | 0 min (automated) |
| Friday review | Friday (Kirsten) | Kill underperformers, scale winners, plan next week | 15-30 min per client |
| Monthly strategy call | Monthly | Review results, plan next system, adjust ICP | 30-45 min |

### Time Allocation Per Client

| Tier | Weekly hours | Monthly hours | What |
|---|---|---|---|
| Starter | 2-3 hrs | 8-12 hrs | Monitoring, optimisation, draft review |
| Growth | 3-4 hrs | 12-16 hrs | Above + building new system |
| Scale | 4-5 hrs | 16-20 hrs | Above + multiple systems + strategy |

---

## Capacity Planning

### Solo operator (current)

| Clients | Weekly hours | Viable? |
|---|---|---|
| 1-3 | 6-12 hrs | Easy. Lots of development time. |
| 4-5 | 12-20 hrs | Comfortable. Peak capacity for quality. |
| 6-7 | 18-25 hrs | Stretched. Quality may dip. Need VA. |
| 8+ | 24+ hrs | Unsustainable solo. MUST hire. |

### With VA (from 8 clients)

VA handles: admin, scheduling, data entry, basic monitoring, client comms
Kirsten handles: strategy, system building, optimisation, sales

| Clients | Kirsten hours | VA hours | Total |
|---|---|---|---|
| 8-10 | 20-25 hrs/week | 15-20 hrs/week | 35-45 hrs |
| 11-15 | 25-30 hrs/week | 20-25 hrs/week | 45-55 hrs |

### With junior (from 10 clients)

Junior handles: routine system builds, monitoring, first-line troubleshooting
Kirsten handles: strategy, complex builds, client relationships, sales

---

## Quality Standards

### Outreach quality
- Icebreaker SKIP rate: under 5%
- QA pass rate (first attempt): above 80%
- Email deliverability: above 95%
- Bounce rate: under 2%
- Spam complaint rate: under 0.1%

### Client satisfaction
- Weekly report sent every Monday (never miss)
- Reply to client Telegram within 4 hours during business hours
- Monthly strategy call never cancelled by us
- First draft batch within 14 days of go-live (after warmup)

### System performance
- Pipeline processes overnight (leads → drafts ready by morning)
- Decision log capturing 10+ decisions per client per day
- Autonomy promotion reviewed quarterly

---

## Tools Stack

| Category | Tool | Cost | Who pays |
|---|---|---|---|
| AI Runtime | Claude API (Haiku + Sonnet) | Variable | Client |
| Database | Supabase | $0-25/mo | Client |
| Hosting | Railway | $5-20/mo | Client |
| Email sending | Smartlead | $39-97/mo | Client |
| Email hosting | Zoho Mail | $10-20/mo | Client |
| DNS | Cloudflare | Free | Client |
| Workflows | n8n (self-hosted on Railway) | $0 | Included in hosting |
| Communication | Telegram | Free | Both |
| Calendar | Calendly | Free-$12/mo | Client |
| Embeddings | Voyage AI | ~$1/mo | Kirsten (shared) |
| Enrichment | Anymail Finder / Prospeo | Variable | Kirsten (rebilled 2.5x) |
| Verification | ZeroBounce | Variable | Kirsten (rebilled 2.5x) |
| SMS | Twilio | Variable | Kirsten (rebilled 2.5x) |
| Code | GitHub (private repos) | Free | Kirsten |
| Project tracking | ClickUp / Notion (future) | $0-10/mo | Kirsten |

---

## Risk Management

### Deliverability risk
- Minimum 3 sending domains per client
- 14-21 day warmup before any sending
- Domain reputation monitored via Smartlead
- If domain burns: rotate to backup domain within 24 hours
- Never exceed 50 emails/inbox/day

### Data risk
- Separate Supabase instance per client (complete isolation)
- RLS enabled on all tables
- No cross-client data access
- API keys stored in .env (never committed)
- Client owns their data at all times

### Operational risk
- All processes documented in SOPs
- Client deployment SOP ensures repeatable setup
- Decision log captures institutional knowledge
- If Kirsten is unavailable: system continues running (autonomous operations)
- Emergency: system can be paused via Smartlead dashboard

### Client concentration risk
- No client should exceed 25% of total revenue
- Diversify across niches and geographies
- Retainer model (not project) reduces revenue volatility

---

## Legal Considerations

### Contracts needed:
- [ ] Master Service Agreement (MSA)
- [ ] Data Processing Agreement (DPA) — GDPR/POPIA compliance
- [ ] Service Level Agreement (SLA) — uptime, response times
- [ ] Non-Disclosure Agreement (NDA) — mutual
- [ ] Handover Agreement — terms for full transfer

### Compliance:
- CAN-SPAM (US): unsubscribe mechanism, physical address, no deceptive headers
- GDPR (EU/UK): legitimate interest basis for B2B outreach, DPA required
- CASL (Canada): implied consent for B2B, unsubscribe required
- POPIA (South Africa): legitimate interest, opt-out mechanism
- All outreach must include unsubscribe option
- Opted-out contacts must NEVER be contacted again (enforced by system)

<!-- TODO: Get contracts reviewed by a lawyer -->
<!-- TODO: Set up proper invoicing (Stripe or manual) -->
<!-- TODO: Business registration / tax setup -->
