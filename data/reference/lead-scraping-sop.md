# Lead Scraping SOP

Standard operating procedure for pulling leads across all sources.

---

## Source Priority

| Priority | Source | Quality | Why |
|---|---|---|---|
| 1 | Custom list scraping | Highest | Hand-picked sources, exact ICP match |
| 2 | Skool communities | Very high | Shows active engagement, community membership = intent |
| 3 | LinkedIn Sales Navigator + Vayne.io | High | Activity-based filtering, recent posts, job changes |
| 4 | Airscale.io | High | Company-level signals, growing companies |
| 5 | Apollo People Search | Medium | Firmographic data only, no intent signals |

Apollo is the fallback for volume. The other sources produce higher-quality leads because they show activity and intent, not just job titles.

---

## Source 1: Custom List Scraping (Highest Quality)

Build custom scraping automations for hand-picked, high-intent sources.

**Target sources:**
- Partner directories (Shopify Partners, HubSpot Partners, Webflow Experts)
- Agency award lists (Clutch, DesignRush, GoodFirms top agencies)
- Conference speaker lists (relevant industry events)
- Podcast guest lists (agency/consulting podcasts)
- "Top X agencies" blog posts and listicles
- Job boards where agencies post openings (signals growth)
- Industry-specific directories

**Process:**
1. Identify source URL(s)
2. Scrape company names + websites using Firecrawl or custom scraper
3. Enrich with decision maker name + email using Hunter.io, Prospeo, or Apollo enrichment
4. Import via CSV into the pipeline

**Why this is best:** Every company on a partner directory or award list is a verified, active service business. Zero noise. The ICP match rate should be 80%+.

---

## Source 2: Skool Communities

Scrape Skool.com discovery page for communities where agency founders and consultants hang out.

**Target communities:**
- Agency growth communities
- Marketing agency owner groups
- Consulting business communities
- Fractional executive communities
- B2B sales/outreach communities
- AI for business communities

**Process:**
1. Go to skool.com/discovery and search relevant keywords
2. Find communities with 500+ members related to agency/consulting growth
3. Scrape member profiles (community members are self-selected ICP)
4. Cross-reference with LinkedIn to find company + title
5. Enrich emails using Hunter.io, Prospeo, or Apollo enrichment
6. Import via CSV

**Why this is valuable:** Skool community members are actively investing time in growing their business. That's a buying signal by itself. They're also engaged and reachable.

---

## Source 3: LinkedIn Sales Navigator + Vayne.io

Use LinkedIn Sales Navigator for activity-based filtering, export via Vayne.io.

