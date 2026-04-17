# Outbound Prospecting System — Complete Spec

The full outbound system has 10 parts. Each part feeds the next.
Every part reads from and writes back to the AI OS foundation.

---

## System Map

```
1. LIST BUILDING → 2. RESEARCH + SIGNALS → 3. INFRASTRUCTURE
                                                    ↓
                                            4. AI COPYWRITER
                                                    ↓
                                    ┌───── sends ──────┐
                                    ↓                  ↓
                              5. SURROUND        6. LINKEDIN
                              SOUND              (Signal)
                              (SMS/VM/letter)    (visit/connect/DM)
                                    │                  │
                                    └──── replies ─────┘
                                            ↓
                                    7. REPLY MANAGEMENT
                                       + OBJECTION HANDLING
                                            ↓
                                    8. AI APPOINTMENT SETTING
                                       (book → pre-warm → remind)
                                            ↓
                                    9. TRACKING + ANALYTICS
                                            ↓
                                    10. FEEDBACK LOOP
                                        (learn → improve → repeat)
                                            ↓
                                    feeds back into 1-8
```

---

## Part 1: List Building

### What it does
Find companies and decision makers that match the ICP.

### Sources (priority order)
1. Custom scraping (Clutch, DesignRush, Sortlist, Shopify Partners) — highest quality
2. Skool communities — shows active engagement
3. LinkedIn Sales Navigator + Vayne.io — activity-based filtering
4. Airscale.io — company growth signals
5. Apollo People Search — volume fallback

### Decision maker enrichment waterfall (cheapest first)
1. Website team page scrape (FREE)
2. Anymail Finder — domain or company name → verified emails ($0.06/verified)
3. Email pattern guess + SMTP verify (FREE)
4. Apollo enrichment ($0.03/contact) — last resort

### Data captured per contact
- Company: name, domain, location, employee count, industry, services
- Decision maker: first name, last name, title, company email, personal email, LinkedIn URL, mobile phone
- Scoring: ICP score (0-100), tier (A/B/C/D), avatar classification

### Quality gates
- ICP score below 25 → nurture, no outreach
- No website → 50% rank penalty
- No verified email → don't send (find email first)
- Duplicate check by domain (dedup across sources)
- Same company: contact most senior person only (unless multiple decision makers strategy)

### Foundation integration
- Log `icp_threshold` decisions for every score/screen
- Decision outcomes backfilled when contact eventually replies or books

---

## Part 2: Research + Signals

### What it does
Deep research on each qualified contact. Find buying signals, website observations, case studies, and intent triggers. This is what makes outreach relevant and timely.

