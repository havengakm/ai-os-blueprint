# SOP: Authoring Trigify Monitor YAML
Version: 1.0
Last reviewed: 2026-04-22
Owner: Kirsten / VA

## Purpose

Author the per-client `trigify_monitors.yaml` that the
`configure-trigify-monitors` skill consumes. This YAML defines the four
behavioral-signal monitor types Trigify will watch on behalf of a client.

Monitor quality drives enrich-stage signal quality. Generic keywords = noise;
narrow, use-case-anchored keywords = buyer intent.

## Trigger

Step N of Client Deployment SOP — after `02-setup-supabase.md`, before the
first Scout pipeline run.

Also: whenever an operator adds a new competitor / thought leader / brand
misspelling mid-flight.

## Inputs

- Client ICP definition (`context/{client}/icp.md`)
- Client offer description
- Operator research on competitors + authority figures in the niche

## Outputs

- `context/{client}/sourcing/trigify_monitors.yaml` (operator-authored)
- Returned Trigify `search_ids` persisted to `client_config.trigify_search_ids`

---

## Why monitor types matter

Per Max Mitcham webinar 2026-04-22 (YouTube `bKEmJIch0nI`), Trigify's four
monitor types each produce a different kind of signal:

| Monitor type | What Trigify watches | Signal quality | Typical count per client |
|---|---|---|---|
| `intent_keyword` | Public posts matching the keyword | Medium — noisy unless scoped | 2-5 |
| `competitor_engagement` | Likes/comments on competitor profiles' posts | High — engaged with competitor = category-aware buyer | 3-10 |
| `thought_leader_engagement` | Likes/comments on authority figures' posts | High — authority-adjacency proxy for ICP fit | 3-10 |
| `brand_mention` | Public posts mentioning your brand | Very high — direct awareness | 1 per brand term + misspelling |

Engagement monitors (competitor + thought leader) outperform pure keyword
monitors because the audience is already category-aware.

---

## YAML schema

```yaml
# context/{client}/sourcing/trigify_monitors.yaml
#
# Four sections, all optional but at least one must be non-empty.
# All fields with `#` comments are REQUIRED unless marked (optional).

intent_keywords:
  # 2-5 entries. Each becomes a keyword monitor on Trigify.
  - phrase: "social signals"                   # required — the core keyword
    scope_terms:                               # optional — extra qualifiers ANDed into the query
      - "gtm"
      - "outbound"
    platforms:                                 # optional — defaults to [linkedin, x]
      - "linkedin"
  - phrase: "buying intent data"               # shortest valid form

competitors:
  # 3-10 entries. Each becomes a company_engagement monitor.
  - name: "Clay.com"                           # required — human-readable, used in monitor name slug
    linkedin_url: "https://linkedin.com/company/clay-labs"   # required — Trigify watches this page

thought_leaders:
  # 3-10 entries. Each becomes a profile_engagement monitor.
  - name: "Nick Saraev"                        # required
    linkedin_url: "https://linkedin.com/in/nicksaraev"       # required

brand:
  # 1+ entries. Each string becomes a keyword monitor (brand-mention).
  # Include misspellings — buyers type badly.
  - "Triggery"
  - "TrggerFy"
```

---

## How to pick good intent keywords

Per Max webinar: niche + use-case beats generic.

### Bad (too generic)

- `"AI"` — matches everything
- `"outbound"` — matches everything in GTM
- `"automation"` — matches every SaaS post

### Good (niche + use-case)

- `"cold outbound that actually works"` — specific pain frame
- `"social signals buying intent"` — category-specific
- `"LinkedIn engagement to pipeline"` — use-case-specific

### Rules of thumb

1. Include the pain frame or use-case ("`that actually works`", "`to
   pipeline`", "`without getting flagged`").
2. Scope with `scope_terms` when the bare phrase is ambiguous.
3. Prefer 4-7 word phrases over 1-2 word phrases.
4. Test by searching LinkedIn manually for the phrase — if page 1 is noise,
   the monitor will be noise.

---

## How to find competitor LinkedIn company URLs

1. Operator identifies 3-10 direct competitors from `context/{client}/icp.md`
   or client interview.
2. On LinkedIn, search the competitor name → click the company page (not a
   post).
3. Copy the URL. Format: `https://linkedin.com/company/{slug}`.
4. Verify the URL resolves to a real company page, not a 404 or wrong match.

