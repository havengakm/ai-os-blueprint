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
