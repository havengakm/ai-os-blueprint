# Allbound System Framework

**Source:** Max Mitcham, Trigify founder. Transcript reviewed and endorsed by Kirsten 2026-04-24. Canonical strategic reference for how AIOS approaches outreach.

## Core thesis

**Inbound and outbound are not separate channels.** They feed into each other through AI agents, social signals, and automated workflows that run around the clock. One team of three people generates 160+ meetings per week using this framework.

**Why static lists are dead:**
- Everyone uses the same Apollo / ZoomInfo data
- Email providers now use AI to filter anything that reads like a sales pitch before it hits the inbox
- Reach out to people because they **just did something that shows they care**, not because they match a filter
- **One signal is worth more than 1,000 emails to people who have no reason to talk to you**

This is the direction AIOS is built for. Every architectural decision should be evaluated against: does this move us toward signal-based allbound, or back toward spray-and-pray?

---

## Team shape (mirror for AIOS agent roster)

Max's 3-person team:

1. **Master list builder** (growth / revenue ops person) — builds **evergreen** signal-based lists, NOT manual prospecting. Automated signal-based searches running continuously.
2. **Account Executive (AE)** — closes deals, self-sources warm leads.
3. **AI SDR** (built in n8n) — handles inbound replies, nurtures leads, books warmer prospects coming into the site.
4. **Content generator** — ghostwriter for the entire team, takes real themes from sales calls and turns them into posts.

**For AIOS:** our agent architecture should mirror this: Scout (list builder), Beacon (AI SDR for replies), Optimizer (content loop analyst), Operator (the human AE).

---

## Layer 1 — Signal-based prospecting (Trigify-powered)

**Centrepiece:** Trigify. Two main features: social listening + social engagement workflows.

**Boolean search across platforms:** LinkedIn primary, plus Reddit, YouTube, podcasts, Threads, Instagram.

**Four search types per client** (mirror into `data/reference/sops/trigify-search-setup.md`):
1. **Intent-based keyword searches** — people posting about topics with high intent for your offer
2. **Competitor-mention searches** — anyone engaging with competitor content
3. **Thought-leader engagement searches** — anyone engaging with named industry authorities
4. **Own-brand monitor** — anyone engaging with your own content

**Capture flow:**
- Match hits flow into a workflow
- Enrich the engagers
- Verify ICP fit
- Route to outreach tool (Clay / HeyReach / Instantly / Smartlead)

**Tiered grouping:** Competitors, thought leaders, own brand — each gets a DIFFERENT campaign strategy. Not one-size-fits-all.

**Result:** 1-in-4 positive reply rate from social signals (dramatically higher than cold static lists).

### Social warming (pre-engagement before DM)

Before reaching out to a prospect:
- Monitor key thought leaders in the ICP
- Use a workflow agent to classify whether a given post is relevant to your business
- If yes, be FIRST to drop value in the comments
- Your prospects see your name in the comment section repeatedly before you ever DM them
- By the time you reach out, they recognise the name 5-10+ times over

**"Your DMs stop being cold and your emails stop being ignored."**

This is the mechanism behind the "48-hour SLA + signal-hit priority queue" already in our Plan 2 memory — but with an explicit social-warming step ahead of first send.

---

## Layer 2 — Cold email infrastructure (value-led, conservative)

**Two-step campaigns only.** Never longer.

**Step 1: Lead with value.** A lead magnet with embedded CTAs — not a direct pitch. Soft ask inviting the prospect to accept a resource.

**Stack:**
- Instantly (primary), Plus Vibes (experimental)
- Mail Doso for inbox provisioning (official Google Workspace partnership — not shady)
- Lead Magic for enrichment + validation
- Bounce Banana for secondary verification

**Hard rules:**
- **Plain text only. No HTML.**
- **No links in first email.** (Matches our own rule.)
- **20 emails per inbox per domain per day.** Aggressive but deliberate — keeps deliverability high without inbox rotation.
- **Disable open tracking.** Pixels hurt deliverability. Turn off entirely.
- **Validate every email before send.** Non-negotiable. Bad emails = burned domains = failed campaigns.
- **No waterfall enrichment.** Lead Magic → Prospeo, that's it.

**Anti-personalization thesis:**
> "As long as you're reaching out with relevance, that is enough personalization for what you need."

**If the signal is right, you don't need the icebreaker to mention their dog's name.** Relevance beats surface-level personalization.

**Volume per client/day:** 50-100 inboxes × 20 emails = 1,000-2,000 email ceiling — plenty for niche signal-based outreach.

---

## Layer 3 — Content loop (self-feeding evergreen machine)

Most teams treat content and sales as separate. Max connects them into a loop where **each feeds the other**.

**The loop:**
1. Every demo / sales call transcribed via Fireflies → G-Sheets
2. AI analyzes the transcript, extracts every question asked by the prospect
3. Questions aggregate into **content themes** based on FAQ frequency
4. Content generator produces **4 posts/week** distributed across the team (everyone posts 2-3× per week)
5. Team posts → Trigify tracks the engagement → enrichment → ICP filter → CRM → new demos
6. Those demos produce more transcripts → more themes → more posts → loop

**Plus:** content syndicated into blog posts + newsletter via n8n agent. Blog/newsletter content drives SEO + gets mentioned in Claude/OpenAI training data → emergent authority.

**Principle:** "Every post is based on a real question a real prospect has actually asked in a real conversation." Never stare at a blank page.

**For AIOS:** this is the Content System (Plan 3+). Scout surfaces signals, Optimizer pulls themes from sales transcripts, a content agent drafts posts, Beacon monitors engagement. Full loop.

