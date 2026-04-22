# Composites

Multi-skill chains. One composite calls two or more atomic capabilities in a defined sequence, often once per item in a batch.

## When a composite vs an atomic capability vs a playbook

| | Atomic capability | Composite | Playbook |
|---|---|---|---|
| Scope | One input, one output, one job | One orchestration of 3 to 8 capabilities | End-to-end workflow with decisions, branches, human checkpoints |
| Example | `generate-cold-email.md` | `run-cold-outreach-campaign.md` | `launch-new-niche.md` |
| Who invokes it | Anyone (agent or human) | Usually an agent or scheduler | Usually a human operator, or an agent at a specific trigger |
| Side effects | None beyond its output | Batches writes to state, queues sends | Can touch multiple systems, pause for human approval |
| Rule of thumb | Fits on one page, no branches | A sequence diagram with one path | A flowchart with branches and human gates |

If your composite has more than 8 steps, branches on more than one condition, or pauses for human approval, it is a playbook.

## File convention

Composites follow the same frontmatter shape as atomic capabilities, with:
- `tier: composite`
- `requires_skills:` listing every atomic capability the composite invokes
- `requires_tools:` listing any external tools the composite touches beyond what its called capabilities need

Body sections: Purpose, Inputs, Orchestration (not Steps), Output, Quality gate, Escalation.

## Current composites

- `run-cold-outreach-campaign.md` (populated): orchestrates the 6 outbound atomic capabilities across a batch of leads and produces send-queue-ready email sequences.

## Planned composites

- `ingest-new-lead-list.md`: pull from directory, dedupe, score, screen, enrich in one pass (chains skills from market-intelligence + outbound).
- `weekly-content-cycle.md`: plan topics, draft posts, validate, schedule (chains inbound + copywriting + brand skills).
- `nurture-cold-prospect.md`: after a soft no, re-sequence with new angle + new proof (chains outbound + market-intelligence).
