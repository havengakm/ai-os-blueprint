# SOP: Migrate warming email accounts from Smartlead to Instantly

**Purpose:** Move warming email accounts off Smartlead onto Instantly without restarting the warming cycle from day 1.

**Owner:** Operator (Kirsten for Clymb; future agency clients adapting their own switch).

**Trigger:** Decision to switch primary ESP from Smartlead → Instantly (or any cross-ESP migration). Reference: `docs/superpowers/decisions/2026-04-27-esp-comparison.md` for the Clymb instance.

**Inputs:**
- List of email accounts currently warming on Smartlead.
- Smartlead account access (to pause warmup).
- New Instantly account (Growth tier $47/mo or higher).
- DNS access for each sending domain (to verify SPF / DKIM / DMARC).

**Outputs:**
- 6 (or N) email accounts paused on Smartlead, connected + warming on Instantly.
- DNS auth verified.
- Deliverability monitored for 7 days post-switch.
- Smartlead retained as fall-back for 30 days, then optionally cancelled.

## Why this works (the 30-day worry is mostly wrong)

Email warming has 3 layers; only ONE restarts on ESP switch:

| Layer | Lives at | Switch impact |
|---|---|---|
| Domain reputation | Inbox providers (Gmail / Outlook / Yahoo) | ✅ Carries over fully — clean sending history is permanent positive signal |
| DNS auth (SPF / DKIM / DMARC) | Your DNS records | ✅ ESP-agnostic |
| ESP-internal warmup pool | Each ESP's own pool of mailboxes | ❌ Restarts — but rebuilds in 7-14 days, not 30 |

**Critical rule:** Don't run two ESPs warming the same account at once. Overlapping warmup sends confuse spam filters + pool reciprocity. Pause one before starting the other.

## Steps

### 1. Pause warmup on Smartlead (don't disconnect)

For each warming account:
- Smartlead UI → Email Accounts → click account → Warm Up tab
- Pause warmup (or set daily warmup volume to 0)
- **Do NOT disconnect the SMTP / IMAP connection** — keep the option to fall back.

### 2. Connect accounts to Instantly + start warmup at established-domain volume

- Sign up for Instantly Growth tier ($47/mo) at https://instantly.ai
- Email Accounts → Add Account → for each account, paste the same SMTP / IMAP credentials used in Smartlead
- Enable warmup
- **Set initial daily warmup volume to ~20-25 emails/day per account** (NOT from zero). This matches where Smartlead left off after ~10 days of warming. Instantly's auto-adjust feature should detect established-domain status and accept this ramp.

### 3. Verify DNS health

For each sending domain, run through https://mxtoolbox.com or https://easydmarc.com. Confirm:
- **SPF** record present + sender included (Instantly publishes the include directive on their setup docs).
- **DKIM** record signed.
- **DMARC** policy set (at minimum `p=none` — stricter is fine).

If anything's missing or stale, fix DNS BEFORE Instantly ramps volume.

### 4. Monitor 7 days

Watch Instantly's deliverability dashboard:
- "% landed in inbox" stays > 90% (operator's Smartlead pool was hitting 97% pre-switch — Instantly should match or exceed).
- Bounce rate < 2%.
- No spam complaints.

### 5. Decide on Smartlead retention

After 30 days of clean Instantly operation:
- **Option A:** Disconnect the 6 accounts from Smartlead + cancel the Smartlead subscription. Saves $39/mo.
- **Option B:** Keep Smartlead Base ($39/mo) as a permanent backup pool — useful if you ever hit an Instantly-specific deliverability issue.

Operator's call based on confidence in Instantly at that point.

## QA gates

- [ ] All N accounts paused on Smartlead before any are started on Instantly.
- [ ] All N accounts connected to Instantly with correct credentials.
- [ ] DNS verified for all N sending domains (SPF + DKIM + DMARC pass).
- [ ] Initial Instantly warmup volume = ~20-25/day, not from zero.
- [ ] Day 7 deliverability dashboard reviewed; ramp continues only if healthy.

## Errors / what to do if it goes wrong

| Symptom | Likely cause | Action |
|---|---|---|
| Instantly inbox-placement % drops below 85% within 7 days | Domain reputation hit OR pool reciprocity not yet established | Pause Instantly warmup. Verify DNS still passes. Wait 48hrs. Resume at lower volume (10/day). |
| Bounce rate > 5% | Bad email list OR auth misconfig | Stop sending. Run bounce list through ZeroBounce. Recheck DNS. |
| Spam complaints | Content issue (warmup pool sender chose to mark spam) | This is rare in warmup; if seen, pause warmup, contact Instantly support, investigate before resuming. |
| Both Smartlead AND Instantly active warming on same account | Operator skipped step 1 | Pause Smartlead immediately. Continue with Instantly only. |

## Escalation

- Deliverability issues persisting > 14 days post-switch: contact Instantly support via dashboard.
- Domain reputation tank (sudden inbox-placement collapse): pause ALL sending on the affected domain. Consult mxtoolbox + Google Postmaster Tools. Don't keep sending while debugging.

## Automation potential

This SOP is one-time per ESP migration; not high-priority for automation. Future possible automations:

- Pre-switch DNS-health audit script (mxtoolbox API → return pass/fail per domain).
- Post-switch deliverability-monitoring cron that pings Instantly API daily for 7 days and Slack-pings if metrics drop.

For now: human-driven, low-frequency. Code automation deferred until a 3rd ESP migration justifies the effort.

## When this SOP applies again

- Future agency-client deployments switching their own ESP.
- Adding a 3rd ESP to a client's roster (e.g. PlusVibe.ai if its API matures).
- Reverting from Instantly back to Smartlead if a deliverability issue forces it.
