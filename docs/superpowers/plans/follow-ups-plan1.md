# Plan 1 follow-up backlog

Non-blocking items surfaced by reviewers during Plan 1 execution. Each entry has provenance (which task's review raised it) so the fix lands in the right later window, not as Plan 1 scope creep.

## Hardening — address before Plan 2 wires webhooks

### 1. Rename `require_cron_secret` → `cron_secret_dep` (or expose inner `verify_cron_secret`)

**Raised by:** Task 8 code-quality review (2026-04-20)
**Severity:** Important (but reviewer explicitly advised deferring — naming footgun, not runtime bug)
**File:** `api/middleware/verify_signatures.py`

The current factory returns a `Depends(...)` object, so `dependencies=[require_cron_secret()]` reads like a predicate call but is actually a Depends-factory call. Two-part fix: rename to `cron_secret_dep` (or split into `verify_cron_secret` inner + wrapper), update call site in `api/routers/pipeline.py`. Webhook handlers in Plan 2 will land a sibling `verify_webhook_signature` pattern — align both names at the same time.

### 2. Add invalid-stage test to lock the `Literal` contract

**Raised by:** Task 8 code-quality review (2026-04-20)
**Severity:** Suggestion
**File:** `tests/test_api/test_pipeline_router.py`

```python
def test_pipeline_trigger_rejects_invalid_stage(client):
    r = client.post(
        "/api/pipeline/trigger",
        headers={"X-Cron-Secret": "test-cron"},
        json={"stage": "invalid_stage"},
    )
    assert r.status_code == 422
```

Documents the contract that SOPs hardcode (e.g., `"full"` stage). Four lines; add whenever the pipeline router is next touched.

### 3. Inline comment on pipeline stub clarifying `"accepted"` semantics

**Raised by:** Task 8 code-quality review (2026-04-20)
**Severity:** Suggestion
**File:** `api/routers/pipeline.py`

Current stub returns `status: "accepted"` for ANY valid stage — parsed, not dispatched. Silent-success footgun during the Plan 1 in-progress window (e.g., if cron hits `"render"` before Task 15 lands). Add an inline comment explaining the semantics until real dispatch replaces the stub in Tasks 9/10/12/14.

### 4. Log-capture safe `_configure_logging` in `api/main.py`

**Raised by:** Task 6 code-quality review (2026-04-20)
**Severity:** Suggestion
**File:** `api/main.py`

`_configure_logging` runs on every `create_app()` call and mutates structlog global state. Currently idempotent; but if a future test wants to use pytest's `caplog`, the JSONRenderer output may interfere. Guard with module-level `_LOGGING_CONFIGURED = False` flag if/when a log-capture test lands.

### 5. Module-level `app = create_app()` foot-gun in `api/main.py`

**Raised by:** Task 6 code-quality review (2026-04-20)
**Severity:** Important (latent, not active)
**File:** `api/main.py`

Any future test that does `from api.main import app` at module top-level will trigger `create_app()` → `get_settings()` before any monkeypatch fires → `ValidationError`. Current conftest.py sets env inside fixture, so it works. Mitigation when tripped: split into `api/main.py` (factory only) + `api/asgi.py` (module-level `app = create_app()`) — Procfile + railway.toml need the startCommand path updated to `api.asgi:app`.

## Test coverage — add when the dependency lands

### 7. Case-insensitive env var resolution test

**Raised by:** Task 3.7 code-quality review (2026-04-20)
**Severity:** Suggestion
**File:** `tests/test_config_settings.py`

`Settings.model_config` sets `case_sensitive=False`. Add one test locking that in against regression — `monkeypatch.setenv("manus_api_key", "m-key")` (lowercase) should resolve same as uppercase. Add on the first task in Plan 1 that actually relies on case-insensitive resolution, not before.

## Source adapter hardening — address before first live Clutch run

### 9. Distinguish "empty page" vs "CAPTCHA / rate-limit / layout-change" in ClutchAdapter pagination

**Raised by:** Task 9c code-quality review (2026-04-20)
**Severity:** Important
**File:** `systems/scout/sources/clutch.py` (termination logic around the empty-parse branch)

Current behaviour: when a Clutch page returns HTML but regexes match nothing, adapter treats it as end of listings and silently stops. A CAPTCHA interstitial, soft-block page, or layout change would masquerade as a successful-but-empty run in decision_log.

Fix: emit a `scout.source.empty_first_page` decision-log entry when page 0 yields 0 rows, treat it as a failed pull. Consider a response-length / marker-string check to distinguish real empty-state pages from error interstitials.

### 10. Handle HTTP 429 / 403 / 503 gracefully instead of aborting the pull

**Raised by:** Task 9c code-quality review
**Severity:** Important
**File:** `systems/scout/sources/clutch.py` (per-page `get + raise_for_status`)

Current behaviour: one rate-limit or soft-block mid-pull raises `httpx.HTTPStatusError` and the operator loses everything already scraped. Wrap the per-page block in `try/except httpx.HTTPStatusError` — on 429/403/503 (or any 5xx / network timeout), stop gracefully, return accumulated results, log a decision-log entry suggesting the ScraperAPI escalation trigger. Apply the same pattern to Apollo adapter while you're there.

### 11. Pairing-by-index parser fragility on sponsored rows / ad insertions

**Raised by:** Task 9c code-quality review
**Severity:** Important (time-bomb)
**File:** `systems/scout/sources/clutch.py::_parse_listing_page`

Current parser pairs `_NAME_PATTERN` matches with `_PROFILE_URL_PATTERN` matches by index. If Clutch injects a sponsored row producing a `"name":"..."` match without a matching profile URL, every subsequent row misaligns (name-A pairs with profile-B, etc.). The n8n JS has the same bug — porting verbatim was the right call for fidelity, but it remains a time-bomb.

Fix: extract `<div class="provider">` blocks first (selectolax / lxml) and regex within each block. Add a fixture with a mismatched count (4 names, 3 profile URLs) to lock in current behaviour until the block-based extractor lands.

### 12. `company_website=profile_url` is semantically misleading

**Raised by:** Task 9c code-quality review
**Severity:** Suggestion
**File:** `systems/scout/sources/clutch.py`

Storing the Clutch profile URL in `company_website` makes downstream code think it has a usable company domain. Fix: move profile URL exclusively into `raw_data["profile_url"]` (already there) and set `company_website=None`. Task 9.5 identity lookup populates the real domain.

### 13. Plan doc Protocol signature drift

**Raised by:** Task 9c code-quality review
**Severity:** Documentation fix
**File:** `docs/superpowers/plans/2026-04-20-foundation-scout-migration.md` (Task 9 prose)

Plan prose references `pull(client_id, icp_spec: ICPSpec, max_contacts, ...)`. Adopted Protocol in `systems/scout/sources/base.py` uses `max_companies` with no `icp_spec` arg (adapters accept source-specific filters via `**kwargs`). Update plan prose to match reality so the next executing agent doesn't get confused.

## Pull orchestrator cleanup — bundle with Task 17 wiring

### 14. Add `source_selection` to `decision_log.decision_type` CHECK constraint

**Raised by:** Task 9d code-quality review (2026-04-20)
**Severity:** Important (vocabulary squat)
**File:** `scripts/sql/001_foundation.sql` (CHECK constraint at line 141-146) + `systems/scout/pipeline/pull.py` (switch from `enrichment_choice` to `source_selection`)

Pull-stage source routing currently logs as `enrichment_choice` which is reserved for Task 12's enrichment-vendor decisions. When the weekly report asks "success rate of enrichment_choice", pull-source health + enrich-vendor health get averaged together. Fix: schema migration adding `source_selection` to the allowed `decision_type` values; update pull orchestrator to emit it.

### 15. Pull orchestrator suggestions (Task 9d CQ S1–S7)

**Raised by:** Task 9d code-quality review (2026-04-20)
**Severity:** Suggestions — roll into Task 17 integration pass
**File:** `systems/scout/pipeline/pull.py`

- S1: add `total_errored: int` computed property on `PullResult`
- S2: decide + document empty `source_filter=[]` semantics (ValueError vs pass-through)
- S3: add test for ghost-adapter + `source_filter` interaction
- S4: already partially done in hardening (structured context) — verify richer counts are consumed by Plan 4 cost-report queries
- S5: reject reserved kwarg keys (`client_id`, `max_companies`, `dry_run`) in `adapter_kwargs`
- S6: raise `ValueError` on duplicate adapter names in `PullOrchestrator.__init__`
- S7: add one-line comment near `normalize_domain(row.company_domain)` noting it's defensive idempotency against non-normalising adapters

## Refactor — trigger at ~6 lead-stack keys

### 8. Move vendor config to `data/reference/vendor_stack.yaml`

**Raised by:** Task 3.7 code-quality review (2026-04-20)
**Severity:** Suggestion (data-driven refactor)
**Files:** new `data/reference/vendor_stack.yaml`; `config/settings.py` (simplify)

Two-bucket "primary vs escalation" comment grouping scales fine up to ~6 total keys. Beyond that, keep only raw API key env-vars in `Settings` and move the metadata (trigger rules, tier gates, cost caps) to a YAML file in `data/reference/`. Aligns with CLAUDE.md's "customisation is data, not code" and `feedback_productised_not_custom`. Fire the refactor at the 6-key threshold (adding RocketReach, ContactOut, Surfe, etc. would cross it), not sooner.

## Schema cleanup — address in a future migration

### 6. Drop legacy `enrichment_budget_per_contact_cents` column from `client_config`

**Raised by:** Amendment 1 architecture decision (2026-04-20) → Task 3.6 migration
**Severity:** Low (dead column, not referenced by new code)
**File:** new migration `scripts/sql/NNN_drop_legacy_enrichment_budget.sql`

Task 3.6 added `tier_budgets_cents` JSONB which supersedes the single `enrichment_budget_per_contact_cents` INT column from `002_scout.sql`. Drop the legacy column after confirming no read paths in Plan 1 or Plan 2 code touch it. Hold until Plan 1 e2e dry-run is green to avoid schema churn during execution.

## Process notes

- Items 1, 5: "Important" severity but reviewer explicitly advised deferral because the issue is latent (no Plan 1 test trips it).
- Items 2, 3, 4: "Suggestion" severity — pure quality wins.
- Item 6: clean-up dependent on validation that no code path reads the old column.

Fold these into the "hardening pass" before Plan 2 kicks off.
