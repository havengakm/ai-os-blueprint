# Departments

Departments are the company-level organising unit. One file per top-level department. Each manifest declares:

- Which **skills** from `/skills/` the department activates (the department's capabilities)
- Which **knowledge sources** from `/data/knowledge/` the department reads
- Which **agents** and **systems** from `/agents/` and `/systems/` run on its behalf
- **Sub-departments / Functions** as sections within the file, not folders

## Why manifests, not folders

Skills in `/skills/` are function-based and reusable across departments. A single `copywriting/generate-headlines.md` can be activated by Marketing, Sales, and Brand. Department manifests are the activation layer. This mirrors the existing `/agents/` pattern (agent = persona + skills + systems; department = team + skills + agents).

## Productised library, per-deployment activation

Your deployment can activate every department fully. Client deployments inherit the same `/skills/` library and `/rules/`, but their `/departments/` manifests activate only the subset relevant to their system. A client on a pure-outbound tier has `sales.md` populated and the others near-empty.

## File convention

```markdown
---
name: sales
owner: Kirsten
autonomy: suggest            # start low; promote per CLAUDE.md rules
display-order: 5             # how the department sorts in the company view
---

# <Department Name>

## Purpose
<one sentence>

## Sub-departments / Functions
### <function-name>
Skills:
- skills/<category>/<skill>.md
- ...
Knowledge:
- data/knowledge/<path>/
Agents / systems:
- systems/<system>/ (if applicable)

## Cross-department dependencies
- Reads output of: <other department>
- Hands off to: <other department>
```

## Creating a new department

Don't create one pre-emptively. Add a department when:

1. A real business function exists (someone, human or agent, is responsible for it).
2. There are 3+ skills that department invokes that don't fit an existing one.
3. There are clear hand-offs between it and at least one other department.

## Current departments (in display order)

| # | Department | File | Status | Purpose |
|---|---|---|---|---|
| 01 | Admin | `admin.md` | scaffolded | filesystem, naming, KB maintenance, internal comms |
| 02 | Finance | `finance.md` | scaffolded | forecasting, unit economics, pricing experiments |
| 03 | Tax | `tax.md` | scaffolded | planning, filing prep, compliance |
| 04 | Legal | `legal.md` | scaffolded | contracts, policies, compliance (draft-only) |
| 05 | Sales | `sales.md` | **active** | cold outreach, qualification, close hand-off |
| 06 | Marketing | `marketing.md` | scaffolded | content, SEO, paid acquisition, brand |
| 07 | Operations | `operations.md` | scaffolded | docs, sprints, RevOps, data, offer + positioning, GTM |

Filenames are clean (no numeric prefixes) so cross-file references stay stable. Display order lives in the `display-order:` frontmatter of each manifest and in the table above.

## 2026-04-22 refactor

Admin, Finance, Legal, Tax were previously sub-sections inside `operations.md`. They are now standalone departments. The `operations.md` manifest was narrowed to: documentation, sprints, RevOps, data + analytics, offer + positioning, market intelligence, GTM.
