# Client Onboarding Guide — Step by Step

Everything needed to take a client from "signed" to "system live."
Follow this exactly. Update when the process changes.

---

## Overview

| Phase | What | Time | Who does the work |
|---|---|---|---|
| 1. Pre-onboarding | Prep before the call | 30 min | Kirsten |
| 2. Onboarding call | Context gathering + API key setup | 90 min | Together (screen share) |
| 3. Technical setup | Deploy everything | 2-3 hours | Kirsten (solo) |
| 4. First pipeline run | Test the system | 1 hour | Kirsten (solo) |
| 5. Review + go-live | Client approves first batch | 30 min | Together |

**Total client involvement: ~2 hours across 2 calls.**
**Total Kirsten time: ~5-6 hours over 1-2 days.**

---

## Phase 1: Pre-Onboarding (30 min, Kirsten solo)

Do this BEFORE the onboarding call so the call is focused on context, not admin.

### 1.1 Purchase cold email domains (15 min)

Buy 2-3 domains that look like variations of their brand:

| If their domain is | Buy |
|---|---|
| acmeagency.com | tryacme.com, acmehq.com, acmegrowth.com |
| smithcreative.co | smithcreative.com, smithcreativehq.com |
| brightlabs.io | trybright.com, brightlabshq.com |

Where to buy: Namecheap, Cloudflare, or Porkbun (~$10/year each).
Point nameservers to Cloudflare (free plan).

### 1.2 Set up Zoho Mail on each domain (15 min per domain)

For each cold email domain:
1. Add domain to Zoho admin (mailadmin.zoho.com)
2. Verify domain ownership via DNS TXT record
3. Add DNS records to Cloudflare:
   - 3 MX records (mx.zoho.com, mx2.zoho.com, mx3.zoho.com)
   - SPF TXT record (`v=spf1 include:zoho.com ~all`)
   - DKIM TXT record (generate in Zoho → DKIM → Add selector `default` 2048 bits)
   - DMARC TXT record (generate in Zoho → DMARC)
   - Tracking CNAME (`track` → `open.sleadtrack.com`, DNS only)
4. Delete any old MX records (eforward etc.)
5. Create 2 inboxes per domain:
   - `{firstname}@domain.com`
   - `hello@domain.com`
   - Set display name to client's name on all
6. Enable IMAP on each inbox (Zoho Mail → Settings → Mail Accounts → IMAP)

### 1.3 Prepare onboarding call agenda

Send the client a short message before the call:

> "Looking forward to our onboarding call. I'll need about 90 minutes. Here's what we'll cover:
>
> 1. I'll learn everything about your business, clients, and goals (you talk, I listen)
> 2. We'll set up 2 quick accounts together (takes 5 minutes total)
> 3. I'll show you how the system will work
>
> Nothing to prepare. Just show up and be ready to talk about your business.
>
> See you at [time]!"

---

## Phase 2: Onboarding Call (90 min, screen share)

### Structure

| Time | What | Notes |
|---|---|---|
| 0-5 min | Welcome, set expectations | "By end of this call, I'll know everything I need to build your system" |
| 5-30 min | Business context deep-dive | Kirsten asks, client talks |
| 30-45 min | ICP + avatar identification | Who are your best clients? Who do you want more of? |
| 45-55 min | Voice + brand capture | How do you write? What do you sound like? |
| 55-65 min | API key setup (screen share) | Walk them through Anthropic + Slack (or WhatsApp) |
| 65-80 min | Show the system | Demo how it works, what they'll see |
| 80-90 min | Next steps + timeline | Set expectations for go-live |

### 2.1 Business Context Questions (25 min)

Ask these in conversation, not as a form. Record the call (with permission) for reference.

**About the business:**
- What do you do in plain English? (Not the website version, the real version)
- How long have you been doing this?
- How big is your team?
- What's your rough annual revenue? (Range is fine)
- What services do you offer?
- What's your average project/retainer size?

**About their clients:**
- Describe your best client ever. What made them great?
- Describe your worst client. What made them terrible?
- Where do your clients come from right now? (Referrals? Inbound? Outbound?)
- How many new clients can you take on in the next 3 months?
- Is there a type of client you want MORE of?
- Is there a type you want to STOP working with?

