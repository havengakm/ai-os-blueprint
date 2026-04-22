---
name: finance
owner: Kirsten
autonomy: suggest
status: scaffolded
display-order: 2
---

# Finance Department

## Purpose

Forecasting, unit economics, pricing experiments, margin analysis. Tracks where money comes from and where it goes, and tests pricing changes before they ship.

## Sub-departments / Functions

### Forecasting & Planning
Skills: (none yet)
Planned:
- skills/finance/forecast-revenue.md
- skills/finance/model-costs.md
- skills/finance/run-scenario-analysis.md

### Unit Economics
Skills: (none yet)
Planned:
- skills/finance/calculate-cac.md
- skills/finance/calculate-ltv.md
- skills/finance/analyse-margin.md

### Pricing Experiments
Skills: (none yet)
Planned:
- skills/finance/test-pricing.md
- skills/finance/design-discount-strategy.md

Knowledge:
- data/knowledge/company/pricing.md           (current tiers, price points)
- data/knowledge/company/proof-points.md      (client outcomes, LTV evidence)
- data/knowledge/experts/hormozi/pricing.md   (price anchoring, premium positioning, planned)

Agents / systems:
- (none yet)

## Cross-department dependencies

- Serves: **Sales** (pricing tiers, discount rules, margin floors), **Marketing** (CAC targets per channel), **Operations** (revenue forecasts feed sprint planning).
- Reads from: **Sales** (booked revenue, deal size distribution), **Marketing** (channel spend, CAC per channel).

## Autonomy rule

All pricing changes are `suggest` only. No autonomy promotion on pricing, ever. Price changes hit every future deal; cost of a mistake is too high for automated execution per CLAUDE.md "Safety Guardrails".
