# SOP: Email Compliance Gate
Version: 1.0
Last reviewed: 2026-04-23
Owner: Kirsten / AIOS operator

> **STATUS: STUB.** This SOP is a bookmark. The full compliance walkthrough ships in Plan 2 alongside the SendStage that enforces it. Below is the checklist every send MUST pass; operational steps fill in when SendStage lands. Plan 1's job is to lock this contract so Plan 2 implements against a stable spec.

## Purpose

Every outbound email must pass CAN-SPAM (US), GDPR (EU / UK), CASL (Canada), and the client-level global DND / opt-out checks. This SOP defines the pre-send gate that SendStage will implement in Plan 2.

The sibling SOP for phone / SMS is [data/reference/sops/compliance/phone-sms-compliance.md](compliance/phone-sms-compliance.md). Email follows the same shape, adapted for the channel.

## Trigger

- Every single email send. No exceptions.
- Implemented as a pre-send gate inside Plan 2's SendStage, called BEFORE handing a message to the ESP (Instantly, SendGrid, etc.).

## Inputs

- Contact row with `email`, `consent_basis`, `timezone`, last send timestamp, reply history.
- Client's `opt_outs` table (global DND per client).
- Email template with unsubscribe token + physical address placeholder.
- Sender identity: `from_name`, `from_email`, `reply_to` (all verified against the sending domain).
- Fresh ZeroBounce verification (cache valid 90 days per Plan 1.5 Amendment 3).

## Outputs

- Pass: send proceeds to ESP, event logged to `activity_log` with consent metadata.
- Fail: send blocked, reason logged to `decision_log` with decision_type `compliance_block`, contact flagged for operator review if fail was unexpected.

---

## Safe-send checklist

Every gate below MUST pass. Any failure = no send. Fail-closed is the default.

1. **Consent basis set.** `contacts.consent_basis` is one of:
   `legitimate_interest | explicit_consent | public_source`. Null = block.
2. **Not in global DND.** Contact's email hash is not present in the client's `opt_outs` table.
3. **No prior opt-out.** Contact has not previously replied with an opt-out keyword (see list below) AND has not been flagged by the Plan 2 toxicity classifier.
4. **Inside business hours.** Send time is inside the contact's timezone business window (default 08:00 to 18:00 local). Explicit override flag required to send outside.
5. **Unsubscribe link present.** Rendered template contains a working unsubscribe token resolving to the client's unsubscribe handler.
6. **Physical address present.** Signature resolves to a valid physical mailing address (CAN-SPAM requirement).
7. **Sender identity valid.** `from_name` + `from_email` + `reply_to` match the verified sending domain's records (SPF, DKIM, DMARC aligned).
8. **Fresh email verification.** ZeroBounce verdict is `valid` and verified within the last 90 days. Expired verification = re-verify before send.
9. **Frequency caps respected.** Contact's last email ≥ cadence-minimum days ago (Plan 2 defines per-sequence).
10. **Jurisdiction check.** Apply the stricter of sender and recipient jurisdiction. CASL (Canada) + GDPR (EU / UK) require the consented-source path; CAN-SPAM (US) allows legitimate-interest B2B with opt-out honoured.

---

## Global DND: `opt_outs` table

Checked before every send. Schema:

```sql
CREATE TABLE opt_outs (
    client_id      TEXT NOT NULL,
    email_hash     TEXT NOT NULL,     -- SHA256 of lower-cased email
    opted_out_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason         TEXT NOT NULL,     -- 'reply_keyword' | 'manual' | 'bounce_hard' | 'toxicity'
    source         TEXT,              -- optional: message id that triggered it
    PRIMARY KEY (client_id, email_hash)
);
```

Match is by `email_hash` so raw PII is not stored in the gate table. Lookup path: hash the outgoing contact's email lower-cased, check `PRIMARY KEY` presence.

Once opted out, always opted out. No time-based expiry. Manual re-opt-in = explicit operator action with audit trail.

---

## Opt-out keyword matching

Matched case-insensitive with word boundaries against inbound reply bodies. Matches trigger an immediate `opt_outs` insert with `reason='reply_keyword'`.

Keyword list (expand over time; add via migration, not ad-hoc):

```
STOP
UNSUBSCRIBE
REMOVE
take me off
stop emailing
not interested
opt out
opt-out
```

Plus a Claude-based toxicity classifier for edge cases (explicit profanity, direct hostility). Classifier verdict of `toxic` = auto opt-out with `reason='toxicity'`. False-positive rate monitored in the weekly `/prime` review.

