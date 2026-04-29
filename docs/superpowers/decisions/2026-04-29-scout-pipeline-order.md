# Decision: Scout pipeline order — cheap-resolve before score, expensive-resolve after

**Date:** 2026-04-29
**Status:** Proposed
**Decider:** Kirsten
**Drafted by:** Claude (AIOS agent) during Slice 15 of 2026-04-29
**Affects:** `aios/daemon/client_worker.py::STAGE_ORDER`, `systems/scout/identity/orchestrator.py` (split into two stages), score_v1 weights, AdapterFactory wiring, `client_config.active_directories` per-source ICP filters, Clutch employee-band parsing, `feedback_enrichment_tiers` memory.

---

## Context

The 2026-04-29 Scout pull end-to-end test (Slices 11-15) shipped three production fixes
(orchestrator naming, Cloudflare bypass, parser enrichment) and ran a live Phase B with
real Clutch agencies. Result: **5 contacts inserted with rich data, all archived at
`score_v1`**. Investigation showed two distinct issues operating together:

1. **Pipeline ordering**: `score_v1` runs immediately after `pull` with whatever data the
   pull-stage adapter could harvest from a listing card. For Clutch, that's now (post-Slice
   15 parser): name, city, state, country, employees-band-upper, profile_url. **Industry,
   title, domain, email, person-data are all `None` until `identity` runs at stage 4** —
   but `identity` only operates on contacts that survived `score_v1`. Contacts that score
   below `archive_floor=35` (because they look thin, not because they actually mismatch
   ICP) get archived BEFORE the data needed to score them properly is fetched.

2. **Source/ICP fit on Clutch's `agencies/digital-marketing`**: that category lists
   agencies in employee bands `50-249`, `250-999`, `1,000+`. Clymb's ICP says `2-50`.
   So even if scoring were perfect, every result on this category fails the size band.
   This is a real source/ICP mismatch — Scout is correctly rejecting them; the issue is
   we picked the wrong Clutch sub-category for Clymb's ICP.

Both issues need decisions. The pipeline-ordering question is the architectural one and
affects every client deployment going forward; the ICP-coverage question is a
per-deployment configuration concern and is captured in section "Implementation".

This doc captures the architectural decision. The operator-driven ICP-coverage call is
recorded in the Implementation section as a per-Clutch-deployment note.

---

## Decision — one-sentence summary

**Scout adopts Pattern C — split identity resolution into a cheap-domain stage
(Hunter Domain Search + free-tier directory profile scrape) that runs BEFORE
`score_v1`, and an expensive-person stage (Apollo People Search + Claude scraper)
that runs AFTER `score_v1` passes — so scoring sees domain + industry + person-count
band data without spending per-call API credits on contacts that obviously fail ICP
on the cheap-data alone.**

---

## The three patterns considered

### Pattern A — resolve-then-score (always identity, always full)

```
pull → identity (full waterfall) → score_v1 → screen → enrich → score_v2 → compose
```

Every pulled contact runs through the full identity waterfall (Apollo People Search →
Hunter → Claude scraper) before scoring. `score_v1` sees rich data: domain, industry,
title, person, email.

**Pros**: best signal at score_v1; no contact archived for missing data.
**Cons**: spends Apollo/Hunter/Claude on every pulled contact regardless of fit. At
50 pulls/day × 30 days × ~$0.05/contact identity-cost = ~$75/mo just on identity for
contacts that may fail at obvious ICP boundaries. Scales linearly with pull volume.
Doesn't honour `feedback_lead_sourcing` rule "Apollo last-resort".

### Pattern B — score-then-resolve (current as of 2026-04-29)

```
pull → score_v1 → screen → identity → enrich → score_v2 → compose
```

`score_v1` runs on pull-stage data only. Identity runs after score+screen, so only
on contacts that look promising on cheap data. Apollo/Hunter/Claude only spent on
score-survivors.

**Pros**: cheap; respects `feedback_enrichment_tiers` rule "research/phone gated by
icp_score".
**Cons**: archives contacts whose only "miss" is that pull-stage didn't include the
data needed to score them. The Slice 15 finding: 5 perfectly-good Clutch agency
listings archived at `score_v1` because pull doesn't include `industry` or `title`,
and `score_v1` weights those at 40% fit. Even fixing the parser to harvest more
listing-card fields didn't help because **the listing card fundamentally doesn't
have person-level data, only company-level**.

