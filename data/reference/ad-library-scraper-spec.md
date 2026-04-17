# Ad Library Scraper Spec

## Purpose

**Primary use case:** Generate qualified lead lists FOR agency clients by finding brands actively spending on paid media. This is the core product differentiator. Anyone can send cold emails. We find brands already spending money and put their founders on our client's calendar.

**Secondary use case:** Enrich agency prospects by checking if their clients run ads (signals they work with growth-minded brands).

The ad library scraper is a **lead source**, not just an enrichment step. It answers: "Which brands have budget and are actively trying to grow?"

---

## Data Sources

### Meta Ad Library API
- Endpoint: `https://www.facebook.com/ads/library/api/`
- Free, public, no auth required for basic searches
- Search by: advertiser name, country, active status
- Returns: ad count, creative types, start dates, active status
- Limitations: exact spend only shown for EU advertisers

### Google Ads Transparency Center
- URL: `https://adstransparency.google.com`
- Public, scrapeable via Firecrawl or Playwright
- Search by: advertiser name
- Returns: active ads, regions, date ranges, ad formats

### TikTok Ad Library
- URL: `https://library.tiktok.com`
- Public, scrapeable
- Search by: advertiser name, country
- Returns: active ads, creative, landing pages

### BuiltWith / Wappalyzer (tech stack detection)
- Check prospect's website for: Meta Pixel, Google Ads tag, TikTok Pixel, Klaviyo, Shopify
- Confirms they use paid media infrastructure
- BuiltWith API: paid but has free tier
- Wappalyzer: browser extension or API

---

## Use Case 1: Enrich Agency Prospects

During enrichment of a Shopify/eCommerce or CRO agency prospect:

1. Scrape the agency's website for client names/logos (already done in page summaries)
2. For each named client, check Meta Ad Library:
   - Are they running active ads?
   - How many ads are active?
   - How long have they been running? (longevity = real spend)
3. Score:
   - 3+ clients with active Meta ads = high signal (agency works with ad-spending brands)
   - 1-2 clients with active ads = medium signal
   - 0 clients with active ads = low signal (may work with small/no-budget clients)
4. Store as enrichment signal: `ad_library_client_activity`
5. Use in icebreaker: "I noticed [Client X] is running a solid Meta campaign right now"

### Signal scoring
- `agency_clients_running_ads`: base score 40 (high intent signal)
- Added to compound score for routing priority

---

## PRIMARY Use Case: Find Qualified Brands for Agency Clients

This is the core product. Generate lead lists FOR agency clients by finding brands actively spending on paid media.

### Why this matters

A brand running 20+ Meta ad variations for 60+ days has budget, is growth-minded, and is actively trying to scale. They are infinitely more qualified than a random Shopify store from Apollo. This is what we sell: "I don't just send cold emails. I find brands already spending money and put their founders on your calendar."

### Process

**Step 1: Scrape ad libraries for active advertisers**

| Platform | What to scrape | Qualification criteria |
|---|---|---|
| Meta Ad Library | Brand name, ad count, run duration, categories | 10+ active ads, running 30+ days |
| Google Ads Transparency | Brand name, active ads, regions | Active Google Shopping or Search ads |
| TikTok Ad Library | Brand name, ad count, creative types | Active TikTok ads (signals DTC brand) |
| Amazon | Sponsored product listings in category | Sponsored badge = paying for visibility |
| Takealot (SA) | Promoted sellers/products | Promoted = has budget |
| Instagram/Facebook Shops | Shop presence + running ads | Active shop + ads = serious ecom |

**Step 2: Filter for quality**
- Active ads for 30+ days (not just testing)
- 10+ ad variations (indicates real creative investment)
- Multiple platforms (Meta + Google = serious spend)
- Category match to client's niche (beauty, fitness, supplements, fashion, home, food, etc.)

**Step 3: Qualify the brand**
- Check website: real brand, real products, professional site
- Employee count via Apollo/LinkedIn (5+ = real team, not dropshipper)
- Check if they already have an agency partner (Clutch, DesignRush, website footer)
- If no agency on record = unserved opportunity

