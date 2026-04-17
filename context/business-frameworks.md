# Business Frameworks — Decision-Making Principles

These are the principles that guide all decisions. The AI OS should internalise these and apply them automatically.

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