### Pattern C — cheap-resolve before, expensive-resolve after (recommended)

```
pull → cheap_resolve → score_v1 → screen → expensive_resolve → enrich → score_v2 → compose
```

Two-stage identity resolution split by cost-class:

- **`cheap_resolve`** runs immediately after pull, before score_v1. Uses only
  free-tier or per-call-cheap signals:
  - **Hunter Domain Search** by company name → returns domain + company industry tag
    (Hunter charges per *contact*, not per domain lookup; domain search is on
    the free tier, then $49/500 if exhausted).
  - **Directory profile scrape** (Clutch profile page, Clutch / DesignRush /
    GoodFirms): for adapters that already use Playwright for Cloudflare bypass,
    one extra page fetch is marginal. Profile pages typically expose
    industry tags, services, hourly rate, year founded, employee band.
  - **Cheap signals add to the contact record**: `company_domain`,
    `industry`, optionally `year_founded`, `services_offered_tags`.

- **`expensive_resolve`** runs after `score_v1` + `screen` pass. Uses paid APIs:
  - **Apollo People Search** by company → decision-maker first/last name + title +
    work email + LinkedIn.
  - **Claude scraper** as last-resort fallback for hard cases.

**Pros**: score_v1 sees domain + industry on every contact (so it can actually score
fit); paid APIs only spent on score-survivors; honours both `feedback_lead_sourcing`
and `feedback_enrichment_tiers` rules; matches `feedback_value_first_efficiency`
("efficiency through quality parity, not quality reduction").

**Cons**: adds a stage to the pipeline (one more thing that can fail); cheap-resolve
adapters need to be built for new directories (Hunter's domain search is reusable but
the per-directory profile scrape is per-source code); slightly higher complexity in
`STAGE_ORDER`.

**Cost model** (per pulled contact, kirsten-client-zero scale):

| Stage | Pattern A | Pattern B (current) | Pattern C (proposed) |
|---|---|---|---|
| Pull | ~$0 (Clutch scrape) | ~$0 | ~$0 |
| Cheap-resolve | n/a | n/a | ~$0.02 (Hunter free tier domain lookup; cached after 25/mo at $49/500) |
| Score_v1 | $0 | $0 | $0 |
| Screen | $0 | $0 | $0 |
| Expensive-resolve / Identity | ~$0.05 (every contact) | ~$0.05 (only score-survivors, ~30%) | ~$0.05 (only score-survivors, ~30%) |
| Enrich | gated by ICP tier | gated by ICP tier | gated by ICP tier |
| **Total per 100 pulls** | ~$5.00 | ~$1.50 | ~$3.50 |

Pattern C is more expensive than B (~+$2/100 pulls) but **catches contacts
that B silently archives**. The lift in qualified-pipeline volume should
more than offset the marginal cost; if it doesn't, the per-tier budget caps
catch it via `feedback_cost_management`.

---

## Decision — Pattern C, with these specifics

### 1. STAGE_ORDER changes

```python
# aios/daemon/client_worker.py
STAGE_ORDER: tuple[str, ...] = (
    "pull",
    "cheap_resolve",   # NEW: domain + industry, no person-level
    "score_v1",
    "screen",
    "identity",        # RENAMED FROM identity-as-full-waterfall to expensive_resolve
    "enrich",
    "score_v2",
    "compose",
)
```

`identity` keeps its name (semantically still "identity resolution") but its
behaviour narrows to person-level only. `cheap_resolve` is the new stage.

### 2. cheap_resolve adapters

| Adapter | Source | Cost | Returns |
|---|---|---|---|
| `HunterDomainResolver` | Hunter `/domain-search` by company name | Free tier 25/mo, then $49/500 | domain, industry, country |
| `ClutchProfilePageResolver` | Per-source: re-use the source's Playwright session to fetch the profile page | $0 (one extra page fetch) | industry, services, hourly rate, year founded, employee band confirmation |
| `DesignRushProfileResolver` | (Future) | $0 | same shape |