---

## Round re-entry (90-day cool-off)

Per `feedback_surround_sound_architecture.md`: contacts enter a 90-day cool-off after a sequence ends. When cool-off expires and the contact is eligible for `sequence_round = N+1`:

1. Re-hash the email and re-check `opt_outs`.
2. Re-run `consent_basis` validation (data may have changed: contact changed jobs, company was acquired, jurisdiction shifted).
3. Re-verify email via ZeroBounce (the 90-day cache has expired by definition).
4. Only proceed to SendStage if all three pass.

Never skip re-entry checks based on prior-round pass. Consent is not transitive across cool-off.

---

## Plan 2 scope

This SOP locks the contract. The implementation lands in Plan 2:

- **SendStage** wraps the ESP call with this gate.
- **ComplianceService** provides the single-method contract `async def can_send(contact, client_id, template) -> ComplianceVerdict`.
- **Verdict logging:** every block lands in `decision_log` with decision_type `compliance_block`; every pass lands with `compliance_pass`.
- **Toxicity classifier:** owned by Plan 2's reply-handling module; classifier verdicts feed `opt_outs`.
- **Physical address source:** resolved from `client_config.physical_address` at template render time.

Plan 1 ships the contract + the `opt_outs` table scaffold (see migration scope in Plan 2's Task P2-X) so the data model is stable before the code lands.

---

## QA (when SendStage is live)

Pre-go-live on a new client:

1. Dry-run a full compliance check on 20 sample contacts. Zero sends should reach the ESP.
2. Send a known opt-out keyword reply from a seeded test inbox; verify `opt_outs` row appears within 60 seconds, and the next send to that contact is blocked.
3. Confirm unsubscribe token resolves to a working handler that inserts an `opt_outs` row.
4. Confirm `from_name` / `from_email` / `reply_to` pass SPF + DKIM + DMARC alignment checks via a test send to `check-auth@verifier.port25.com` or equivalent.
5. Physical-address field renders correctly in the footer of every template.

Weekly spot-check once live:

- Opt-out rate per campaign in the weekly report. Alert if > 2% weekly.
- Bounce rate (hard) alert if > 2% weekly.
- Complaint / spam rate alert if > 0.1% weekly.

## Common errors (placeholder for Plan 2)

| Error | Cause | Fix |
|---|---|---|
| `compliance_block: consent_basis_missing` | Contact row missing `consent_basis`. | Enrich the contact, or set explicit basis; do not default to legitimate_interest without source justification. |
| `compliance_block: in_opt_outs` | Contact previously opted out. | No fix. Permanent block. |
| `compliance_block: verification_stale` | ZeroBounce verdict older than 90 days. | Re-verify before retrying send. |
| `compliance_block: outside_business_hours` | Send attempted outside contact's business window. | Scheduler should not queue this; investigate the scheduler if it happens in practice. |
| `compliance_block: toxicity_classifier` | Prior reply flagged toxic. | Manual operator review; un-flag only with audit trail. |

## Escalation

- Complaint / regulatory notice (CAN-SPAM, GDPR DPA, CASL CRTC): halt all sends to the jurisdiction immediately; preserve logs; Kirsten-only escalation; engage legal counsel.
- Three compliance blocks of the same type on the same client: escalate per CLAUDE.md; the upstream data path is likely broken.
- Opt-out not honoured within 24 hours: immediate alert, full send pause for the client until root cause found.
- SPF / DKIM / DMARC failure on live sending domain: stop all sends from that domain, investigate before resuming.

## Automation notes

- **Fully automated (Plan 2):** every gate in the checklist, opt-out keyword matching, toxicity classifier, round re-entry checks, compliance decision logging.
- **Operator-driven:** template authoring, physical-address configuration per client, jurisdiction-policy review.
- **Not automated:** regulatory-notice legal response (intentional, human-only).

## Related

- [data/reference/sops/compliance/phone-sms-compliance.md](compliance/phone-sms-compliance.md): sibling SOP, same pattern adapted for phone / SMS.
- `feedback_surround_sound_architecture.md`: 90-day cool-off, round re-entry, global DND.
- `feedback_copy_architecture.md`: human-written templates + placeholder fills; AI never writes outbound copy.
- Plan 2 Task P2-X: SendStage implementation against this contract.

## Change log

- v1.0, 2026-04-23, initial (Task 18). STUB: contract locked; Plan 2 implements.
