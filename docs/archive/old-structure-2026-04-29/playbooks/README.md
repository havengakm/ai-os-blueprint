# Playbooks — mission specifications

A **Playbook** is a YAML or Python spec defining a mission an Employee runs end-to-end. Each spec names the owner employee, the workflows it composes, success criteria, cadence, and budget.

## Spec shape

```yaml
# playbooks/cold_email_outreach.yaml
name: cold_email_outreach
owner_employee: outreach-manager
mission: |
  Run an end-to-end cold-email outbound mission against an enriched contact list.
  Includes list pull, enrichment, copy compose + QA, send dispatch, reply triage hand-off.
workflows:
  - workflows/list_pull
  - workflows/enrich_contact
  - workflows/compose_outreach
  - workflows/dispatch_send
  - workflows/handoff_to_conversation_manager  # cross-employee
success_criteria:
  - reply_rate >= 0.05
  - bounce_rate <= 0.02
cadence: continuous   # continuous | daily | weekly | on-demand
budget_per_contact_cents: 5
```

Python mirror lives in `aios/foundation/playbook_spec.py` (Phase 1+):

```python
@dataclass
class PlaybookSpec:
    name: str
    owner_employee: str
    mission: str
    workflows: list[str]
    success_criteria: list[str]
    cadence: Literal["continuous", "daily", "weekly", "on_demand"]
    budget_per_contact_cents: int | None
```

## Registration

Playbook specs are registered globally so the COO can read them and so employees can hand off into other employees' playbooks via cross-employee references.

Vertical-specific playbooks live inside `vertical-templates/<vertical>/playbooks/`. Universal playbooks (e.g. COO's `daily_dispatch`) live in this top-level directory or under their owner employee.

## Status

Empty scaffold today. First playbooks land in Phase 2 (COO's `daily_dispatch` + `weekly_recap`) and Phase 4+ (employee-specific playbooks during migration).