---

## Layer 4 — Recirculation (capture every channel, feed back)

Every channel's signals feed back into outbound. Nothing leaks.

**Website visitors at person-level:** RB2B or Vector (identify visitors who don't convert).

**LinkedIn engagement:** Trigify captures profile views + post engagements.

**Feedback loop:** signals fed back into Instantly via subsequence. Leads re-enter the Trigify flow.

**"Someone who visited your website after seeing a cold email gets a follow-up that feels warm because it is — they've already shown interest."**

---

## The 3 AI agents tying it together

1. **AI SDR** (n8n workflow)
   - Handles initial conversation when someone replies to email or lands on site
   - Books warm leads directly into calendar
   - Cross-correlates communication across channels
   - Updates CRM / systems of record continuously

2. **Call prep agent** (Max calls his "Master Chief")
   - Every 15 minutes, scans calendar for upcoming meetings
   - For each: runs business analyst + website analyst + use-case generator sub-agents
   - Delivers full brief via Slack + writes notes to CRM
   - Key discipline: **update systems of record to prevent duplicate research.** No wasted API calls.
   - Outcome: "I walk into every call knowing more about the business than they do."

3. **AI content generator**
   - Monitors social listening keywords via Trigify for industry trends
   - Delivers 3 content ideas each morning at 9am via Slack
   - Team has zero excuse not to post consistently

---

## How this maps to AIOS today

| Max's Layer | AIOS Current State | Gap |
|---|---|---|
| Signal-based prospecting | Trigify adapter wired in enrich pipeline; `client_config.trigify_search_ids` field exists; SOP drafted at `data/reference/sops/trigify-search-setup.md` | Trigify searches not yet set up for Client Zero — Plan 2 task |
| Social warming | Not built | Plan 2+ — add "social warming" agent: auto-comment on thought-leader posts before reaching out to their audience |
| Cold email infrastructure | Composer → outreach_drafts table; Smartlead wire pending | Plan 2 — Smartlead send infra + Max's infra rules baked in |
| Content loop | None | Plan 3+ — transcribe sales calls, extract themes, feed content agent |
| Recirculation | None | Plan 2+ — RB2B/Vector-equivalent for website visitor capture; Trigify LinkedIn-view capture wiring |
| AI SDR | Plan 2 task (reply classifier + autoresponder) | In backlog |
| Call prep agent | Not built | Plan 3+ |
| AI content generator | Not built | Plan 3+ |

**Current drift to correct:** we over-invested in Claude Deep Research for website scrape as the primary enrich path. Max's framework says **signal-first, website-fallback only** — which is already in our 4-tier icebreaker ladder (Tier 1/2 = Trigify, Tier 3 = structural signal, Tier 4 = website). But today we always run Claude Deep Research regardless of tier. **Plan 1.5 fix: gate Deep Research on signal absence.**

---

## Principles distilled (fast reference)

1. **Allbound > inbound/outbound separation.** Channels feed each other.
2. **Signal > filter.** Relevance based on what they JUST DID beats matching a static list.
3. **Social warming before DM.** Be visible in their feed before landing in their inbox.
4. **Two-step campaigns.** Lead with value (lead magnet), never more than 2 touches.
5. **Infrastructure basics beat hacks.** Plain text, no links, no open tracking, validated emails, conservative per-inbox volume.
6. **Anti-personalization.** Relevance IS personalization. Skip the dog's name.
7. **Content loop from sales calls.** Every demo transcript is 4 posts. Every post generates signals. Every signal generates demos.
8. **Recirculate everything.** Every channel's signals feed back. Nothing leaks.
9. **AI agents where they compound.** SDR handles inbound volume. Call prep agent makes every meeting 10x better. Content agent ensures consistency.
10. **Systems of record matter.** Prevent duplicate research, duplicate outreach, duplicate spend.

---

## Implementation stack — AIOS diverges from n8n

Max's team runs this framework on **n8n** (visual workflow orchestration). AIOS deliberately builds the same allbound framework with a **code-native, agent-driven stack**:

| Capability | AIOS (code-native) | Max (n8n) |
|---|---|---|
| Agent orchestration + reasoning | Claude Code + Claude Agent SDK | n8n AI agent nodes |
| Scheduled jobs | Trigger.dev + Unix cron + APScheduler | n8n schedules |
| Per-contact research | Claude Code subagents + Playwright | n8n HTTP + AI nodes |
| Signal workflows | Python daemons + Supabase | n8n workflows |
| Model access | Anthropic SDK (Sonnet + Haiku per CLAUDE.md rule) | n8n model nodes |

**Why code-native over visual workflow:**
- Git-tracked, version-controlled, diff-reviewable
- Testable with pytest before ship
- Composable — agents can call agents
- Reasoning capability beyond fixed branch logic
- No UI-config drift between environments
- Cost predictability — tokens counted in code, not hidden in n8n nodes

**Candidate tools to evaluate:** Claude Code (agentic CLI), Claude Agent SDK (orchestration), Trigger.dev (developer-first background jobs), Hermes Agent / OpenClaw-equivalent open-source agent frameworks.

**Do not build:** n8n workflows alongside the Python system. The existing `systems/scout/` pipeline + `os/` foundation is the abstraction — extend it, don't shadow it.

## Where this doc lives

This is the canonical strategic reference for AIOS outreach architecture. When in doubt — does THIS feature move us toward Max's allbound loop, implemented with AIOS's code-native stack? If yes, build it. If no, don't.
