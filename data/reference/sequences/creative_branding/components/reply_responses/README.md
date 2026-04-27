# Reply response templates (creative_branding)

Operator-authored response templates for the Beacon auto-respond runtime
(Plan 2 Phase 3 Task 2.3.2). The runtime picks the file matching the
classification returned by the Haiku reply classifier, fills the
placeholders, validates against the writing rules, and sends as a
thread reply.

## Filename → classification mapping

| File | Classification |
|---|---|
| `objection_pricing.md` | `objection_pricing` |
| `objection_timing.md` | `objection_timing` |
| `objection_authority.md` | `objection_authority` |
| `objection_other.md` | `objection_other` |
| `meeting_request.md` | `meeting_request` |
| `positive_interest.md` | `positive_interest` |

Other classifications (`negative`, `unsubscribe`, `out_of_office`,
`bounce`, `wrong_person`, `spam_marked`, `cannot_classify`) do NOT have
templates — they're routed to `archive` / `add_to_dnd` /
`wait_for_human_review` actions instead, never auto-responded to.

## Placeholders

- `{first_name}` — recipient first name (from contacts.first_name)
- `{company}` — recipient company (from contacts.company)
- `{calendly_url}` — sender's calendar link (from client_facts.calendly_url)
- `{sender_name}` — sender display name (from client_facts.sender_name)

`meeting_request.md` and `positive_interest.md` MUST reference
`{calendly_url}` — the runtime gates on a non-empty calendly_url and
skips with `skipped:no_calendly_url` if absent, rather than letting the
placeholder leak into the body.

## Writing rules (validator-enforced)

Per `rules/global-writing-guardrails.md`, the runtime rejects any
rendered body containing:

- Em-dash (`—`) — use commas or periods
- Banned words: `impressed`, `leverage`, `solution`, `scale`, `pipeline`,
  `headcount`, `lead gen`, `ecosystem`, etc. (full list in
  `systems/scout/enrich/icebreaker_adapter._BANNED_WORDS_RE`)
- Diagnostic phrases: `usually means`, `which suggests`, `feels like`,
  etc. (full list in
  `systems/scout/enrich/icebreaker_adapter._BANNED_DIAGNOSTIC_PHRASES`)

A template that fails validation skips the send with
`skipped:validator_failed` — the template stays untouched on disk;
operator must fix it.

## When to revise

These skeletons are starting points. Revise them when:
- Reply data shows a template's reply rate is low (Phase 4 Optimizer
  surfaces this).
- A specific objection variant comes up repeatedly and the catch-all
  `objection_other.md` isn't doing it justice.
- Brand voice evolves.
