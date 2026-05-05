---
name: sales
owner: Kirsten
autonomy: suggest
status: active
---

# Sales Department

## Purpose

Turn verified prospects into booked calls. Cold outreach through reply-handling through hand-off to human closer. Does not send contracts, does not close deals: those remain human per `feedback_voice_agent_rejected` (high-ticket calls are human-only).

## Sub-departments / Functions

### Outbound

Capabilities (atomic):
- skills/outbound/generate-outreach-angles.md
- skills/outbound/write-personalised-first-line.md
- skills/outbound/generate-cold-email.md
- skills/outbound/build-email-sequence.md
- skills/outbound/classify-replies.md
- skills/outbound/generate-reply.md
- skills/meta/validate-writing.md  # mandatory on every content-producing capability above

Composites (orchestrations):
- skills/composites/run-cold-outreach-campaign.md  # runs the 6 atomic capabilities across a lead batch

Playbooks (end-to-end, planned):
- (none yet)

Knowledge:
- data/knowledge/personal/        (Kirsten's operating principles, goals)
- data/knowledge/company/         (offer positioning, proof points, pricing)
- data/knowledge/experts/saraev/  (cold-email patterns, AI positioning)
- data/knowledge/experts/sapp/    (objection taxonomy, response patterns)

Agents / systems:
- systems/scout/  (prospecting pipeline: produces the inputs that Outbound skills consume)

Autonomy per action (inherited from agents/scout.md where applicable):
- generate-outreach-angles: draft
- write-personalised-first-line: draft
- generate-cold-email: draft
- build-email-sequence: draft
- classify-replies: act_notify
- generate-reply: draft

### Inbound
Skills: (none yet: would draw from skills/inbound/ when inbound pipeline ships)

### Qualification
Skills: (planned: skills/sales/score-leads.md, run-bant-framework.md, identify-disqualification.md)

### Enablement
Skills: (planned: skills/sales/generate-call-script.md, generate-objection-responses.md)

### Closing
Skills: (planned: skills/sales/generate-proposal.md, generate-contract-flow.md)
Note: the actual close conversation stays human. This function produces artefacts (proposals, contracts) the closer sends.

## Cross-department dependencies

- Reads output of: **Marketing** (warm-lead hand-off), **Operations** (CRM state, pipeline definitions)
- Hands off to: **human closer** (booked calls), **Customer Success** (post-close onboarding)

## Reports to
- Operator (Kirsten) via the weekly Optimizer report (planned, Plan 7)