**About their pipeline:**
- How do you currently find new clients?
- What have you tried that didn't work?
- How much time do you spend per week on business development?
- What happens when you get busy with delivery? (Pipeline dries up?)
- Have you tried cold email before? What happened?

**About their goals:**
- What does success look like in 6 months?
- Is there a revenue target?
- What's the ONE thing that would change your business if it was solved?

### 2.2 ICP + Avatar Identification (15 min)

**ICP questions:**
- What industry are your best clients in?
- What size companies? (employees, revenue)
- What titles do you usually sell to?
- What geography? (local, national, international)
- What's the minimum project/retainer size you'll accept?
- Who should we NEVER contact? (competitors, industries, specific companies)

**Avatar questions:**
- Think of your last 5 clients. What "type" of buyer were they?
  - Were they overwhelmed and needed help?
  - Were they growing and looking to scale?
  - Had they tried other agencies and been burned?
  - Were they tech-savvy or tech-averse?
- What objections do you hear most in sales calls?

**Write as you go** into `context/projects/{client}/icp.md`

### 2.3 Voice + Brand Capture (10 min)

**Ask:**
- How would your best client describe your communication style?
- Show me an email you've sent to a client that you're proud of
- Show me a LinkedIn post or message that sounds like you
- Any words you always use? Any words you'd never use?
- Are you formal or casual? Direct or diplomatic?
- Do you use humour? Emojis? Slang?

**Capture:**
- 2-3 real email examples (copy-paste from their sent folder)
- Their LinkedIn profile URL
- Their website URL
- Logo + brand colours (or screenshot their website, extract later)

**Write into** `context/voice.md` and `context/brand/`

### 2.4 API Key Setup (10 min, screen share)

#### Anthropic API Key (5 min)

Say: "I need you to create an account for the AI that powers your system. Takes 2 minutes."

