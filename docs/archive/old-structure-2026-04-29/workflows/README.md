# Workflows — ordered sequences of skills + tools

A **Workflow** is a chained sequence that produces a measurable outcome. Workflows are the layer between Playbooks (missions) and Skills (atomic capabilities).

This directory replaces the old `skills/composites/` (renamed Slice 33).

## Shape

```python
# workflows/compose_outreach.py
async def run(contact: dict, deployment_config: dict) -> ComposeResult:
    """Compose-then-validate-then-persist outreach for one contact.

    Skills used:
        skills.outbound.cold_email_compose  — LLM call with deployment-specific tone
        skills.meta.validate_writing        — guardrails (em-dash, AI-clichés, founding-year, etc)

    Tools used:
        tools.api_clients.anthropic         — LLM API client
        tools.validators.writing_validator  — pure-Python validator
    """
    ...
```

## Job-completion contract

Every workflow that produces a measurable artifact (a sent email, a generated icebreaker, a published post, a captured reply) must call `feedback_loop.publish(client_id, employee_id, kind, content)` at completion. This writes to `employee_memory` AND to `learning_events` for subscribed employees. See `aios/foundation/feedback_loop.py`.

## Cross-employee workflows

Workflows that span employees (e.g. `handoff_to_conversation_manager`) live here at the top level. Single-employee workflows live under that employee's directory: `employees/<role>/workflows/`.

## Status

Empty scaffold today. First workflows land in Phase 2 (COO's `observe_team`, `synthesise_status`) and Phase 4+ (per-employee workflows during migration).
