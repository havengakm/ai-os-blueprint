# Playbooks

End-to-end workflows with decisions, branches, and usually a human checkpoint. One playbook orchestrates multiple composites and/or atomic capabilities to deliver a business outcome from start to finish.

## Playbook vs composite vs capability

| | Capability | Composite | Playbook |
|---|---|---|---|
| Steps | 1 | 3 to 8 | Many, often branching |
| Decisions | None | Linear | Branches on signals |
| Human gates | No | Rarely | Yes, at named checkpoints |
| Scope | A unit of work | A batch pass | A business outcome |
| Example | `generate-cold-email` | `run-cold-outreach-campaign` | `launch-new-niche` |

If you find yourself writing `if ... else` across steps or stopping for operator approval, you are writing a playbook. Otherwise, it is a composite.

## Why playbooks live under `skills/`

Everything the agent can invoke lives in `skills/`. Playbooks are invoked by agents or by operators at named triggers; keeping them in the skill tree makes them discoverable through the same description-matching pathway as atomic capabilities and composites.

`data/reference/sops/` remains the home for **human-facing system documentation**: deep explanations of how a system works, spec docs, deployment guides. That is reference material, not an invokable procedure.

Rule of thumb: if a future agent would invoke it from a description match, it is a playbook in `skills/playbooks/`. If a future human reads it to understand the system, it is reference in `data/reference/`. A file can be referenced from both, but it is authored for one primary audience.

## File convention

Playbooks follow the same frontmatter shape as capabilities and composites, with:
- `tier: playbook`
- `requires_skills:` every capability and composite the playbook invokes
- `requires_tools:` any external tools the playbook touches
- `human_checkpoints:` a list of named decision points where the playbook pauses for approval

Body sections: Purpose, Inputs, Triggers, Phases (not Steps or Orchestration), Decision branches, Human checkpoints, Output, Quality gate, Escalation.

## Populated playbooks

None yet. Written when the underlying composites and capabilities exist and a real end-to-end workflow repeats more than once.

## Planned playbooks

- `launch-new-niche.md`: from niche selection → ICP definition → offer-fit check → first outbound campaign → first reply cohort analysis. Multiple human checkpoints.
- `onboard-new-client.md`: provision AIOS deployment → seed context + brand + integrations → configure departments → run first Scout batch → hand off dashboard. Mostly human-approved.
- `weekly-optimisation-review.md`: pull decision-log outcomes → cluster winners/losers → propose promotions → surface to operator for approval. Runs on a schedule.
- `respond-to-inbound-lead.md`: classify form submission → score ICP fit → route to sales or nurture → trigger appropriate sequence. Runs on webhook trigger.
