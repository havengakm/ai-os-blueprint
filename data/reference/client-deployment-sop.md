# Client AIOS Deployment SOP

Step-by-step process for deploying a new client instance of the AI OS.
Follow this EXACTLY for every new client. Update when the process changes.

---

## Pre-Deployment Checklist

- [ ] Client signed (contract + first payment received)
- [ ] Onboarding call scheduled (60-90 min)
- [ ] Client provided: Anthropic API key, Telegram username

---

## Step 1: Fork the Blueprint (5 min)

```bash
# Fork ai-os-blueprint for the new client
# On GitHub: Fork kirsten/ai-os-blueprint → kirsten/ai-os-{client-name}
# Make the fork PRIVATE

git clone git@github.com:kirsten/ai-os-{client-name}.git
cd ai-os-{client-name}
```

## Step 2: Set Up Supabase (15 min)

1. Create new Supabase project: `{client-name}-ai-os`
2. Run foundation migration:
   ```sql
   -- Paste contents of scripts/sql/001_foundation.sql
   ```
3. Run Scout migration (if Scout is the first system):
   ```sql
   -- Paste contents of systems/scout/sql/migrations.sql
   ```
4. Note the Supabase URL and service role key

## Step 3: Set Up Railway (10 min)

1. Create new Railway project: `{client-name}-ai-os`
2. Connect to the forked GitHub repo
3. Set environment variables (from .env.example)
4. Deploy
5. Verify `/health` returns 200

## Step 4: Configure Environment (.env) (10 min)

```bash
# Copy and fill in
cp .env.example .env

# Required:
SUPABASE_URL=https://{project}.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
ANTHROPIC_API_KEY=...           # Client's key
TELEGRAM_BOT_TOKEN=...
CLIENT_ID={client-name}
VOYAGE_API_KEY=...              # Shared (Kirsten's)
```

## Step 5: Onboarding Call (60-90 min)

During the call, gather context using `/build-context`:

### 5a. Company Context (20 min)
- What does the company do? (plain English)
- How long in business?
- Team size?
- Revenue range?
- What services do they offer?
- Who are their ideal clients?
- What's their average deal size?

Write to: `context/projects/{client-name}/company.md`

### 5b. Team Context (10 min)
- Who's on the team?
- Who handles sales currently?
- Who will review drafts?

Write to: `context/projects/{client-name}/team.md`

### 5c. Brand Context (10 min)
- Brand colours, fonts (or extract from website)
- Communication style
- Logo files

Write to: `context/brand/`

### 5d. Voice & Copy Style (15 min)
- How do they write? Formal? Casual?
- Any words they always/never use?
- Get 2-3 examples of emails they've sent

Write to: `context/voice.md`

### 5e. ICP & Avatars (15 min)
- Who's their ideal client? (title, industry, size, geography)
- What are the common buyer types?
- What signals indicate someone is ready to buy?
- Who should they NEVER contact?

Write to: `context/projects/{client-name}/icp.md`

### 5f. Strategy & Goals (10 min)
- What are they trying to achieve this quarter?
- What's worked before? What hasn't?
- Any specific niches or angles to test?

Write to: `context/projects/{client-name}/strategy.md`

### 5g. API Keys (5 min)
Walk them through generating:
- Anthropic API key (console.anthropic.com)
- Telegram bot (BotFather, takes 2 min)
- Calendly link (or Google Calendar)
- Smartlead API key (if they have an account)

## Step 6: Load Context into Supabase (15 min)

```bash
python scripts/load_context.py --client {client-name}
python scripts/load_knowledge.py --client {client-name}
```

Verify embeddings loaded:
```sql
SELECT section, length(content), embedding IS NOT NULL
FROM business_context WHERE client_id = '{client-name}';
```

## Step 7: Set Up Email Infrastructure (30 min)

1. Purchase 2-3 cold email domains (variations of their domain)
2. Set up Zoho Mail (or Google Workspace) on each domain
3. Configure SPF, DKIM, DMARC on Cloudflare/DNS
4. Create 2-3 inboxes per domain
5. Connect all inboxes to Smartlead
6. Enable warmup (14-21 days before sending)

## Step 8: Configure Scout System (20 min)

1. Set up ICP definitions in Supabase:
   ```sql
   INSERT INTO icp_definitions (client_id, industries, ...) VALUES (...)
   ```
2. Set up client_config:
   ```sql
   INSERT INTO client_config (client_id, icp_titles, ...) VALUES (...)
   ```
3. Seed autonomy rules:
   ```sql
   INSERT INTO autonomy_rules (client_id, action_type) VALUES
     ('{client-name}', 'copy_variant'),
     ('{client-name}', 'icp_threshold'),
     ('{client-name}', 'send_timing'),
     ...
   ```

## Step 9: First Pipeline Run (30 min)

1. Pull first batch of leads:
   ```bash
   python scripts/pull_leads.py --client {client-name} --limit 100
   ```
2. Score:
   ```bash
   python scripts/score_contacts.py --client {client-name} --dry-run
   ```
3. Screen:
   ```bash
   python scripts/screen_contacts.py --client {client-name} --dry-run
   ```
4. Enrich (A-tier only, limit 10):
   ```bash
   python scripts/enrich_contacts.py --client {client-name} --dry-run --limit 10
   ```
5. Review icebreaker quality with client
6. Generate outreach:
   ```bash
   python scripts/generate_outreach.py --client {client-name} --dry-run
   ```
7. Review full emails with client
8. Approve and go live

## Step 10: Go Live Checklist

- [ ] `/health` returns 200
- [ ] Pipeline endpoints reject requests without secret
- [ ] No credentials in source code
- [ ] Domains warmed (14+ days)
- [ ] Email templates approved by client
- [ ] First batch of drafts reviewed and approved
- [ ] Telegram bot responding
- [ ] Autonomy rules seeded at 'suggest' for all action types
- [ ] Weekly report scheduled

## Post-Launch (Week 1)

- [ ] Monitor deliverability daily (bounce rate < 2%)
- [ ] Review first replies with client
- [ ] Adjust ICP/avatar if needed based on first results
- [ ] Set up Friday review cadence
- [ ] Log all setup decisions to decision_log for learning

---

## Time Estimate

| Step | Time |
|---|---|
| Fork + Supabase + Railway | 30 min |
| Environment config | 10 min |
| Onboarding call | 60-90 min |
| Load context | 15 min |
| Email infrastructure | 30 min |
| Configure Scout | 20 min |
| First pipeline run | 30 min |
| **Total** | **~3.5-4 hours** |

Plus 14-21 days waiting for domain warmup before sending.