**Step 4: Find decision maker**
- Enrich via Apollo, Hunter.io, or Prospeo
- Target: Founder, CEO, Head of Marketing, CMO, Head of Growth
- Get verified email

**Step 5: Deliver to client**
- Brand name, website, ad platforms active on, ad count, decision maker, email
- Client's outbound system reaches them with personalised outreach

### Output per batch

| Field | Example |
|---|---|
| Brand name | GlowUp Skincare |
| Website | glowupskin.com |
| Ad platforms | Meta (34 active ads, running since Jan 2026), Google Shopping, TikTok |
| Category | Beauty / DTC |
| Employee count | 12 |
| Decision maker | Sarah Chen, Founder |
| Email | sarah@glowupskin.com |
| Agency on record? | No CRO agency found |
| Qualification | High — multi-platform ads, 30+ active, 60+ days running |

### What this looks like per agency niche

**For Shopify/eCommerce agency clients:**
"Here are 50 DTC brands running Meta + Google ads, no Shopify agency on record. They're spending money but their stores need work."

**For CRO agency clients:**
"Here are 50 brands spending serious money on paid media with no CRO partner. They're driving traffic but not optimising conversion."

**For Creative/Branding agency clients:**
"Here are 50 fast-growing DTC brands running heavy ad campaigns with generic creative. They need a creative partner."

### Volume targets

Per client, per month:
- Scrape 500-1,000 brands from ad libraries
- Filter to 200-300 qualified (active ads, real team, no agency)
- Enrich 200-300 with decision maker + email
- Feed into outbound system for personalised outreach
- Target: 10 booked meetings from this list

### Competitive moat

This is what nobody else does. Other cold email agencies:
- Pull from Apollo (same list everyone has)
- Send generic templates
- Hope for replies

We:
- Find brands **already spending money** (ad library proof)
- Verify they **don't have an agency partner** (unserved)
- Personalise outreach based on **their actual ads and products**
- Book qualified meetings with brands that have budget

This is the "10 qualified brand owners on your calendar" promise delivered.

---

## Implementation

### New file: `scripts/scrape_ad_libraries.py`

```python
async def check_meta_ads(brand_name: str, country: str = "US") -> dict:
    """Check Meta Ad Library for active ads by advertiser name."""
    # Returns: {active: bool, ad_count: int, running_since: date, categories: []}

async def check_google_ads(brand_name: str) -> dict:
    """Check Google Ads Transparency Center for active ads."""
    # Returns: {active: bool, regions: [], ad_count: int}

async def check_tiktok_ads(brand_name: str) -> dict:
    """Check TikTok Ad Library for active ads."""
    # Returns: {active: bool, ad_count: int}

async def enrich_agency_ad_signals(agency_contact: dict, client_names: list[str]) -> dict:
    """For each named client of an agency, check ad library activity."""
    # Returns: {clients_with_ads: int, total_clients_checked: int, details: [...]}
```

### Integration into enrichment pipeline

In `scripts/enrich_contacts.py`, after page summary extraction:

1. Extract client names from page summaries (already in research JSON as `client_results`)
2. For each client name, run `check_meta_ads()`
3. Add results to `intent_signals` as `ad_library_client_activity` signal
4. Factor into priority_rank scoring

### Rate limiting
- Meta Ad Library: no official rate limit but be respectful (1 req/sec)
- Google Ads Transparency: scrape carefully (2-3 sec between requests)
- TikTok: similar caution

---

## Additional Data Sources

### BuiltWith / Store Detection
- BuiltWith can identify every store built on Shopify, WooCommerce, Magento, etc.
- Cross-reference: brand running Meta ads + built on Shopify + no agency on record = perfect lead for Shopify agency client
- BuiltWith API or StoreCensus for bulk Shopify store data
- Filter by: technology stack, traffic rank, country

### Platforms to add later
- Amazon Sponsored Products (scrape search results for sponsored badges)
- Takealot Promoted Products (SA-specific, scrape category pages)
- Instagram/Facebook Shops (via Meta Commerce Manager, limited public data)
- LinkedIn Ads (limited transparency)

---

## Priority

Sprint 2 feature. Build after the core outbound pipeline is live and sending.
The pipeline works without this. This makes it significantly better.