The orchestrator runs them in priority order, first-hit wins on each field. If both
Hunter AND profile-page yield an industry tag, prefer profile-page (more specific to
the actual agency, not Hunter's general guess).

### 3. score_v1 weight rebalancing

Current weights: `fit=40, intent=30, reach=20, recency=10` (sum to 100).

`fit` is currently weighted on:
- industry match (vs ICP)
- title match (vs ICP)
- employee band (vs ICP)
- geography (vs ICP)

After cheap_resolve, `industry` and `employee` and `geography` are reliably populated.
`title` is still null until expensive_resolve. Adjust the score_v1 fit calculation
so it explicitly tolerates `title=None` (treat as neutral, don't penalise) instead of
zero-scoring it. The score_v1 implementation lives in `systems/scout/pipeline/score.py`
— check that the fit function's behaviour with `title=None` is "skip, don't penalise".

If implementation already does this, no change needed. If it penalises, fix it in
the same slice that adds `cheap_resolve`.

### 4. Clutch employee-band parsing — keep upper-bound

Today's Slice 15 parser uses upper-bound: "10-49" → 49, "50-249" → 249, "250-999" → 999.

For Clymb's tight 2-50 ICP, this is correct:
- "2-9" → 9 ≤ 50 → PASS ✅
- "10-49" → 49 ≤ 50 → PASS ✅
- "50-249" → 249 > 50 → FAIL ✅ (operator: "agencies over 50 are too large")
- "250-999" → 999 > 50 → FAIL ✅
- "1000+" → 1000 → FAIL ✅

Lower-bound or median would let "50-249" agencies pass (their lower bound is 50,
which is exactly at the limit). Operator's intent is to exclude that band — too many
decision-making layers, harder to reach the buyer. Upper-bound is the right heuristic
for tight-ICP small-agency targeting.

**Future-state**: when Clymb's case studies expand to mid/larger agencies, revisit
band parsing. Options at that point:
- Switch to lower-bound (more permissive)
- Add a "use-band-lower-bound-for-fit" flag on `client_config`
- Fan out per-band into multiple "tier" buckets and score per-band

Not a today problem. Decision: keep upper-bound.

### 5. ICP-coverage on Clutch — operator's per-deployment guidance

For Clymb (kirsten-client-zero):
- **Target Clutch sub-categories with smaller agencies**: `agencies/digital-marketing`
  is full of mid/large agencies. Need to find or filter to a category that has 2-50
  employee agencies. Options:
  1. Use Clutch's URL filter `?employees=2-49` if it exists (verify in step-1 of any
     adapter implementation).
  2. Page deep into the listing — small agencies typically rank lower.
  3. Pick a category that intrinsically has small agencies (e.g., `agencies/branding`,
     `agencies/creative`, freelance directories).
- **Default ICP stays `employee_min=2, employee_max=50`** until Clymb has case studies
  with larger agencies.

Documented in this doc; not a code change.

### 6. Memory + skill updates

- New memory entry `feedback_pipeline_resolve_split.md` — "cheap-resolve before
  score, expensive-resolve after; Hunter + profile-scrape are cheap, Apollo +
  Claude-scraper are expensive; per `feedback_cost_optimiser_continuous_concern`
  every paid API call gates on score".
- Update `feedback_enrichment_tiers.md` — clarify the tier definitions: the
  archive-floor=35 gate still holds, but now applies AFTER cheap_resolve has run,
  not on bare pull-stage data.

---

## Affects (code, config, memory)

### Code

- `aios/daemon/client_worker.py` — add `cheap_resolve` to `STAGE_ORDER`; route the new
  stage in `_run_one_stage`. Tests in `tests/test_daemon/test_client_worker.py` need
  the new stage in expectations.
- `systems/scout/skill.py` — add `run_cheap_resolve` method. Foundation-loop priming
  matches existing pattern.
- `systems/scout/identity/cheap_resolve_orchestrator.py` (new) — runs the cheap-tier
  adapters in priority order, first-hit wins on each field.
- `systems/scout/identity/cheap_*` — new cheap adapters: `hunter_domain.py`
  (already exists for full identity; refactor to expose domain-only mode);
  `clutch_profile_resolver.py` (new — uses the existing ClutchAdapter's Playwright
  page); `designrush_profile_resolver.py` (future).
- `aios/daemon/adapter_factory.py` — `build_cheap_resolve_orchestrator` factory
  method.
- `systems/scout/pipeline/score.py` — verify `title=None` is neutral, not zero.

### Config

- `client_config` schema unchanged. Cheap-resolve adapters are wired on by the
  factory based on env keys (Hunter domain) + `active_directories` (per-source
  profile resolvers).

### Tests

- New tests for cheap-resolve orchestrator (mirror identity orchestrator pattern).
- Update STAGE_ORDER tests in `test_client_worker.py`.
- New live-Phase-B verification with cheap_resolve in place: expect the 5 Clutch
  agencies to gain `domain` + `industry` post-cheap-resolve, then archive at
  score_v1 with explicit reasoning ("employees=999 exceeds icp_max=50") rather
  than bland "fit=0".

### Memory

- New: `feedback_pipeline_resolve_split.md`.
- Update: `feedback_enrichment_tiers.md` (clarify tier-gating point in the new pipeline).

### Plan

- Add a Plan 2 follow-up task or Plan 3 entry: "Pattern C migration (cheap_resolve
  stage)". Estimate: 4-6 hours including tests + live verification.

