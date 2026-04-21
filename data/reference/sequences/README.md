# Sequence library

YAML-defined outbound sequence DAGs per niche per round. Loaded + executed by Plan 2's sequence engine.

## Structure

```
data/reference/sequences/
├── fractional-cfo/                   # niche
│   ├── round-1-linkedin-first.yaml   # round 1: pipeline pain + LinkedIn-first channel mix
│   ├── round-2-email-only.yaml       # round 2 (after 90d cool-off): retention angle + email only
│   └── round-3-workshop-offer.yaml   # round 3: downsell to workshop + cross-channel
├── marketing-agency/
│   ├── round-1-scale-without-hiring.yaml
│   ├── round-2-client-onboarding-auto.yaml
│   └── round-3-team-capacity-angle.yaml
├── legal-consultancy/
└── ...
```

One niche per directory, one YAML per round. Sequences are authored during Plan 2 (sequence engine + channel modules) and expanded per client / per offer over time.

## Format (sketch — finalised in Plan 2)

```yaml
name: "Fractional CFO — LinkedIn first with email fallback (Round 1)"
niche: fractional_cfo
round: 1
offer: aios_full
angle: pipeline_predictability

entry: linkedin_connect

steps:
  linkedin_connect:
    channel: linkedin
    action: connect_request
    template_family: linkedin-connect-no-note
    on_success: wait_acceptance

  wait_acceptance:
    wait:
      max_days: 3
      watch_events: [linkedin_connection_accepted]
    on_event: send_linkedin_msg_1
    on_timeout: fallback_email_1

  send_linkedin_msg_1:
    channel: linkedin
    action: send_message
    template_family: linkedin-msg-1-pipeline-pain
    next: wait_reply_1d

  # ... branches converge or terminate at STOP or END nodes
  # STOP = reply received, Beacon takes over
  # END = sequence complete, contact enters 90d cool-off for round 2
```

## Rules

- Every sequence MUST end at either `STOP` (reply received) or `END` (completed-no-reply → cool-off).
- Every `send` step references a `template_family`; the composer bandit-selects a specific template + component tuple at render time (see Plan 1 Task 15 composer).
- Channel steps that reference a channel the client has disabled (per `client_config.enabled_channels`) are skipped automatically, engine advances to `next`.
- Channel steps referencing a channel the contact has no ID for (no phone → skip SMS) are skipped per-contact without affecting sequence for other contacts.

## Productisation principle

Sequences are authored ONCE per niche-round-angle combination and apply to EVERY client in that niche. If a client needs a different sequence, the right move is usually:
1. A different niche definition (if their business is genuinely different).
2. A different autonomy level or send-window (client-level config, not sequence-level).
3. A new angle sequence added to the shared library (benefits all clients in that niche).

Per-client forks of sequences are the anti-pattern. See `feedback_productised_not_custom`.
