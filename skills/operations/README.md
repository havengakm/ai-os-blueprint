# Operations skills

Atomic skills for business operations: documentation, playbooks, sprint planning, task tracking. Every skill: one input → one output.

## Planned atomic skills

- `write-sop.md`
- `structure-documentation.md`
- `build-playbook.md`
- `plan-sprint.md`
- `track-tasks.md`
- `allocate-resources.md`
- `run-quality-check.md`

## Populated
None yet.

## Note on scope (previously this folder)

This folder previously scaffolded system-level RUNBOOKS for operating the AIOS itself (run-nightly-pipeline, diagnose-stuck-contact, weekly-optimization-review, rerun-cool-off-contacts, pause-client, resume-client, inspect-daemon-state). Those are multi-step procedures, not atomic skills. Their new home is `data/reference/sops/`: they get written as their owning plan tasks ship (Plan 1 Task 16.6, Plan 1 Task 17, Plan 2, Plan 7). Phase 2 of the productised AIOS plan (carving aios-scout) will own these references; see `docs/superpowers/plans/2026-05-05-phase1-foundation-extraction.md`.