Pitfalls:

- Sub-brands vs parent company — watch the one your ICP actually follows.
- Acquired companies — the LinkedIn page may redirect or change slug.
- Regional variants — pick the global or the client-relevant region.

---

## How to find thought-leader URLs

1. Ask the client: "Who do you follow?" Also: "Who do your prospects
   quote on LinkedIn?"
2. For each named leader, LinkedIn-search → profile page.
3. URL format: `https://linkedin.com/in/{slug}`.
4. Validate the profile is active (posted within 90 days) — dead profiles
   produce zero signals.

Signal quality by type of leader:

- Niche-specific authority (best) — e.g. Nick Saraev for outbound.
- Category-adjacent influencer (good) — e.g. a VC investing in the category.
- Generic business influencer (noisy) — avoid.

---

## Brand monitoring gotchas

- **Misspellings matter.** If the brand is `Triggery`, add `TrggerFy`,
  `Triggerfy`, and any variants you see in the wild.
- **Sub-brands.** Monitor the parent brand AND each product name if they
  market separately.
- **Common words.** If the brand is a common English word ("Apple"), the
  keyword monitor will be overwhelmed — skip brand monitoring for that case
  and rely on competitor / thought-leader monitors instead.
- **Ambiguous acronyms.** "AMS" could be "Account Management Services" or
  "Amsterdam". Use `scope_terms` or skip.

---

## What to do if Trigify rejects a payload

The `TrigifyMonitorCreator` records each failure in `result.failed` with the
HTTP status and first 200 chars of the response body. Common causes:

| Error signature | Fix |
|---|---|
| `HTTP 401 / unauthorized` | `TRIGIFY_API_KEY` missing or expired — rotate. |
| `HTTP 400 / invalid target_url` | LinkedIn URL malformed — check for trailing slash, query string, mobile variant. |
| `HTTP 400 / query too short` | Intent keyword phrase under Trigify's min length — add scope_terms or extend phrase. |
| `HTTP 422 / monitor_type not allowed on plan` | Client's Trigify plan doesn't include this monitor type — escalate to billing. |
| `HTTP 429 / rate limit` | Wait 60s, re-invoke. Idempotency will skip what already succeeded. |

Do not retry automatically more than twice. Per CLAUDE.md, three QA failures
= escalate.

---

## QA

After `configure-trigify-monitors` skill completes:

- `client_config.trigify_search_ids` count = `len(created) + len(skipped_existing)`.
- `GET /v1/searches` on Trigify dashboard shows every monitor with
  `[{client_id}]-...` name prefix.
- Test pull: run a single-contact enrich with `dry_run=False` and verify the
  Trigify adapter returns either `behavioral_signals_found` or
  `no_signals_matched` (not `no_monitors_configured`).

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `ValueError: intent_keywords[N]: missing required field 'phrase'` | YAML typo | Check the exact key name; `phrase` not `keyword` or `text`. |
| `ValueError: competitors[N]: missing required field 'linkedin_url'` | Used `url` instead | Rename to `linkedin_url`. |
| Zero signals after first pipeline run | All monitors noisy / thought-leaders inactive | Review `result.dry_run_planned`, swap keywords for narrower phrases, swap dead thought leaders for active ones. |

## Escalation

- Any Trigify API auth failure: rotate key, check billing.
- Any monitor type rejected by plan: escalate to Kirsten before building
  around it.
- More than 50% of monitors producing zero signals after two weeks: escalate
  to `/prime` review.

## Automation notes

- Fully automated: partial — skill creates monitors, operator still authors
  YAML per-client.
- Not automated: monitor-spec authoring itself (judgment-heavy).
- Future: capture the 27-constraint offer scorecard to pre-suggest keywords
  from `context/{client}/icp.md`.

## Change log

- v1.0 — 2026-04-22 — initial (Task 1.5.9a).
