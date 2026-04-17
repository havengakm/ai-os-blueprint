# Integrations Context

## Connected Services

| Service | Purpose | Status | Account owner |
|---|---|---|---|
| **Supabase** | Database + vector storage | Live | Kirsten |
| **Anthropic (Claude)** | AI runtime (Haiku pipeline, Sonnet agent) | Live | Kirsten |
| **Voyage AI** | Embeddings (voyage-3, 1024-dim) | Live | Kirsten |
| **Smartlead** | Cold email campaign management | Live, warming | Kirsten |
| **Zoho Mail** | Email hosting (tryclymb.com) | Live | Kirsten |
| **Apollo** | Lead scraping + enrichment | Active | Kirsten |
| **Prospeo** | Email finding from LinkedIn | Available | Kirsten |
| **ZeroBounce** | Email verification | Available | Kirsten |
| **Cloudflare** | DNS management | Live | Kirsten |
| **Railway** | App hosting | Not deployed yet | Kirsten |

## Pending Connections

| Service | Purpose | When |
|---|---|---|
| Telegram bot | Client communication, draft approval, intelligence briefs | Sprint 1 go-live |
| Calendly API | Meeting booking, availability check | Sprint 1 go-live |
| n8n | Workflow automation, pipeline scheduling | Sprint 1 go-live |
| Slack | Team communication (future) | When team grows |
| ClickUp / Notion | Project management (future) | When process needs it |
| Google Drive | Document storage (future) | When needed |
| Stripe | Billing and invoicing (future) | When clients onboard |
| Twilio | SMS/WhatsApp for surround sound | Sprint 1 high-intent |
| GHL (GoHighLevel) | CRM (future consideration) | Evaluation phase |

## API Keys Location

All API keys stored in `.env` (never committed). See `.env.example` for required keys.

## Data Flows

```
Apollo/Scraper → Supabase (contacts)
                     ↓
              Score → Screen → Enrich (Haiku + web scrape)
                     ↓
              Generate outreach (Haiku + templates)
                     ↓
              Smartlead (send) → Track (webhooks) → Supabase (activity_log)
                     ↓
              Reply → Telegram notification → Kirsten responds
```

<!-- TODO: Update as integrations are connected -->
