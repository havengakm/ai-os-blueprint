# SOP: Legal Phone Number Sourcing + SMS Compliance
Version: 1.0
Last reviewed: 2026-04-20
Owner: Kirsten (policy); VA / Operator (run-book)

## Purpose
Ensure every mobile number Scout sources and every SMS Scout sends has a documented legal basis under POPIA (South Africa), GDPR (EU/UK), TCPA (US), and CASL (Canada). Manus AI intentionally refuses to scrape personal contact data — this SOP defines the compliance-first path that replaces scraping.

## Trigger
- Enrich stage queues a phone lookup for a contact whose `icp_score >= 50` (hard gate)
- Send stage dispatches an SMS (Plan 2 scope — rules below apply when that stage lands)

## Inputs
- Contact row with verified B2B email, title, company, geography
- `icp_score >= 50` (no phone lookup fires below this)
- Client's operating jurisdiction and the contact's market jurisdiction
- Active suppression / DNC data (refreshed at most 7 days old)

## Outputs
- `contacts.phone` populated in E.164 format, or left null
- `contacts.phone_source` = vendor name
- `contacts.phone_consent_basis` in {`legitimate_interest`, `explicit_consent`, `public_source`}
- `contacts.phone_found_at` timestamp
- Every SMS send logged to `activity_log` with consent metadata
- STOP replies recorded in a suppression table, honored within 24h

## Vendor priority (waterfall)
1. **Cognism** — default for EU / UK / SA / cross-border deployments. GDPR-registered, legitimate-interest-sourced, DNC-screened, purpose-built for B2B cold outreach.
2. **Lusha** — default at startup scale (< 5 active clients). Compliance-first, cheaper than Cognism, covers SA / EU / US mobile adequately.
3. **Apollo Premium** — fallback for US-heavy deployments where Cognism / Lusha coverage is thin.

Never use ContactOut, consumer-data brokers, or general-purpose scrapers for personal mobile numbers. Never ask Manus to find personal mobile / personal email — its refusal is the correct behaviour.

## Hard rules — do not override
- **B2B work mobiles only.** Never source personal mobiles. Vendor filters must be set to "business contact" where available.
- **Score gate at 50.** Do not call any phone adapter for `icp_score < 50`. Enforced at the orchestrator, logged to `decision_log` for every blocked call.
- **Jurisdiction awareness.** Apply the stricter of sender and recipient jurisdiction:
  - POPIA (SA): B2B legitimate-interest OK with clear opt-out in every SMS
  - GDPR (EU/UK): same standard; documentation heavier; consented-source vendor mandatory
  - TCPA (US): **do not cold-SMS US mobiles without explicit prior consent.** Use email-first, ask-for-SMS-later.
  - CASL (Canada): explicit consent required; treat like TCPA
- **Frequency cap.** Max 1 SMS per contact in the first 14 days from initial contact. No exceptions.
- **STOP mechanism.** Every SMS includes explicit opt-out language (e.g., "Reply STOP to unsubscribe"). STOP replies are honoured within 24 hours — suppression entry created, contact marked `sms_opted_out = true`, all future SMS blocked.
- **DNC screening.** Every send checks the vendor-supplied DNC list; list refreshed at most every 7 days. Match = skip send, log event.
- **Quiet hours.** No SMS sent outside recipient's local business hours (08:00–18:00 recipient TZ).

## Steps

### Phone sourcing (enrich stage)
1. Orchestrator checks `icp_score >= 50`. If not, skip — write decision_log entry `{"decision":"phone_lookup_skipped","reason":"below_score_gate","score":X}`.
2. Dispatch via waterfall: Cognism → Lusha → Apollo. First hit wins.
3. Vendor returns number + metadata. Insert into `contacts`:
   - `phone` in E.164
   - `phone_source` = vendor
   - `phone_consent_basis` from vendor's declared basis
   - `phone_found_at` = now
4. If no vendor returns a number, leave `phone` null. Re-check allowed monthly, not more often.
5. Log decision to `decision_log` with cost + vendor + basis for audit.

### SMS send (Plan 2 scope — rules below apply when that stage lands)
1. Before any send: verify `sms_opted_out = false`, `phone` not on current DNC list, recipient's local time inside quiet-hours window, contact's last SMS >= 14 days ago.
2. Compose message using approved template (human-written + placeholders filled by research — never AI-generated copy per `feedback_copy_architecture`).
3. Append STOP instruction if not in template footer.
4. QA sub-agent gate (Plan 2 QA agent) validates message + verifies all gates above. Fail = no send; three fails = escalate to operator.
5. Send via provider; log `activity_log` with `event_type='sms_sent'`, consent_basis, opt-out message text, vendor message ID.
6. Monitor for STOP reply. On STOP: insert suppression row, mark contact, send confirmation SMS, log `activity_log` with `event_type='sms_opt_out'`.

## QA
- **Monthly audit (Kirsten + VA):** sample 20 phone-sourced contacts. Verify: legal basis documented, source vendor recorded, STOP mechanism would work, DNC honoured.
- **Weekly spot-check:** send a STOP to a test number, confirm suppression fires within 24h.
- **Deliverability metrics in weekly report:** bounce rate, opt-out rate, complaint rate per inbox / per campaign. Alert if opt-out rate > 2% weekly.

## Common errors + mitigations
| Risk | Mitigation |
|---|---|
| Stale vendor DNC | DNC refresh < 7 days old; fail-closed if older |
| Cross-border jurisdiction mismatch | Apply stricter of sender/recipient; log which jurisdiction applied |
| SMS fired outside quiet hours | Orchestrator checks recipient TZ before send; reject if outside window |
| Phone lookup for low-score lead | Score gate at orchestrator; decision_log catches any bypass attempt |
| STOP reply not honoured | 24h SLA with automatic suppression; monitoring alert if SLA breached |
| Complaint / regulatory notice | Stop all SMS to that jurisdiction immediately; escalate to Kirsten |

## Escalation
- **STOP not honoured within 24h →** immediate alert to Kirsten + full SMS pause for that client until investigated
- **DNC match detected mid-pipeline →** pause SMS for that contact, flag for operator, audit how the match was missed
- **Regulatory complaint received →** halt all SMS to the jurisdiction, preserve logs, engage legal counsel, Kirsten-only escalation
- **Three QA failures on a single template →** escalate per CLAUDE.md's three-failure rule; retire template

## Automation notes
- **Fully automated:** score-gate check, vendor waterfall, DNC screening, quiet-hours check, STOP suppression, decision logging
- **Human-approved:** every new template + every new jurisdiction added to Scout's send scope (Plan 2 human approval gate)
- **Not automated:** legal counsel engagement on regulatory notices — intentional

## Related
- `feedback_enrichment_tiers.md` — score gate thresholds
- `feedback_vendor_stack.md` — vendor escalation triggers (Lusha → Cognism)
- `feedback_copy_architecture.md` — SMS copy rules (templates only, never AI-generated)
- Plan 2 will operationalise the SMS send stage; this SOP is the contract it must satisfy

## Change log
- v1.0 — 2026-04-20 — initial. Pre-dates Plan 2 SMS send implementation; rules apply when that stage lands.
