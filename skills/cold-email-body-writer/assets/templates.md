# Production Email Templates

Copy-paste ready email templates for outbound tools. Replace placeholder text in [BRACKETS].

## Master Template

```
Subject: [3-5 words, lowercase, specific to recipient]

Hi {{firstName}},

{{personalization}}

Most [AUDIENCE] in [CITY/CONTEXT] are [SPECIFIC PROBLEM PATTERN]. [OPTIONAL SECOND SENTENCE WITH CONSEQUENCE].

I help [AUDIENCE] [SPECIFIC OUTCOME]. We handle [LIST WHAT IS INCLUDED]. [WHAT THEY HAVE TO DO].

[PROOF SENTENCE WITH SPECIFIC NUMBER].

If you are [THEIR GOAL], I would love to [VERB] [SPECIFIC FREE DELIVERABLE] for [{{company}} or "your business"] — [DIFFERENTIATOR OR FRAMING] — completely free.

[2-4 WORD QUESTION]

[SIGN-OFF]
```

## Variable definitions

When filling in this template, you need:

- **AUDIENCE:** The specific persona (med spas, real estate agents, PM companies, etc.)
- **CITY/CONTEXT:** Either a city placeholder ({{city}}) or a context like "your size" or "at your stage"
- **SPECIFIC PROBLEM PATTERN:** What this audience is doing wrong, in concrete terms
- **CONSEQUENCE (optional):** What the problem costs them
- **SPECIFIC OUTCOME:** What you deliver in plain language
- **LIST:** Specific things you handle, separated by commas
- **WHAT THEY HAVE TO DO:** The minimal effort required from them
- **PROOF SENTENCE:** Number-based result statement
- **THEIR GOAL:** Their stated business goal (grow doors, scale revenue, become known)
- **VERB:** Action verb for the deliverable (build, write, create, design, map)
- **SPECIFIC FREE DELIVERABLE:** The tangible thing with a number
- **DIFFERENTIATOR:** What makes this deliverable specifically valuable to them

## Subject line library

Pick one based on what fits the offer:

```
Subject lines that work:
- quick question
- {{company}}'s website
- {{company}}'s site
- {{company}}'s [specific area, e.g., "blog" or "ads"]
- question for {{firstName}}
- 5 [deliverable] for {{firstName}}
- [city] [vertical]
- [vertical] in [city]
- {{firstName}}, [topic]?
```

## Free deliverable library by service type

When the user is unsure what to offer, refer to this library:

### Content / video / brand services

- "5 video scripts written for your business"
- "3 viral hook concepts tested for your audience"
- "30-day content calendar with specific topic angles"
- "10 social post drafts ready to publish"

### Paid ads services

- "3 proven ad creatives plus copy you could run on your own"
- "Ad audit with 5 prioritized fixes"
- "$1,000 worth of ad copy variations across 4 angles"

### CRO / web / landing page services

- "Landing page mockup for one of your top products"
- "Conversion audit of your top 5 pages with specific fixes"
- "Mobile checkout flow redesign mockup"

### Lead gen / outbound services

- "Target list of 200 prospects matched to your ICP"
- "5-touch outbound sequence built for your offer"
- "Signal-detection setup for 100 priority accounts"

### SEO services

- "SEO audit of your top 10 pages with prioritized fixes"
- "12-topic content roadmap based on competitor gaps"
- "Local SEO audit with [N] specific opportunities"

### Email / lifecycle services

- "Audit of your top 5 email automations with revenue estimates"
- "3 email flow templates built for your industry"
- "Subject line bank with 30 tested variations"

### Strategy / consulting

- "90-day growth roadmap for your current situation"
- "Competitive teardown of 3 competitors with positioning gaps"
- "ICP definition document with 5 priority segments"

### Recruiting

- "Sourcing list of 50 candidates matched to your role"
- "Compensation benchmarks for 3 roles you are hiring"
- "Interview rubric custom-built for your stage"

### AI / automation

- "Workflow blueprint mapping 3 of your manual processes"
- "AI prompt library for your most repeated tasks"
- "Custom GPT/agent built for one specific workflow"

### Property management / real estate specific

- "Target list of 200 absentee landlords in your market"
- "AI receptionist demo configured for your business"
- "Owner acquisition playbook with 5 channel breakdowns"

## Pre-filled examples by industry

### Property management owner acquisition

```
Subject: phoenix property management

Hi {{firstName}},

{{personalization}}

Most PMs your size in {{city}} are getting Sunday and Monday inquiries that go cold by Wednesday because nobody is responding fast enough. Owners sign with whoever calls back first.

I help PM companies install AI agents that respond to every inquiry in 60 seconds and run outbound to absentee landlords automatically. We handle the build, integrations, and ongoing optimization. You review one weekly dashboard.

I have built this same system for 100+ service businesses across 10 countries before pivoting specifically to property management.

If you are looking to grow doors faster, I would love to build you a free target list of 200 absentee landlords matched to your portfolio. Useful whether you work with us or not.

Worth a look?

Sebastiaan
```

### Vacation rental management owner acquisition

```
Subject: {{city}} vacation rentals

Hi {{firstName}},

{{personalization}}

Most VR managers in {{city}} are growing through agent referrals while 1,000+ Airbnb hosts in their market are quietly burning out and looking for full-service management.

I help VR managers build automated owner acquisition systems. We handle list building, multi-channel outreach, AI follow-up, and qualified booking. You take the calls.

Built and exited a marketing agency that worked with 100+ short-term rental and hospitality businesses across 10 countries.

If you are growing this season, I would love to build a free target list of 100 burned-out Airbnb hosts in your market. Specific to your unit type and price point.

Interested?

Sebastiaan
```

## Implementation notes

**For Instantly / Smartlead users:**
Save the master template as your base. Build one variant per ICP segment. Use spintax sparingly (test without it first — most spintax does not improve deliverability much and can hurt readability).

**For multi-step sequences:**
This skill produces Email 1 only. For follow-ups (Emails 2-5), use a separate "follow-up writer" approach. The follow-ups should reference the original offer, add new value, and shorten progressively.

**For deliverability:**
Keep total email length under 130 words. Avoid links in the first email (they trigger spam filters). Use plain text formatting only — no HTML, no images, no fancy formatting. Send from a warmed-up domain on a separate root domain from your main company domain.
