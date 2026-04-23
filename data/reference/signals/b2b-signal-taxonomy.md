# Broad B2B Signal Taxonomy: Buying & Social Triggers

Universal framework for identifying "in-market" behavior in B2B. Signals are categorized by the type of business movement they represent. This taxonomy is **global** — it applies to every AIOS deployment regardless of niche. Per-client specifics (which competitors to monitor, which thought leaders, which intent keywords) are configured via `client_config.trigify_search_ids`.

## How this doc is consumed by AIOS

- **`systems/scout/enrich/claude_deep_research.py`** reads this file's 5 categories into its extraction prompt. When the research adapter scrapes a prospect's site/LinkedIn, it classifies any hits against these categories and writes `research_data.structural_signals: list[{type, evidence_url, summary}]`.
- **`systems/scout/enrich/icebreaker_adapter.py`** reads `structural_signals` at Tier 3 of the 4-tier icebreaker source ladder (after Trigify Tier 1/2, before website-fallback Tier 4).
- **`data/reference/sops/trigify-search-setup.md`** (Plan 2) uses this taxonomy to script the per-client Trigify search playbook — each category maps to a signal-list recipe.

## Signal hierarchy (hot → cold)

Not all signals carry equal weight. The icebreaker adapter prefers signals in this order:

1. **Tier 1 (hottest):** Negative / Pain signals + Social engagement with competitor that reads as frustration → immediate outreach window.
2. **Tier 2 (warm):** Social engagement (neutral), thought-leader engagement, intent-topic posts → high-relevance window within 14 days.
3. **Tier 3 (structural):** Financial, Operational, Technographic changes → relevant for 30-90 days; frame outreach around the implication of the change, not the change itself.
4. **Tier 4 (fallback):** Website / portfolio / case study citation when none of the above fires. Generic personalization, still scoped to something specific the prospect has done.

---

## 1. Operational & Organizational Signals

Internal shifts in capacity, strategy, or leadership.

*   **New Leadership Appointments:** C-suite or Department Head changes (e.g., New VP of Sales, New CMO). New leaders often have a "100-day plan" and a budget to implement new systems.
*   **Aggressive Hiring Spikes:** A sudden increase in job postings for a specific department (e.g., hiring 5+ sales reps in a month). This signals a mandate for rapid growth.
*   **"Headless" Department Growth:** Hiring for execution roles (SDRs, Analysts) without a corresponding senior leader. This indicates a need for external systems or management.
*   **Geographic Expansion:** Opening new offices or entering new territories. This requires new infrastructure to support decentralized operations.
*   **Mergers & Acquisitions:** Signals a period of integration where legacy systems are being audited and replaced.

---

## 2. Financial & Growth Signals

Changes in capital position or market valuation.

*   **Funding Rounds (Series A, B, C):** A direct signal of "dry powder" and a mandate from investors to scale operations immediately.
*   **Major Contract Wins:** Public announcements of "landmark deals." This often creates a temporary "capacity crunch" where automation is needed to handle the new workload.
*   **IPO Filings / Exit Preparation:** Companies preparing for a public offering or sale need to "clean up" their operations and show predictable, scalable systems.
*   **Profitability Milestones:** Announcing "record quarters" or hitting specific revenue milestones. This signals a shift from "survival mode" to "optimization mode."

---

## 3. Technographic & Infrastructure Signals

Changes in "Digital DNA."

*   **Software Stack Migrations:** Moving from one major platform to another (e.g., HubSpot to Salesforce, or legacy ERP to Cloud). This is a high-intent window for complementary tools.
*   **Installation of "Trial" Tools:** Detecting the addition of specific tracking pixels or trial versions of industry-standard software.
*   **Legacy System Decay:** Public complaints or forum discussions about the limitations of their current tech stack.
*   **Adoption of Emerging Tech:** Early adoption of specific categories (e.g., AI, Blockchain, Web3) signals a "Tech-Forward" culture that is open to innovation.

---

## 4. Social & Engagement Signals

Intent of individual decision-makers based on public behavior.

*   **"How-To" Queries in Professional Forums:** Decision-makers asking for recommendations or "best practices" in niche communities (LinkedIn Groups, Slack Communities, Reddit).
*   **Engagement with "Problem-Aware" Content:** Liking, commenting, or sharing content that highlights a specific business bottleneck (e.g., "The Scaling Wall," "Talent Retention").
*   **Alumni Movements:** When a former employee of a "Power User" client moves to a new company. They often bring their preferred systems and vendors with them.
*   **Event Attendance:** Registering for or speaking at specific industry conferences or webinars related to growth and efficiency.
*   **Public "Referral" Requests:** Directly asking their network for vendor recommendations (e.g., "Who is the best for [X]?").

---

## 5. Negative / "Pain" Signals

A business is struggling and may be desperate for a solution.

*   **Downsizing in Specific Departments:** Laying off manual labor roles (e.g., data entry, basic support) often signals a shift toward automation.
*   **Public Customer Service Failures:** A spike in negative reviews or public complaints about "response times" or "quality control" indicates a broken internal process.
*   **Declining Market Share:** Reports of losing ground to "more efficient" competitors.
*   **Founder/CEO "Burnout" Content:** Leaders posting about the "grind" or "lack of time," signaling a readiness to delegate to systems.

---

## Reference — Trigify patterns (per-client configuration)

The Trigify search playbook (Plan 2 SOP) sets up 4 search types per client, mapped to this taxonomy:

1. **Intent-based keyword searches** (Social/Engagement + Negative) — 5-10 topic keywords drawn from the client's ICP pain language.
2. **Competitor-mention searches** (Social/Engagement + Negative) — 3-5 direct competitors by name, LLM-classified for sentiment (frustrated → Tier 1, neutral → Tier 2).
3. **Thought-leader engagement searches** (Social/Engagement) — 3-5 industry authorities whose followers are likely ICP.
4. **Own-brand monitor** (Social/Engagement) — anyone engaging with the client's own content.

Structural signals (Categories 1-3) are typically captured via the Claude Deep Research adapter parsing public sources (site, LinkedIn company page, news), not Trigify.