---

## Migration path

1. **Existing kirsten-client-zero state**: 36 contacts. Of those, 5 are post-parser
   Clutch agencies that all archived at score_v1 due to ICP/source mismatch (their
   employees-band exceeds 50). Pattern C wouldn't change their fate — even with
   cheap_resolve filling in industry, they'd still fail employees=249/999 vs icp=50.
   So: no migration needed for those 5; they're correctly archived.
2. **Future kirsten-client-zero pulls** (after Pattern C ships): pull from a different
   Clutch sub-category that has small agencies. The cheap_resolve stage will fill in
   domain + industry; score_v1 will properly evaluate fit; survivors enter
   expensive_resolve and continue.
3. **New client deployments**: get Pattern C from day one. No legacy migration.

---

## Open questions / future considerations

1. **Hunter domain search free-tier exhaustion**. 25/mo free; ~$49 for 500. At 50
   pulls/day per client × 1 client = 1500/mo, we'd burn through free tier in ~half a
   day. Either (a) cache aggressively (domain rarely changes per company), (b) accept
   ~$50/mo Hunter cost, or (c) fall back to Clutch profile-page scrape as the primary
   domain source and skip Hunter for Clutch contacts. Decision: cache + start with
   profile-scrape primary; only call Hunter when profile-scrape doesn't yield domain.
2. **When does cheap_resolve become expensive_resolve**? The line is fuzzy. If
   Hunter starts charging per domain lookup or rate-limits hard, "cheap" no longer
   applies. Revisit if Hunter's pricing changes or volume forces upgrade tiers.
3. **What about per-source overrides**? Some sources (Trigify) already include person
   data in the pull. For those, the cheap_resolve step is redundant. Solution: each
   adapter can declare which fields it provides; cheap_resolve skips fields already
   set. Implementation detail, not a decision.
4. **Score_v1 weights and ICP tightness**. With Clymb's 2-50 ICP, fit-by-employee-
   band is a strong signal. With looser ICPs, employees becomes less discriminating
   and other fit dimensions (industry, title) matter more. The current weight set
   (fit=40, intent=30, reach=20, recency=10) was chosen for tight-ICP scenarios.
   Future loose-ICP clients may need rebalanced weights — handled per-client via
   `client_config.weights` (already supports this).
5. **When to revisit Pattern C → A or B**? Trigger conditions:
   - Cheap-resolve cost crosses $0.05/contact (no longer "cheap").
   - Score_v1 archive rate stays > 95% even with cheap-resolve fill (signal is
     coming from elsewhere).
   - Operator manually overrides 30%+ of score_v1 archives within a quarter
     (signal: scoring is too aggressive, not too weak).

---

## Open loop registered

`memory/INDEX.md` Open Loops:
- Pattern C migration: implement `cheap_resolve` stage (4-6h scope) — depends on this
  doc being accepted. Triggers: when next operator-Scout test cycle runs OR when next
  client deployment starts.
- Re-test Phase B with Pattern C in place + a small-agency Clutch sub-category — should
  see contacts move past `score_v1`.