Walk them through:
1. Go to `console.anthropic.com`
2. Click "Sign up" (use their business email)
3. Verify email
4. Go to Settings → API Keys → Create Key
5. Name it: `clymb-system`
6. **IMPORTANT:** They need to add a payment method (Settings → Billing → Add payment)
7. Set a usage limit: $20/month (more than enough for Haiku pipeline)
8. Copy the API key → paste into YOUR notes (they don't need to save it)

Say: "This costs about $0.15 per month for 500 contacts. Less than a coffee."

#### Slack (or WhatsApp) Bot (3 min)

Say: "This is how you'll interact with the system. Like having a team member in your pocket."

Walk them through:
1. Open Slack (or WhatsApp) on their phone
2. Search for `@BotFather`
3. Type `/newbot`
4. Name: `{Company} Assistant` (or whatever they want)
5. Username: `{company}_clymb_bot` (must be unique, end in `bot`)
6. BotFather gives a token → they read it out → you copy it

Say: "That's it. You'll never need to do this again."

#### Calendly Link (1 min)

Say: "Send me your Calendly link so the system can suggest meeting times."

If they don't have Calendly:
- "No problem. I'll set one up for you." (Do it in Phase 3)
- OR use their Google Calendar directly

### 2.5 Show the System (15 min)

Show them what they'll experience day-to-day:

1. **"Every morning you'll get a brief like this:"**
   Show a mock intelligence brief in Slack (or WhatsApp)

2. **"When we have drafts ready, you'll see this:"**
   Show a mock draft review (icebreaker + bridge + body)

3. **"When someone replies, you'll get this:"**
   Show a mock reply notification with suggested response

4. **"Every Monday you'll get this:"**
   Show a mock weekly report

5. **"You'll never need to log into anything technical. Everything comes to you through Slack (or WhatsApp)."**

### 2.6 Next Steps + Timeline (10 min)

Set clear expectations:

> "Here's what happens next:
>
> 1. I'll build your system over the next 3-5 days
> 2. Your email domains need 14-21 days to warm up (this is industry standard, can't rush it)
> 3. In about 2 weeks, I'll send you the first batch of draft emails to review
> 4. Once you approve them, we go live
> 5. You should see first replies within the first week of sending
> 6. First meetings typically happen in weeks 3-4
>
> During warmup, I'm building everything. When domains are ready, we flip the switch."

---

## Phase 3: Technical Setup (2-3 hours, Kirsten solo)

The client is DONE at this point. Everything below is Kirsten's work.

### 3.1 Fork the Blueprint (5 min)

```bash
# On GitHub: Fork kirsten/ai-os-blueprint → kirsten/ai-os-{client}
# Make the fork PRIVATE

git clone git@github.com:kirsten/ai-os-{client}.git
cd ai-os-{client}
```

### 3.2 Set Up Supabase (15 min)

1. Create new Supabase project: `{client}-ai-os`
2. Run `scripts/sql/001_foundation.sql` in SQL editor
3. Run Scout migrations (when migrated to systems/scout/sql/)
4. Note URL + service role key

### 3.3 Set Up Railway (10 min)

1. Create new Railway project
2. Connect to the forked GitHub repo
3. Add environment variables
4. Deploy
5. Verify `/health` returns 200

### 3.4 Configure Environment (10 min)

```bash
cp .env.example .env
# Fill in:
# SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
# ANTHROPIC_API_KEY (from client's account)
# TELEGRAM_BOT_TOKEN (from onboarding call)
# CLIENT_ID={client-name}
# VOYAGE_API_KEY (Kirsten's shared)
# SMARTLEAD_API_KEY (Kirsten's account)
```

### 3.5 Load Context (30 min)

Write the context files from onboarding call notes:

```
context/
├── personal.md            — Empty (this is Kirsten's OS, not the client's)
├── voice.md               — From voice capture during call
├── brand/
│   └── brand-guide.md     — Logo, colours extracted from website
├── projects/{client}/
│   ├── company.md          — From business context questions
│   ├── team.md             — From team discussion
│   ├── strategy.md         — From goals discussion
│   ├── icp.md              — From ICP + avatar questions
│   └── current-data.md     — Starting state (all zeros)
```

Load into Supabase:
```bash
python scripts/load_context.py --client {client-name}
python scripts/load_knowledge.py --client {client-name}
```

### 3.6 Connect Inboxes to Smartlead (15 min)

For each inbox created in Phase 1:
1. Connect to Smartlead (SMTP/IMAP settings from Zoho)
2. Set daily limit: 40
3. Set min time gap: 8 minutes
4. Enable warmup (weekdays only)
5. Set custom tracking domain
6. Note the warmup identifier tag

### 3.7 Set Up Zoho Mail Filters (5 min per inbox)

For each inbox, create filter:
- Subject contains `{warmup-tag}` → Move to Warmup folder

### 3.8 Configure ICP in Supabase (15 min)

```sql
INSERT INTO icp_definitions (client_id, industries, titles, ...) VALUES (...)
INSERT INTO client_config (client_id, sender_name, ...) VALUES (...)
INSERT INTO autonomy_rules (client_id, action_type) VALUES
    ('{client}', 'copy_variant'),
    ('{client}', 'icp_threshold'),
    ('{client}', 'send_timing'),
    ...
```

### 3.9 Set Up Smartlead Campaigns (15 min)

Create campaigns split by niche x timezone:
- Same 3-step sequence in each
- Step 1: `{{custom_subject}}` / `{{custom_body}}`
- Step 2: `re: {{custom_subject}}` / follow-up nudge
- Step 3: `last note, {{first_name}}` / breakup

### 3.10 Email Templates in Supabase (15 min)

Customise email templates with client's:
- Voice (from onboarding)
- Offer (from strategy discussion)
- Case studies (from their portfolio)
- CTA (Calendly link or custom)

```sql
INSERT INTO email_templates (client_id, touch, body, ...) VALUES (...)
```

---

## Phase 4: First Pipeline Run (1 hour, Kirsten solo)

### 4.1 Pull First Leads (15 min)

```bash
# Apollo pull based on ICP from onboarding
python scripts/pull_leads.py --client {client} --limit 100
```

Or import from custom scraping (Clutch, DesignRush, etc.)

### 4.2 Score + Screen (15 min)

```bash
python scripts/score_contacts.py --client {client} --dry-run
# Review scores, check avatar classification
python scripts/score_contacts.py --client {client}

python scripts/screen_contacts.py --client {client} --dry-run
# Review exclusions
python scripts/screen_contacts.py --client {client}
```

### 4.3 Enrich (20 min)

```bash
# A-tier first, limit 10
python scripts/enrich_contacts.py --client {client} --dry-run --limit 10
# Review icebreaker quality
# If good, run full batch
python scripts/enrich_contacts.py --client {client} --limit 50
```

### 4.4 Generate Outreach (10 min)

```bash
python scripts/generate_outreach.py --client {client} --dry-run
# Review full emails — icebreaker + bridge + template body
# Check: does it sound like the client?
```

---

## Phase 5: Review + Go-Live (30 min, together)

### 5.1 Schedule Review Call

Once domains are warm (14-21 days) and first batch is generated:

> "Your system is ready. I've prepared the first batch of outreach emails. Let's hop on a quick call so you can review them before we start sending."

### 5.2 Review Call (30 min)

Walk them through:
1. Show 5-10 draft emails on screen
2. "Does this sound like you?"
3. "Is there anything you'd change?"
4. Make adjustments live based on their feedback
5. "Ready to start sending?"

### 5.3 Go Live

Once approved:
```bash
python scripts/send_outreach.py --client {client} --dry-run
# Final check
python scripts/send_outreach.py --client {client}
```

Send Slack (or WhatsApp) message:
> "Your outbound system is live. First emails are going out now. I'll notify you the moment someone replies. Here's to your first new client from the system! 🚀"

---

## What the Client Provides (summary)

| Item | When | How | Time for client |
|---|---|---|---|
| 90 min of their time | Onboarding call | Screen share, conversation | 90 min |
| Anthropic API key | During call | Kirsten walks them through | 5 min |
| Slack (or WhatsApp) bot token | During call | Kirsten walks them through | 3 min |
| Calendly link | During call | They share the URL | 1 min |
| Domain registrar access OR nameserver change | Before call or during | Email or screen share | 5 min |
| Brand assets (logo, colours) | Before or after call | Email or extract from website | 0 min (Kirsten extracts) |
| Draft approval | Review call (14-21 days later) | 30 min call | 30 min |
| **Total client time** | | | **~2.5 hours** |

## What Kirsten Does (summary)

| Task | Time | When |
|---|---|---|
| Buy domains + set up Zoho Mail | 30 min | Before onboarding call |
| Run onboarding call | 90 min | Day 1 |
| Fork repo + set up Supabase + Railway | 30 min | Day 1-2 |
| Write context files from call notes | 30 min | Day 1-2 |
| Load context + configure ICP | 30 min | Day 2 |
| Connect inboxes to Smartlead + warmup | 15 min | Day 2 |
| Set up campaigns | 15 min | Day 2 |
| First pipeline run (pull, score, screen, enrich, generate) | 60 min | Day 3-5 |
| Review call with client | 30 min | Day 14-21 (after warmup) |
| Go live | 15 min | Day 14-21 |
| **Total Kirsten time** | **~5.5 hours** | |

---

## Post Go-Live Checklist

- [ ] First emails sending (check Smartlead dashboard)
- [ ] Deliverability looks good (no bounces, no spam complaints)
- [ ] Intelligence brief sending to client's Slack (or WhatsApp) daily
- [ ] Weekly report scheduled for Monday mornings
- [ ] Autonomy rules seeded at 'suggest' for all actions
- [ ] Client knows how to approve/reject drafts via Slack (or WhatsApp)
- [ ] Client knows to reply "approve" or "skip" to draft reviews
- [ ] Calendar is connected for meeting booking
- [ ] Reply macros configured in Smartlead
- [ ] Friday review cadence set in Kirsten's calendar

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Client can't create Anthropic account | Create under Kirsten's account, add $15/mo to retainer |
| Client doesn't have Slack (or WhatsApp) | Set up email notifications instead (less ideal but works) |
| Client doesn't have Calendly | Create a free Calendly for them during Phase 3 |
| Domain warmup taking longer than 21 days | Check Smartlead deliverability score, rotate if needed |
| Client wants to see "the backend" | Show them the Slack (or WhatsApp) interface and weekly report. Never show Supabase/Railway. |
| Client wants to change the copy | Note changes, update templates, re-generate. Never let them edit directly. |
| Client asks "how does the AI work?" | "It reads your website, finds specific things about your prospect's business, and writes an opening that sounds like you wrote it personally. Then it follows up automatically." |
