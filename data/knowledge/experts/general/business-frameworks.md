# Business Frameworks — Constraints, Preferences & Decision Principles

These are non-negotiable constraints and preferences that shape every business decision. The AI OS must internalise these and apply them automatically. If a recommendation violates these, flag it.

---

## Business Constraints (non-negotiable)

### Revenue model
- **High ticket only.** No low-margin volume plays. One $5K client beats 100 $50 subscribers. Exception: low-ticket front-end products ($29-97) are fine IF they feed a high-ticket backend (AIOS retainer) or generate affiliate revenue. The low-ticket product must be a gateway, never the destination.
- **Recurring revenue first.** Monthly retainers over project fees. Predictable cash flow beats sporadic windfalls.
- **60%+ gross margins minimum.** If a client's variable costs exceed 40% of their retainer, the pricing is wrong. Fix it or fire the client.
- **Setup fees cover onboarding costs.** Never subsidise the install. The setup fee exists so day-one is profitable.

### Team structure
- **Lean by design.** Solo until 8 clients. VA at 8. Junior at 10. Full team at 15+. Never hire ahead of revenue.
- **AI does the work, humans do the thinking.** Systems handle volume. Kirsten handles strategy, relationships, and quality.
- **No office overhead until $30K MRR.** Coworking is fine. Lease is not. Keep fixed costs under $500/month as long as possible.
- **Contractors over employees (initially).** VA, junior, specialists — all contract until revenue justifies employment.

### Client model
- **4-5 clients maximum per person.** Quality over quantity. Each client gets real attention, not assembly-line treatment.
- **No client exceeds 25% of revenue.** Concentration risk kills. Diversify across niches and geographies.
- **Month-to-month contracts.** Never lock clients in. They stay because of results, not contracts.
- **Fire bad clients fast.** Scope creep, late payments, disrespect = exit. Time spent on bad clients is time stolen from good ones.

### Operations
- **One person can do everything (initially).** The AIOS makes this possible. If a process requires two people to execute, the system isn't automated enough.
- **Batch over daily.** Weekly lead pulls, weekly enrichment batches, weekly draft reviews. Not daily grind.
- **Automate before hiring.** Every repetitive task should be automated before considering a person to do it.
- **Document everything.** Every process gets an SOP. Every decision gets logged. If Kirsten gets hit by a bus, the business can still run for 30 days.

### Growth
- **Profitable from client one.** No "grow now, profit later." Every client must be margin-positive from month one.
- **Reinvest in systems, not marketing.** The system IS the marketing. Better outreach quality > more ad spend.
- **Organic over paid.** LinkedIn content, cold email, referrals. Ads are a multiplier, not a foundation.
- **SA first, then international.** Prove the model at home before scaling to bigger, more competitive markets.

---

## Business Preferences (strong defaults, can flex)

### Pricing
- **Premium positioning.** Never the cheapest option. Position on quality, intelligence, and results.
- **Value-based pricing.** Price reflects the outcome ($50K+ in pipeline), not the hours (10 hrs/month).
- **Round numbers.** $2,500/month not $2,497. $5,000 setup not $4,997. Respects the buyer.
- **No discounting the retainer.** Discount the setup fee if needed. Retainer represents ongoing value.

### Sales
- **Inbound-assisted outbound.** The cold email system creates conversations. Content creates awareness. Together they compound.
- **No proposals longer than 1 page.** The discovery call should close. If they need a 10-page proposal, they're not the right client.
- **7-14 day close cycle.** If it takes longer, they have a procurement department (not ICP) or they're not serious.
- **Founder-to-founder.** Sell to the decision maker. Never sell to a marketing manager who needs to "run it by the boss."

### Delivery
- **Results in 30 days or less.** First meetings booked within 30 days of go-live. If not, something is wrong.
- **Underpromise, overdeliver.** Promise 10 meetings. Deliver 15. Never the reverse.
- **Show, don't tell.** Loom videos, dashboards, screenshots. Not PowerPoints and promises.
- **Make the client feel smart.** They chose you. Reinforce that decision constantly with visible results.

### Technology
- **Claude (Anthropic) only.** No OpenAI, no Gemini, no open-source models. One AI provider, deep expertise.
- **Supabase for data.** PostgreSQL + pgvector. Battle-tested, scalable, affordable.
- **Railway for hosting.** Simple, GitHub-connected, persistent processes.
- **Build over buy.** Own the stack. Don't depend on vendors who can change pricing or shut down.
- **Open source over proprietary.** Prefer tools you can inspect, modify, and self-host.

### Personal
- **Work from anywhere.** No office dependency. Laptop + internet = full capacity.
- **4-day work week (target).** Monday-Thursday delivery. Friday review + planning. Weekends off.
- **Peak hours for hard work.** 10am-12pm is for revenue-generating tasks. Never waste it on admin.
- **Energy management over time management.** Match the task to the energy, not the clock.

---

## Core Principles

1. **Quality over quantity.** 10 personalised emails beat 100 generic ones. Always.
2. **Performance-first.** If it doesn't produce results, it doesn't ship.
3. **Human in the loop.** Until the system earns autonomy through proven decisions, a human reviews every action.
4. **Own your data.** Clients own their systems and data. Always. Never hold anyone hostage.
5. **Don't assume struggle.** Target growth-mode businesses, not desperate ones. Be growth-curious, not problem-aware.
6. **AI makes things profitable, not possible.** Don't sell AI as magic. Sell it as making existing processes faster, cheaper, and more consistent.
7. **The only moat is distribution.** The system that generates pipeline fastest wins. Everything else is commoditised.
8. **Consistency beats intensity.** A system that sends 200 personalised emails every day beats a human who sends 50 one week and 0 the next.

## Decision Rules

| Situation | Rule |
|---|---|
| Burn API credits? | NO. Write manual examples first. Validate direction. Then test with --limit 2. |
| Send outreach? | Only after human review on first batch. Only to contacts with verified signals. |
| Auto-update templates? | NO. Surface recommendations. Human decides all copy changes. |
| New enrichment source? | Cheapest method first. Free → $0.01/contact → $0.03/contact. Never start expensive. |
| Scale sending volume? | Only after reply rate confirmed above 3% on 200+ sends. |
| Add a system for a client? | Only after current system is delivering measurable ROI. |
| Accept a new client? | Must pass the 6-question ICP test. Must have 2,000+ addressable contacts. |

## Red Lines (never cross)

- Never send outreach without a verified buying signal or leverage match
- Never contact opted-out contacts (check before every send, every channel)
- Never hallucinate facts in outreach (every claim must exist in verified data)
- Never commit .env or credentials
- Never use Sonnet or Opus in pipeline scripts (Haiku only)
- Never auto-send on a new deployment without human review
- Three QA failures = stop, flag for human review, don't retry