**Sales Navigator filters:**
- Title: Founder, CEO, Owner, Managing Director (at companies with 3-50 employees)
- Industry: Marketing & Advertising, IT Services, Staffing & Recruiting, Design
- Keywords: same as Apollo pulls below
- Activity filter: Posted on LinkedIn in last 30 days (shows they're active)
- Spotlight: Changed jobs in last 90 days, mentioned in news

**Process:**
1. Build saved search in Sales Navigator with filters above
2. Export contacts via Vayne.io (extracts profile data)
3. Enrich emails using Hunter.io, Prospeo, or Apollo enrichment
4. Import via CSV

**Why Sales Nav is better than Apollo:** Activity filters. You can target founders who actually post, engage, and are visible. Apollo gives you everyone including the ghosts.

---

## Source 4: Airscale.io

Use Airscale to find growing companies by company-level signals.

**Filters:**
- Company size: 3-50 employees
- Growth signals: hiring, revenue growth, web traffic growth
- Industry: Marketing, IT Services, Consulting, Staffing, Design
- Geography: US, UK, Canada, Australia, NZ, South Africa

**Process:**
1. Set up company search in Airscale with growth filters
2. Export company list
3. Enrich with decision maker + email using any mail finder
4. Import via CSV

**Why Airscale matters:** Company-level growth signals (hiring, traffic, revenue) indicate they have budget and momentum. Static Apollo data doesn't tell you this.

---

## Source 5: Apollo People Search (Volume Fallback)

---

## Global Settings (apply to all pulls)

**Titles:**
Founder, Co-Founder, Owner, CEO, Managing Director, MD, Director, Principal

**Employee Count:** 3-50 (unless noted otherwise)

**Geography:**
United States, United Kingdom, Canada, Australia, New Zealand, South Africa

**Email Status:** Verified only

**Exclude:**
- Hospitals & Healthcare
- Real Estate
- Insurance
- Government
- Education
- Construction
- Mining
- Oil & Energy
- Defense
- Pharmaceuticals

---

## Pull 1: Digital & Creative Agencies (Primary Segment)

**Industries:** Marketing & Advertising, Design

**Keywords:**
digital marketing agency, creative agency, branding agency, SEO agency, PPC agency, social media agency, content marketing agency, performance marketing agency, web design agency, UX agency, CRO agency, eCommerce agency, Shopify agency, influencer marketing agency, email marketing agency

**Employees:** 3-50

**Target volume:** 200-300 contacts

**Notes:** Strongest ICP fit. Richest websites for icebreaker content. Closest to Kirsten's own agency experience. Start here.

---

## Pull 2: Web & Software Development Agencies

**Industries:** Information Technology & Services, Computer Software

**Keywords:**
web development agency, software development agency, app development agency, WordPress agency, Shopify development, custom software development, SaaS development

**Employees:** 3-50

**Target volume:** 100-200 contacts

**Notes:** Digital delivery by definition. Strong websites with portfolio/case studies.

---

## Pull 3: PR & Communications

**Industries:** Public Relations & Communications, Marketing & Advertising

**Keywords:**
PR agency, communications agency, reputation management, public relations firm

**Employees:** 3-50

**Target volume:** 100-150 contacts

**Notes:** Smaller segment but high-ticket ($10K+ retainers). Good ICP fit.

---

## Pull 4: Fractional Executives

**Titles:** Fractional CMO, Fractional COO, Fractional CFO, Fractional CTO

**Industries:** Any

**Keywords:**
fractional CMO, fractional COO, fractional CFO, fractional CTO

**Employees:** 1-10

**Target volume:** 100-200 contacts

**Notes:** High-ticket ($5K-25K/month per client). Solo or tiny team. Pipeline is always referral-dependent. The employee filter (1-10) and title filter (Fractional) naturally exclude enterprise consultancies like Deloitte, Bain, McKinsey, EY (400K+ employees, titles like "Partner" not "Fractional CMO").

---

## Pull 5: Recruiting & Staffing

**Industries:** Staffing & Recruiting, Human Resources

**Keywords:**
executive search, recruiting agency, staffing agency, talent acquisition, headhunter

**Employees:** 3-50

**Target volume:** 100-150 contacts

**Notes:** Entirely digital workflow. Decision maker is the founder or MD.

---

## Pull 6: MSP & Cybersecurity

**Industries:** Information Technology & Services

**Keywords:**
managed services provider, MSP, cybersecurity firm, IT consulting, IT services

**Employees:** 3-50

**Target volume:** 100-150 contacts

**Notes:** High-touch sales ($10K-100K+ ACV). Founder + small sales team.

---

## Pull 7: B2B Coaches & Advisors

**Titles:** Founder, Co-Founder, Owner, CEO, Coach, Advisor

**Industries:** Professional Training & Coaching, Management Consulting

**Keywords:**
business coach, executive coach, AI consultant, AI advisor, business advisor, growth advisor, revenue consultant, sales trainer, leadership coach, operations consultant

**Employees:** 1-15

**Target volume:** 100-150 contacts

**Notes:** Must serve businesses, not individuals. Someone coaching CEOs = B2B (good). Someone selling a $297 mindset course to consumers = B2C (excluded by screen). The small employee count (1-15) + founder title naturally filters out enterprise consultancies.

---

## Import Process

1. Export CSV from Apollo
2. Save to `data/` directory (e.g. `data/apollo-export-agencies-001.csv`)
3. Dry run first:
```
python -B scripts/import_apollo.py --file data/[filename].csv --client kirsten-client-zero --dry-run
```
4. Review the output: check avatar classification, tier distribution, exclusion rate
5. If exclusion rate > 30%, check why and adjust Apollo filters
6. Import for real:
```
python -B scripts/import_apollo.py --file data/[filename].csv --client kirsten-client-zero
```

---

## Pipeline After Import

1. **Score:** `python -B scripts/score_contacts.py --client kirsten-client-zero --rescore`
2. **Screen:** `python -B scripts/screen_contacts.py --client kirsten-client-zero --dry-run`
3. **Enrich:** `python -B scripts/enrich_contacts.py --client kirsten-client-zero --dry-run --limit 5`
4. **Generate:** `python -B scripts/generate_outreach.py --client kirsten-client-zero --dry-run`
5. **Review drafts**, then approve and send

Always dry-run before live runs. Enrichment uses Haiku credits. Limit to 5 first to check quality.

---

## Monthly Volume Target

- 500 contacts/month into the pipeline
- Screen excludes ~20-30% (100-150 out)
- Enrichment SKIP + nurture catches ~10% (50 out)
- ~250-350 get personalised outreach
- At 3-5% reply rate = 8-15 replies/month
- At 30-50% reply-to-meeting = 3-7 meetings/month

Pull schedule: 1-2 segments per week, rotating through all 7 segments monthly.

---

## Quality Checks

- **Avatar = "unknown" for >20% of contacts?** Apollo keywords may not match triggers. Check the segment.
- **Exclusion rate > 30%?** Apollo filters are too broad. Tighten keywords or industries.
- **All catch-all emails?** That domain doesn't verify properly. Still sendable but monitor bounce rates.
- **Multiple contacts from same company?** Only contact the most senior person (Founder > CEO > Director).
