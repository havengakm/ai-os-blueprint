# Company Knowledge Base

Facts about the company this AIOS runs for. This deployment = Clymb.

Files migrated from `context/projects/clymb/` on 2026-04-22 because Clymb is the company itself, not a sub-project.

## Current files

### Company identity and state
- `company.md`: company overview
- `product-ecosystem.md`: the full product/service lineup
- `team.md`: team structure, roles, responsibilities

### Customer and market
- `icp.md`: ideal customer profile

### Financial
- `financials.md`: financial state, revenue, costs
- `metrics.md`: KPI snapshot

### Strategy and plans
- `strategy.md`: current strategic direction
- `business-plan.md`: full business plan

### Operational
- `operations.md`: how the company runs day-to-day
- `current-data.md`: current operational data snapshot
- `blacklist.md`: do-not-contact list (respected by outbound skills)

### Research library
- `research/competitor/competitor-landscape.md`
- `research/customer/pain-buckets-and-offers.md`
- `research/customer/reddit-agency-owners.md`
- `research/customer/reddit-all-niches.md`
- `research/customer/reddit-categorised.md`
- `research/market/dmc-niche-analysis.md`
- `research/market/google-trends.md`
- `research/market/offer-angles.md`
- `research/market/pain-points-by-niche.md`

## Skills that read from here

- Outbound skills pull ICP traits, pain points, offer angles, blacklist entries.
- Offer & Positioning skills read from research/, product-ecosystem, strategy.
- Market Intelligence skills read from research/competitor, research/market.
- Finance skills read from financials.md, metrics.md.

## Per-company silo

For a client deployment: this folder holds THAT client's company facts, not Clymb's. Zero content copies across deployments. The folder STRUCTURE (company.md, icp.md, research/, etc.) can be used as a template; the CONTENT is always per-client.

## Possible reorganisation (not done)

Some files might read more naturally elsewhere:
- `business-plan.md`, `strategy.md` → `data/plans/` (plans are plans, not standing knowledge)
- `metrics.md` → `data/outputs/` or `data/captures/` (snapshot, not stable)
- `current-data.md` → `data/captures/` (captured operational state)

Left in place for now. Move when a skill or workflow makes the case.
