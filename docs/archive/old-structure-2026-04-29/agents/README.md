# AIOS Agents

Named agent personas that run autonomously on a schedule. Each agent is the human-readable identity of one or more AIOS systems — operators interact with agents ("Scout is running"), not code modules ("systems/scout/pipeline/pull.py").

## What an agent is (and isn't)

| An agent IS | An agent is NOT |
|---|---|
| A named persona (Scout, Beacon, Optimizer, channel modules) | A Python class |
| A schedule + trigger pattern (daemon tick, event, cron) | An HTTP endpoint |
| A bundle of skills the agent is authorised to invoke | A workflow editor |
| An autonomy level (suggest / draft / act_notify / autonomous) per action type | A UI for a human to drive |

Each agent wraps one or more `systems/*` code modules. The code lives in `systems/`; the agent's name + responsibilities + skills + schedule live here.

## Convention

One YAML manifest per agent, named `agents/{name}.md` (markdown wrapper around a fenced YAML block for readability + inline comments).

Agents are added as the corresponding Plan ships. Do not pre-author empty agents — write them when the code they wrap exists and a schedule is defined.

## Current roster (as of 2026-04-21)

| Agent | Wraps systems | Plan status | Schedule |
|---|---|---|---|
| Scout | `systems/scout/*` | Plan 1 (in progress) | Daily daemon tick (Task 16.6) |
| Beacon | (future) `systems/beacon/*` | Plan 2 (not started) | Continuous scheduler |
| Optimizer | (future) `systems/optimizer/*` | Plan 7 (not started) | Weekly cron |
| Email channel | (future) `systems/channels/email/*` | Plan 2 | Send-window cron, per client timezone |
| LinkedIn channel | (future) `systems/channels/linkedin/*` | Plan 3 | Same |
| SMS channel | (future) `systems/channels/sms/*` | Plan 4 | Same |
| Voicemail channel | (future) `systems/channels/voicemail/*` | Plan 5 | Same |
| Voice-booking | (future) `systems/channels/voice_booking/*` | Plan 5 (narrow scope: booking only) | Event-triggered on positive reply |
| WhatsApp channel | (future) `systems/channels/whatsapp/*` | Plan 6 | Send-window cron |
| Letters channel | (future) `systems/channels/letters/*` | Plan 6 | Batch weekly |

## Agent manifest format

Markdown file with a fenced YAML block. Outside the fence: free-form notes. Inside the fence: structured YAML with inline `# comments` explaining each field (per `feedback_autonomous_agent_goal` + operator-readability goal).

Example: `agents/scout.md`.

## Why markdown-wrapped YAML (not pure YAML)

- Pure YAML: structured, machine-friendly, but no place for inline prose explanations or persona details.
- Pure markdown: prose-friendly but unstructured.
- Markdown + YAML fence: structured AI-parseable block + surrounding prose for persona, rationale, operator notes. Best of both.

## How agents relate to the autonomous-SDR framing

See `docs/superpowers/decisions/2026-04-21-aios-as-autonomous-sdr.md`. Each agent encapsulates a slice of the human SDR's job. Together, they ARE the SDR function.