### Research sources per contact
1. Website scrape: homepage, about, team, portfolio, case studies, testimonials, services
2. Google News: recent press, funding, expansion
3. Hiring signals: LinkedIn Jobs, career pages (hiring BD/sales = pipeline gap)
4. Social signals (Trigify): LinkedIn posts, Reddit questions, YouTube comments
5. Ad library (future): Meta/Google/TikTok active ads (for agency clients' clients)

### Signal taxonomy

| Signal type | Base score | Example |
|---|---|---|
| Trigify LinkedIn pain post | 40 | Posted about pipeline struggles |
| Trigify Reddit question | 35 | "Anyone tried cold email for agencies?" |
| Trigify YouTube comment | 30 | Commented on Jordan Platten video |
| LinkedIn hiring revenue role | 45 | Hiring Head of Sales |
| New C-suite leadership | 75 | New CEO appointed |
| Competitor trial/removed | 50 | Cancelled Instantly subscription |
| Google News funding | 45 | Raised seed round |
| Website observation | 10 | Generic website detail |

### Freshness multipliers
- Under 24 hours: 1.5x
- Under 7 days: 1.3x
- Under 14 days: 1.0x
- Under 30 days: 0.5x
- Over 30 days: 0.3x

### Compound scoring → routing

| Compound score | Priority | SLA | Channels |
|---|---|---|---|
| 150+ | Immediate | Same day | Email + SMS + LinkedIn |
| 100-149 | High | 24 hours | Email + LinkedIn |
| 50-99 | Standard | 48 hours | Email only |
| Under 50 | Nurture | Weekly batch | Email only (if at all) |

### Foundation integration
- Log `signal_weight` decisions when choosing top signal for icebreaker
- Outcomes: did signal-based outreach get better replies than website-only?

---

## Part 3: Infrastructure

### What it does
Email sending infrastructure that maximises deliverability.

### Per client setup
- 2-3 cold email domains (variations of their brand)
- 2 inboxes per domain (6 total)
- Zoho Mail hosting (SPF, DKIM, DMARC configured)
- Custom tracking domain per domain (CNAME → Smartlead)
- 14-21 day warmup before any sending
- 40 emails/day per inbox, 8 min gap between sends

### Deliverability management
- Daily warmup emails (Smartlead manages)
- Bounce rate monitoring (alert if > 2%)
- Spam complaint monitoring (alert if > 0.1%)
- Domain rotation (if one domain burns, rotate to backup)
- Never exceed 50 emails/inbox/day
- Weekday sending only (human pattern)

### Capacity math
- 6 inboxes x 40/day = 240 emails/day
- 240 x 22 business days = 5,280 emails/month
- At 3% reply rate = 158 replies/month
- At 40% meeting rate = 63 meetings/month (theoretical max)

---

## Part 4: AI Copywriter + Personalisation

### What it does
Writes personalised outreach using research, signals, and the client's voice.

### What the AI writes (per contact)
1. **Subject line** — lowercase, personal, under 6 words
2. **Icebreaker** (paragraph 1) — 2-3 sentences, 40 words max, specific work reference + detail + industry observation
3. **Bridge** (paragraph 2) — 1-2 sentences, 25 words max, connects observation to their business development

### What the AI does NOT write
- Email body (human-written templates)
- Offer paragraph (from client config)
- CTA (from client config)
- Follow-up emails (fixed copy in Smartlead)

### Framework selection (per avatar)

| Avatar | Primary framework | Secondary |
|---|---|---|
| agency_founder | AIDA or BAB | SAS (if signal) |
| overwhelmed_founder | PAS (only with signal) | Pain/Proof/Ask |
| burned_agency_buyer | Empathy/Story/Ask | Star/Story/Solution |
| growth_mode_founder | AIDA | BAB |
| tech_curious_founder | AIDA | Question Framework |
| fractional_executive | BAB | Question Framework |

### Quality gate (14 checks)
- No em dashes
- No AI vocabulary (surgical, leverage, ecosystem, etc.)
- No "most agencies" comparisons
- No GetLatka/Crunchbase revenue references
- No sensitive case studies (vaccines, political, religious)
- No assumed struggle in bridge
- First person used ("I saw" not "Noticed")
- Under word count limits
- Specific (not generic)
- No hollow praise
- No research process announcement
- No spam trigger words
- Subject line under 6 words
- Icebreaker SKIP rate under 5%

### Sequence structure
- **Touch 1 (Day 0):** Full personalised email (icebreaker + bridge + template body)
- **Touch 2 (Day 3):** Short nudge. "Quick ping on this." Under 40 words.
- **Touch 3 (Day 8):** Breakup. "Last one from me." Under 60 words. Door left open.

### Foundation integration
- Log `copy_variant` and `framework_selection` decisions
- Query past decisions: "Which framework produced best replies for this avatar?"
- Query knowledge_base: copywriting frameworks, Nick Saraev templates
- Outcomes backfilled when email opened/replied

---

## Part 5: Surround Sound

### What it does
Multi-channel amplification for high-intent contacts. Email is the primary. These channels support it.

### Channels (by contact score threshold)

| Channel | Score threshold | When | Tool |
|---|---|---|---|
| SMS | 50+ | After Touch 2 sent, day 5 | Twilio |
| WhatsApp | 50+ | Alternative to SMS (client preference) | Twilio |
| Voicemail drop | 50+ | After Touch 2, day 6 | Slybroadcast |
| Handwritten letter | 75+ | After Touch 3, day 12 | Handwrytten |
| LinkedIn (connection) | 50+ | After Touch 1, day 1 | Part 6 (Signal system) |

### SMS template
> "Hey {first_name}, sent you an email about {short_company}'s pipeline. No pitch, just curious how you're finding new clients. - Kirsten"

### Voicemail script
> "Hey {first_name}, it's Kirsten. Sent you a note about building your pipeline on autopilot. Not trying to sell you anything, just thought it might be relevant for {short_company}. Feel free to reply to the email or give me a shout. Cheers."

### Rules
- Never send SMS/voicemail without email first
- Never send to contacts who haven't been emailed
- Mobile phone numbers only (no landlines for SMS)
- SA mobile: starts with 06/07/08. UK: 07. US: hard to distinguish.
- Check opted-out before every send on every channel
- Max 1 SMS + 1 voicemail per contact per cycle

---

## Part 6: LinkedIn Outreach (Signal)

### What it does
Parallel outreach channel via LinkedIn. Runs independently from email but shares the same research, signals, and appointment setting system.

### Status: Build AFTER email is proven
Get email working first. Add LinkedIn as amplification once niches and angles are validated. This prevents spreading too thin early.

### Sequence
1. **Profile visit** (Day 0) — visit their profile, triggers "who viewed" notification
2. **Connection request** (Day 1) — short personal note, no pitch
3. **DM 1** (Day 3, after connected) — reference something specific, bridge to offer
4. **Engage with content** (ongoing) — like/comment on their posts genuinely
5. **DM 2** (Day 7) — soft follow-up if no response
6. **DM 3** (Day 14) — breakup message

### Connection request template
> "{first_name}, saw your work at {short_company}. Love what you're doing with [specific thing]. Would be great to connect."

No pitch in the connection request. Ever.

### DM templates
Follow same voice rules as email. Shorter, more casual. No icebreaker needed (they can see your profile).

### Tools (evaluate when ready)
- Dripify — LinkedIn automation
- Expandi — LinkedIn + email sequences
- Manual (Sales Navigator) — safest, lowest risk of LinkedIn ban

### Foundation integration
- Same decision logging as email
- Track: connection accept rate, DM reply rate, meeting rate
- Compare LinkedIn vs email performance per niche

---

## Part 7: Reply Management + Objection Handling

### What it does
Classify every reply, route to the right response, handle objections automatically for common scenarios, escalate unusual ones.

### Reply classification

| Classification | Examples | Auto-respond? | Action |
|---|---|---|---|
| `interested` | "Sure, let's chat" / "Tell me more" | Yes | → Part 8 (book meeting) |
| `interested_question` | "How does it work?" / "What's the cost?" | Yes | Answer + book |
| `objection_tried_before` | "We tried cold email, didn't work" | Yes | Objection handler |
| `objection_price` | "Too expensive" / "Not in budget" | Yes | ROI reframe |
| `objection_inhouse` | "We handle this ourselves" | Yes | Differentiate |
| `objection_timing` | "Not the right time" | Yes | Acknowledge + follow-up |
| `objection_not_interested` | "Not for us" / "No thanks" | Yes | Soft no macro |
| `hard_no` | "Stop emailing" / "Unsubscribe" | Yes | Opt out immediately |
| `out_of_office` | Auto-reply with return date | Yes | Parse date, schedule follow-up |
| `referral` | "Talk to my partner" / "CC'ing our CEO" | No (escalate) | Add new contact, reference original |
| `wrong_person` | "I'm not the right person" | Yes | Ask for redirect |
| `positive_complex` | Long thoughtful reply, multiple questions | No (escalate) | Flag for Kirsten to handle personally |

### Auto-response rules

**CRITICAL: The AI uses ONLY pre-approved macros. It never makes up answers, never debates, never gives pricing, never explains the system in detail. The goal of every response is to BOOK THE MEETING. Details are for the call.**

**Never answer over email:**
- Pricing ("how much?") → deflect to call
- Detailed "how does it work?" → deflect to call
- Technical questions → deflect to call
- Comparison questions ("how is this different from X?") → deflect to call

**Principle:** Be warm, be respectful, don't give away information that should be discussed live. Every response ends with a CTA to book.

### Pre-approved macros (from earlier sessions)

**Macro 1 — Simple positive reply:**
> "Thanks for getting back to me {first_name}. Do you have time {day1} at {time1} {tz} or {day2} at {time2} {tz}? Let me know and I'll send an invite. Or grab a slot here if easier: {calendly_link}. Looking forward. Kirsten"

**Macro 2 — Positive with questions:**
> "Thanks for getting back to me {first_name}. Great question. Easiest to cover on a quick call so I can show you rather than explain over email. Do you have time {day1} at {time1} or {day2} at {time2} {tz}? Can also use my calendar: {calendly_link}. Kirsten"

**Macro 3 — Soft no / not interested:**
> "Thanks for getting back to me {first_name}. Sure thing, no hard feelings. If you're willing to keep in touch, should I add you on LinkedIn? I'd love to keep tabs on {short_company}. All the best :) Kirsten"

**Macro 4 — Not now / follow up later:**
> "Thanks for getting back to me {first_name}. Sure thing, no rush. Let's keep in touch in the meantime - {short_company} looks great and I'd love to follow it. I'll send you a connect request on LinkedIn. All the best :) Kirsten"

**Macro 5 — Price question:**
> "Thanks for getting back to me {first_name}. Great question. Pricing depends on a few things specific to {short_company} so it's easiest to walk through on a quick call. Do you have time {day1} at {time1} or {day2} at {time2} {tz}? {calendly_link}. Kirsten"

**Macro 6 — "How does it work?" question:**
> "Thanks for getting back to me {first_name}. Easiest to show you rather than type it out. I can walk you through exactly how it would work for {short_company} in about 15 minutes. Do you have time {day1} at {time1} or {day2} at {time2} {tz}? {calendly_link}. Kirsten"

**Macro 7 — Hard no / stop:**
> "Removed. All the best with {short_company}. Kirsten"

**Macro 8 — Out of office:**
> [No response sent. Parse return date. Schedule follow-up for return date + 2 days.]

**Macro 9 — Wrong person / referral:**
> "Thanks {first_name}. Who would be the best person to chat with about this? Happy to reach out to them directly. Kirsten"

### Escalation rules
- Reply doesn't match any classification → flag for Kirsten
- Reply mentions legal/compliance concerns → flag immediately
- Reply is from a different person than contacted → flag
- Reply sentiment is angry/aggressive → flag, do NOT auto-respond
- Three auto-responses to same contact without booking → flag

### Response timing
- Positive replies: within 5 minutes (macro + scheduling)
- Questions: within 15 minutes
- Objections: within 30 minutes
- Soft no: within 1 hour
- Hard no / opt-out: within 5 minutes (immediate removal)

### Foundation integration
- Log `reply_handling` decision for every reply processed
- Track which objection handlers convert vs don't
- Pattern: "objection_tried_before → our response → did they book?" → learn what works
- Autonomy: starts at auto-respond for common objections, escalate unusual ones

---

## Part 8: AI Appointment Setting

### What it does
Books meetings, pre-warms prospects so they show up, handles reminders and no-shows.

### Booking flow

1. **Positive reply detected** (Part 7 classifies as interested)
2. **Suggest two times** (in prospect's timezone, within 5 business days)
3. **Include Calendly link** as fallback
4. **Calendar API check** — pull two open slots from Calendly before suggesting

### Booking response template
> "Thanks for getting back to me {first_name}. Do you have time {day1} at {time1} {tz} or {day2} at {time2} {tz}? Let me know and I'll send an invite. Or grab a slot here if easier: {calendly_link}. Looking forward. Kirsten"

### Booking rules
- Max 5 business days out (further = higher no-show)
- No calls before 6am or after 9:30pm SAST
- Convert times to prospect's timezone
- Exception: prospect says "I'm away until [date]" → offer slots after return

### Pre-warming sequence (after meeting booked)

| When | What | Channel | Purpose |
|---|---|---|---|
| Immediately | Calendar invite with Zoom/Google Meet link | Email (auto via Calendly) | Confirm |
| Day -2 | Personal video or message: "Looking forward to chatting. Here's what we'll cover." | Email or Slack | Build familiarity |
| Day -1 | LinkedIn connection request (if not already connected) | LinkedIn | Put a face to the name |
| Day 0, -2 hours | "Just confirming our call at {time}. Here's the link: {link}" | Email | Reminder |
| Day 0, -15 min | "See you in 15!" | SMS (if mobile available) | Final nudge |

### Pre-warm assets (decide when meetings start coming)
- Option A: Generic Loom intro video (one video for all, scalable)
- Option B: Personalised Loom per prospect (higher show rate, more effort)
- Option C: No video, just email + LinkedIn (simplest start)

### No-show handling

| Scenario | When | Response |
|---|---|---|
| No-show after 5 min | 5 min past start time | Email: "Hey {first_name}, looks like we missed each other. No worries! Want to reschedule? {calendly_link}" |
| No-show after 15 min | 15 min past | SMS (if available): "Missed you today. Happy to reschedule whenever works: {calendly_link}" |
| No response to reschedule (3 days) | 3 days later | "Last note on this — happy to find another time if you're still interested. If not, no hard feelings." |
| Second no-show | After second missed meeting | Flag for Kirsten. Don't auto-schedule a third. |

### Post-meeting follow-up
- Same day: "Great chatting {first_name}. As discussed: [1-2 bullet summary]. Next step: [proposal/trial/etc]. Talk soon."
- If proposal sent: follow up in 3 days if no response
- If not a fit: "Thanks for your time. Not the right fit right now, but happy to stay connected."

### Foundation integration
- Log `meeting_booking` decisions (times suggested, prospect timezone, booked or not)
- Track show rates by: pre-warm method, timezone, day of week, lead source
- Learn: "Prospects who get a Loom video show up 40% more" → recommend Loom for all

---

## Part 9: Tracking + Analytics

### What it does
Track every action, measure every metric, attribute every outcome. No guessing.

### Metrics tracked

**Email performance:**

| Metric | What | Benchmark | Alert if |
|---|---|---|---|
| Open rate | Unique opens / delivered | 40-60% | Below 30% |
| Reply rate | Replies / delivered | 3-5% | Below 2% |
| Positive reply rate | Positive / total replies | 40-60% | Below 30% |
| Bounce rate | Bounces / sent | Under 2% | Above 3% |
| Unsubscribe rate | Unsubs / delivered | Under 0.5% | Above 1% |
| Spam complaint rate | Complaints / delivered | Under 0.1% | Above 0.2% |

**Pipeline conversion:**

| Metric | What | Benchmark |
|---|---|---|
| Lead → reply | Replies / contacts entered | 3-5% |
| Reply → meeting | Meetings / positive replies | 30-50% |
| Meeting → proposal | Proposals / meetings held | 50-70% |
| Proposal → close | Closed / proposals | 20-30% |
| Lead → close | End-to-end conversion | 0.3-0.5% |
| Show rate | Attended / booked | 80%+ |
| Time to first reply | Hours from sent to reply | Track average |
| Time to book | Days from reply to meeting | Under 5 days |

**Per-segment breakdown:**
Track every metric above broken down by:
- Niche (Shopify, CRO, Creative)
- Avatar (agency_founder, growth_mode, burned_buyer, etc.)
- Signal type (Trigify, hiring, website-only)
- Framework used (AIDA, BAB, PAS, SAS)
- Geography / timezone
- Email template variant

### Attribution model
Every meeting booked traces back to:
- Which lead source (Apollo, Clutch, Sortlist)
- Which signal triggered outreach
- Which icebreaker/framework was used
- Which channel got the reply (email, LinkedIn, SMS)
- Total cost to acquire this meeting

### Reporting cadence

| Report | When | What | Delivered via |
|---|---|---|---|
| Daily intelligence brief | Every morning | Pipeline status, replies, signals, actions needed | Slack/WhatsApp |
| Weekly scorecard | Friday | Kill/scale/test decisions, key metrics | Slack/WhatsApp |
| Monthly performance report | 1st of month | Full funnel analysis, trends, recommendations | Email + PDF |
| Quarterly business review | Every 90 days | ROI analysis, strategy review, roadmap | Live call |

---

## Part 10: Feedback Loop + Continuous Improvement

### What it does
Learn from every interaction. Make the system smarter every week. This is the compounding intelligence moat.

### How it works

```
Every action → Decision logged (Part 7 of foundation)
       ↓
Outcome observed (hours/days later) → Outcome backfilled
       ↓
Next similar situation → Past outcomes retrieved → Better decision
       ↓
Pattern emerges → Confidence grows → Autonomy promotion considered
```

### What the system learns over time

| Learning | How | Impact |
|---|---|---|
| Which icebreaker style works for which avatar | Track reply rate by framework x avatar | Better copy selection |
| Which niches respond best | Track reply rate by niche | Better list building |
| Which signals predict meetings (not just replies) | Track signal → meeting correlation | Better signal weighting |
| Which subject lines get opened | Track open rate by subject pattern | Better subjects |
| Which objection handlers convert | Track objection response → booking rate | Better objection handling |
| Which pre-warm sequence gets show-ups | Track show rate by pre-warm method | Better pre-warming |
| What time of day gets best replies | Track reply rate by send hour | Better send timing |
| Which lead sources produce best ROI | Track source → close rate → revenue | Better sourcing |

### Statistical significance
The system calculates when it has enough data to make a recommendation. Could be 50 sends or 500, depending on the effect size. No arbitrary thresholds.

Formula: minimum sample size = 16 x (variance / minimum detectable effect squared)

In practice:
- Large differences (10% reply rate vs 2%) → detectable in ~50 sends
- Small differences (4% vs 3%) → needs ~500 sends
- System flags when a result is statistically significant vs noise

### A/B testing framework
- Test ONE variable at a time (subject line OR icebreaker OR framework, never multiple)
- Champion vs challenger: current best (champion) vs new variant (challenger)
- Split: 80% champion / 20% challenger (protect performance while testing)
- Decision: when challenger reaches statistical significance, promote or kill
- Log every test as a `copy_variant` decision with outcome

### Prime cycle (from /prime command)

| Frequency | What | Who |
|---|---|---|
| Daily | Check metrics, flag anomalies | System auto |
| Weekly (Friday) | Kill < 1% reply rate. Scale > 3%. Rewrite 1-3%. | Kirsten reviews system recommendations |
| Fortnightly | Detailed copy analysis, A/B results | System generates, Kirsten acts |
| Monthly | Full funnel review, ICP weight review | Kirsten + system |
| Quarterly | Niche research refresh, offer review | Kirsten leads |

### Autonomy progression
All reply handling starts at auto-respond for the 5 common objections. Unusual replies escalate. As the system proves itself:

| Phase | What's autonomous | What needs approval |
|---|---|---|
| Month 1-2 | Common objection responses, OOO handling, opt-out | Booking times, complex replies, escalations |
| Month 3-4 | Above + booking suggestions, simple questions | Complex questions, unusual situations |
| Month 6+ | Above + A/B test decisions, send timing | New templates, ICP changes, strategy |
| Month 12+ | Nearly everything | Major changes, new channels, new niches |

Promotion requires: 50+ decisions, 80%+ success rate, 30+ days, human approval.

---

## Implementation Priority

| Priority | Part | Build time | Depends on |
|---|---|---|---|
| 1 | List Building | Done | — |
| 2 | Research + Signals | Done | Part 1 |
| 3 | Infrastructure | Done | — |
| 4 | AI Copywriter | Done | Parts 1-3 |
| 5 | Reply Management + Objections | 2-3 days | Parts 3-4 (need replies first) |
| 6 | AI Appointment Setting | 2-3 days | Part 5 |
| 7 | Tracking + Analytics | 1-2 days | Parts 1-6 |
| 8 | Surround Sound | 1-2 days | Parts 3-4 |
| 9 | Feedback Loop | Done (foundation) | Parts 7-8 (need data) |
| 10 | LinkedIn (Signal) | 2-3 days | After email proven |

**Build order: 1-4 are done. Next: 5 (reply management) → 6 (appointment setting) → 7 (tracking) → 8 (surround sound) → 10 (LinkedIn after email works).**
