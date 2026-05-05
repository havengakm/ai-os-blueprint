---
name: tax
owner: Kirsten
autonomy: suggest
status: scaffolded
display-order: 3
---

# Tax Department

## Purpose

Tax planning, filing preparation, compliance. Separate from Finance because tax has distinct jurisdictions, deadlines, and professional-advice requirements; separate from Legal because it is quantitative, not contractual.

## Sub-departments / Functions

### Tax Planning
Skills: (none yet, no dedicated `skills/tax/` category exists yet)
Planned draws from adjacent categories:
- skills/finance/analyse-margin.md       (pre-tax profit visibility)
- skills/finance/run-scenario-analysis.md (tax-impact scenarios)

### Filing Preparation
Skills: (none yet)
Candidate new skills to author when needed:
- skills/tax/classify-expense.md         (categorise transactions to tax buckets)
- skills/tax/prepare-filing-pack.md      (assemble document pack for accountant)
- skills/tax/track-deadlines.md

### Compliance
Skills: (none yet)
Planned:
- skills/legal/check-gdpr-compliance.md  (data-handling tax obligations)
- Candidate: skills/tax/check-vat-registration.md, skills/tax/check-withholding-rules.md

Knowledge:
- data/knowledge/personal/   (jurisdictions, fiscal year, accountant contact)
- data/knowledge/company/    (registered entities, VAT IDs, tax residency)

Agents / systems:
- (none yet)

## Cross-department dependencies

- Reads from: **Finance** (margin + revenue data), **Admin** (receipts + expense tracking), **Legal** (entity structures, jurisdictional exposure).
- Hands off to: human accountant or tax advisor. Never auto-files.

## Autonomy rule

Every tax output is `suggest` or `draft` only. No autonomous filing, no autonomous tax decisions. Tax skills exist to assemble and classify; a human accountant signs off before anything leaves the business.

## Note: skills/tax/ category

A dedicated `skills/tax/` folder is NOT in the initial 15-category taxonomy. Create it only when 3+ atomic tax skills exist. Until then, this department activates a curated subset of `skills/finance/` and `skills/legal/`.
