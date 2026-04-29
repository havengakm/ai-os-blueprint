# COO — Operations Director

Head-manager AI. One COO per deployment. Coordinates all employees via two cadences:

- **Daily 6am client-local** — `daily_dispatch` playbook runs, writes one `daily_dispatches` row per active employee.
- **Weekly Sunday 7pm client-local** — `weekly_recap` playbook runs, writes one `weekly_recaps` row.

Plus an always-on **decision feedback loop**: every job completion + outcome arrival fires a learning event. The COO observes those events and routes them to subscribed employees' vector memory so the team learns from each other in real time.

## Layout

```
coo/
├── coo.py                         Employee runtime, .run() entry point
├── playbooks/
│   ├── daily_dispatch.py          Reads decision_log + employee_memory recent activity per employee, generates per-employee task brief, writes daily_dispatches row
│   └── weekly_recap.py            Reads dispatches + outcomes from past week, generates synthesis, writes weekly_recaps row, emits learning_events
├── workflows/
│   ├── observe_team.py            Read from employee_memory + decision_log
│   └── synthesise_status.py       LLM-summarise + KPI-aggregate
├── skills/
│   ├── synthesise_team_status.py  LLM call with structured output
│   └── score_priority.py          Rank tasks for an employee
└── README.md (this file)
```

## Output shape

Both playbooks write structured JSON so Slack + Web App can render without re-parsing:

```python
DispatchPayload = {
    "narrative": str,
    "tasks": [{"playbook": str, "priority": int, "rationale": str}],
    "kpis": dict,
    "alignment_text": str,
}

RecapPayload = {
    "synthesis": str,
    "kpis": dict,
    "decisions_for_next_week": [{"decision": str, "rationale": str, "owner_employee": str}],
}
```

## Status

Phase 2 of the structural rewrite. Empty scaffold today. Build kicks off after Phase 1 (foundation extensions) lands.
