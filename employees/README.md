# Employees — job-level AI specialists

Each subdirectory is a single AI Employee. Plain-language role-descriptive names (climbing names retired Slice 33).

## Roster (creative-branding vertical — CLYMB Co's deployment)

| Employee | Plain-language description | Status |
|---|---|---|
| `prospect-researcher/` | Finds and qualifies leads matching the deployment's ICP | Phase 4 (migrate from `systems/scout/`) |
| `outreach-manager/` | Sends and dispatches across channels (email, LinkedIn, SMS) | Phase 6 (build net-new) |
| `conversation-manager/` | Handles replies, runs nurture sequences, books meetings | Phase 7 (build net-new) |
| `content-writer/` | Drafts posts, emails, ad copy, marketing assets | Phase 5 (migrate from `systems/beacon/`) |

The COO (Operations Director) lives in [`/coo/`](../coo/) at top-level, not inside `employees/`.

## Per-employee structure

```
employees/<role>/
├── <role>.py                Employee runtime, .run() entry point
├── playbooks/               Mission specs (YAML or Python)
├── workflows/               Ordered skill+tool sequences for this employee
├── skills/                  Role-specific skills (atomic OR job-specific)
└── README.md
```

Every employee:
1. Reads its `daily_dispatches` row at the start of each run.
2. Executes the playbooks the COO assigned, in priority order.
3. Writes job-completion events to `employee_memory` (via foundation's `feedback_loop.publish`).
4. Writes outcome events to `decision_log.outcome` (via `feedback_loop.record_outcome`) when results arrive.

## Vertical-specific employees

Property-management vertical (Phase 10) will add: Acquisitions Researcher, Tenant Relations Manager, Maintenance Coordinator, Rent Collection Manager, Owner Reporting Specialist, Marketing Specialist. Each ships in `vertical-templates/property-management/employees/` and is provisioned per deployment.

## Status

Empty scaffold today. Phase 4+ migrations will populate the creative-branding employees.
