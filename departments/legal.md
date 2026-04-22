---
name: legal
owner: Kirsten
autonomy: suggest
status: scaffolded
display-order: 4
---

# Legal Department

## Purpose

Contracts, policies, compliance checks. Every output is a DRAFT. Legal skills exist to accelerate human review, not to replace it.

## Sub-departments / Functions

### Contracts
Skills: (none yet)
Planned:
- skills/legal/generate-contract.md
- skills/legal/generate-nda.md

### Policies
Skills: (none yet)
Planned:
- skills/legal/generate-terms.md
- skills/legal/generate-privacy-policy.md

### Compliance
Skills: (none yet)
Planned:
- skills/legal/check-gdpr-compliance.md
- skills/legal/check-email-compliance.md

Knowledge:
- data/knowledge/personal/   (jurisdictions, entity info)
- data/knowledge/company/    (services scope, standard terms, pricing)

Agents / systems:
- (none yet)

## Cross-department dependencies

- Serves: **Sales** (contracts, NDAs for deals), **Marketing** (privacy policy, email compliance for lead capture), **Tax** (entity structures, jurisdictional exposure), **Operations** (employment agreements, vendor contracts).
- Hands off to: human counsel for review. No legal output ships without human approval.

## Autonomy rule

Every legal skill runs at autonomy level `suggest` or `draft`. No autonomy promotion permitted. Legal outputs are never auto-sent. Per CLAUDE.md "Hard rules": three QA failures on a legal draft flag for human review immediately.

## Note on email compliance

`skills/legal/check-email-compliance.md` is a prerequisite for the Sales department's outbound sequences when operating in GDPR/CAN-SPAM/CCPA jurisdictions. Sales manifest should reference it explicitly once authored.
