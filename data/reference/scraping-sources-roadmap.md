# Scraping Sources Roadmap

## Active (built and running)
- [x] Clutch.co — detailed scraper with stealth Playwright
- [x] DesignRush — stealth scraper
- [x] Free website enrichment (emails, meta, about, portfolio, testimonials)
- [x] Dedup + merge + timezone categorization

## Next (build scrapers)
- [ ] BNI Find a Member — filter by: Marketing Consultant, Web Designer, Web Developer, Graphic Designer, Digital Marketing, Advertising Agency, PR, SEO, Social Media, Brand Consultant, Business Coach, Management Consultant, IT Consultant
- [ ] Shopify Partner Directory — shopify.com/partners/directory
- [ ] Alignable — 9M+ SMBs, filter by industry
- [ ] Bark.com — service provider directory
- [ ] GoodFirms — similar to Clutch
- [ ] ScrapeBeast Shopify Partners dataset ($80, 4,000 contacts)

## Women-focused networks
- [ ] Future Females (futurefemales.co) — SA-based, expanding
- [ ] Chief (chief.com) — women executives
- [ ] Ellevate Network (ellevate.com) — professional women
- [ ] HerBusiness (herbusiness.com) — Australia

## Ad library scraping (for finding brands FOR agency clients)
- [ ] Meta Ad Library API — find brands running ads
- [ ] Google Ads Transparency Center — active advertisers
- [ ] TikTok Ad Library — DTC brands on TikTok
- [ ] BuiltWith — find Shopify stores by tech stack

## Email enrichment waterfall (cheapest first)
1. Free: scrape website contact/about/team pages for emails
2. Free: Google search "@domain.com"
3. Cheap: email pattern guessing + ZeroBounce verify ($0.008/verify)
4. Cheap: Hunter.io domain search (25 free/month, then $49/500)
5. Medium: Prospeo ($39/1000 credits)
6. Expensive: Apollo enrichment ($0.01-0.03/contact) — last resort

## Important: all networking directories need filtering
BNI, chambers of commerce, Alignable etc. have ALL industries.
Must filter search by profession/category matching our niches.
Don't scrape the full directory — only search for relevant professions.
