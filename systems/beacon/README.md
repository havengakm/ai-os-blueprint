# Beacon

**Plain-name labels (operator-facing):** Outreach Manager (send) + Conversation Manager (reply runtime).

**Climbing-name (code path):** `systems/beacon/`. Per the agent-naming decision (2026-05-04), code paths keep climbing names; plain names are display-only. See `docs/architecture/agent-deployment-lifecycle.md` for the full naming + lifecycle convention.

## What Beacon does

Two coupled responsibilities, both in this folder:

1. **Send (Outreach Manager).** Pulls approved outreach drafts, picks a send window, dispatches via Instantly v2 (email channel), logs send attempts, writes outcomes back to `outreach_send_log`. Cool-off + round re-entry handled per the 2026-04-28 decision (parking at `suggest` until calibration).
2. **Reply runtime (Conversation Manager).** Ingests inbound replies via the Instantly webhook, runs the Haiku reply classifier, escalates to operator queue or applies the cool-off / re-enter logic. Auto-respond runtime stays at `suggest` until 30+ {prediction, reply, outcome} triples per class hit ≥80% accuracy (per `feedback_replies_manual_first_then_automate`).

## Layout

```
systems/beacon/
├── pipeline/             : send orchestrator (SendStage), webhook handler
├── reply/                : Haiku classifier, auto-respond runtime, escalation
├── storage/              : Supabase backends (SupabaseSendBackend, SupabaseWebhookBackend)
├── protocol.py           : the typed protocol contract for Beacon's surface
├── types.py              : send/reply data types
└── __init__.py
```

## How Beacon talks to the hub

Per the connected-system pattern (see lifecycle doc):

- **Reads from Supabase**: `agent_system_prompts`, `agent_skills`, `agent_frameworks` (Saraev cold-email + Allbound), `agent_guardrails`, `outreach_drafts`, `client_config`, `send_account`
- **Writes to Supabase**: `outreach_send_log` (one row per send attempt), `outreach_reply` (one row per inbound), `decision_log` (every send / classify / escalate / cool-off decision), `learning_events` (e.g. "subject pattern X correlates with reply rate Y for ICP Z")
- **API connections**: Instantly v2 (send + webhook), Anthropic API (Haiku for classification)
- **Subscribes to**: Scout's `learning_events` (lead source quality), Optimizer's recommendations (variant performance)
- **Subscribed by**: Optimizer (campaign-level performance), Auditor (cross-agent integrity)

## CLI entry points (in `scripts/`)

- `scripts/run_cool_off_cycle.py`: daily cool-off runner

## Tests

- `tests/test_beacon/`: unit + integration tests for send pipeline + reply runtime + classifier + Supabase backends

## Owning skills (per `agent_skills` Supabase rows, Phase 2)

When the schema lands, Beacon's row-set will activate skills under:
- `skills/copywriting/` (subject lines, body templates)
- `skills/outbound/` (sequence sequencing, send-window logic)
- `skills/operations/grade-cold-email-copy.md` (pre-send QA)
- `skills/meta/validate-writing.md` (fail-closed on every draft)

These skills live in the universal `skills/` library. Beacon's specific activation is declared in Supabase, not by physical placement.

## Migrations that brought Beacon online

- `016`: send pipeline + outreach_send_log
- `017`: webhook ingest + outreach_reply
- `018`: escalation queue
- `019`: cool-off + round re-entry
- (Phase 2 plan) `025`: agent_context_backbone (the per-agent declarative tables)

## Cloud-execution model

Beacon's send + reply work is per-contact, often sub-hourly. Per the decision matrix in the lifecycle doc:

- **Per-contact send tasks** → Trigger.dev (NOT Routines, 1hr floor too coarse)
- **Reply webhook listener** → Cloudflare Worker or Hetzner VPS (always-on, sub-second response)
- **Weekly Beacon performance review** → could be a Routine (weekly cadence fits)

No `clymb-beacon` routine repo exists yet. When Phase 4+ ships and Beacon migrates to the cloud, deployment will be a mix of Trigger.dev tasks + a webhook host.
