# SOP: Deploy AIOS to Railway (single client)
Version: 1.0
Last reviewed: 2026-04-22
Owner: Kirsten (operator)

## Purpose

Deploy AIOS from a clean clone to a running Railway service with one client
fully onboarded. Covers build config, env vars, Supabase migrations, client
context authoring, and smoke verification.

Companion SOPs:
- `deployment/02-setup-supabase.md` — per-client Supabase project + schema
- `trigify-monitor-authoring.md` — per-client monitor YAML
- `component-authoring.md` — per-client component tree (if authored separately)

## Owner

- Initial deploys: Kirsten (operator)
- Ongoing runtime: Scout daemon (Task 16.6, pending)

## Trigger

- New Railway deployment (fresh project)
- Major code release (new migration or new required env var)
- New client onboarding (re-uses existing Railway service, new Supabase project)

## Inputs

- GitHub repo + commit SHA to deploy
- Client ID slug (e.g. `acme-co`)
- All 10 env vars listed in `railway.toml` header
- Per-client context YAMLs:
  - `context/{client-id}/trigify_monitors.yaml`
  - `context/{client-id}/components.yaml` (if authored)
  - `context/{client-id}/knowledge/` markdown (if authored)
  - `context/{client-id}/email_patterns.yaml` seed (optional; Plan 1.5)

## Outputs

- Running Railway service, `/health` returns 200
- Supabase schema at migration 009 (007 pending Plan 1.5)
- Client fully onboarded via `scripts/setup_client.sh {client-id}`
- First dry-run pipeline call returns a `PullSummary` with zero failures
- `decision_log` table shows stage activity for the client

## Steps

1. **Create Railway project.** https://railway.app → New → Deploy from GitHub
   repo. Select `main` branch. Railway reads `railway.toml` at repo root.
2. **Set env vars.** Railway dashboard → Variables → add all 10:
   `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `VOYAGE_API_KEY`,
   `ANTHROPIC_API_KEY`, `TRIGIFY_API_KEY`, `APOLLO_API_KEY`, `HUNTER_API_KEY`,
   `ZEROBOUNCE_API_KEY`, `CRON_SECRET`, `CLIENT_ID`. Or via CLI:
   `railway variables set KEY=value`.
3. **Push commit.** Railway builds via `buildCommand` from `railway.toml`:
   `uv sync --frozen && uv run playwright install --with-deps chromium`.
   First build is slow (~5 min) due to Chromium download + OS deps. Subsequent
   builds cache the Playwright layer.
4. **Connect Supabase project.** Provision per `deployment/02-setup-supabase.md`
   (Free tier up to 5 clients, then Pro). Paste `SUPABASE_URL` +
   `SUPABASE_SERVICE_ROLE_KEY` into the Railway env vars set in step 2.
5. **Apply migrations in order.** Supabase SQL editor (or `psql`), paste and
   run each file from `scripts/sql/` in this sequence:
   `001_foundation.sql` → `002_scout.sql` → `003_client_config_extensions.sql`
   → `004_contacts_extensions.sql` → `005_foundation_completion.sql` →
   `006_component_registry.sql` → `008_budget_tracking.sql` →
   `009_trigify_discovery_config.sql`. Note: `007_email_discovery.sql` is
   **pending Plan 1.5** — skip it for Plan 1 deploys.
6. **Verify schema.** From any shell with Supabase env vars exported:
   ```
   uv run python -c "from os_foundation.supabase_client import get_supabase; \
     s = get_supabase(); \
     r = s.rpc('exec', {'sql': \"SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1\"}).execute(); \
     print(r.data)"
   ```
   Or in Supabase SQL editor:
   `SELECT table_name FROM information_schema.tables WHERE table_schema='public';`
   Expect 20+ tables including `clients`, `contacts`, `decision_log`,
   `component_registry`, `trigify_monitors`, `budget_ledger`.
7. **Clone repo locally** (or open Railway shell) to run onboarding.
8. **Author per-client context.** Populate `context/{client-id}/`:
   - `trigify_monitors.yaml` per `trigify-monitor-authoring.md`
   - `components.yaml` per `component-authoring.md` (if used)
   - `knowledge/*.md` per client knowledge base SOP
9. **Run onboarding.** From repo root with env vars exported:
   ```
   bash scripts/setup_client.sh {client-id}
   ```
   This sequences autonomy rules → knowledge → context → components →
   Trigify monitors. Shipped in Task 16b Step 3.
10. **Smoke verify over HTTP.** Replace `$APP_URL` with the Railway domain:
    ```
    curl $APP_URL/health
    # → 200 {"status":"ok"}
    curl $APP_URL/openapi.json | jq '.paths | keys'
    # → includes /api/pipeline/pull, /enrich, /score, /discover, /onboard, /trigger
    ```
11. **Dry-run pipeline.** Fires through pull stage without writing prospects:
    ```
    curl -X POST $APP_URL/api/pipeline/pull \
      -H "Content-Type: application/json" \
      -d '{"client_id": "{client-id}", "dry_run": true, "limit": 10}'
    ```
    Expect a `PullSummary` JSON with zero failures.
12. **Confirm decision log activity.** In Supabase SQL editor:
    ```
    SELECT stage, action, created_at
    FROM decision_log
    WHERE client_id = '{client-id}'
    ORDER BY created_at DESC LIMIT 20;
    ```
    Expect rows from the dry-run above.

## QA

- `/health` returns 200
- `/openapi.json` renders all 6 pipeline routes
- Dry-run pull produces expected counts (0 failures, matching `limit`)
- `decision_log` shows rows from the dry run
- Railway build log shows the Playwright install step completed

## Errors & resolutions

| Error / symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'playwright'` | `uv sync` step of `buildCommand` did not run | Check `railway.toml` `buildCommand` present; re-deploy |
| `Executable doesn't exist at .../chromium` | Playwright binaries missing | Confirm `buildCommand` uses `--with-deps chromium`; clear build cache + redeploy |
| `Playwright Host validation warning` on OS deps | `--with-deps` omitted | Add `--with-deps` to buildCommand |
| App exits at startup, log: `SUPABASE_URL not set` | Env var missing in Railway | Dashboard → Variables → add → redeploy |
| Any `KEY not set` at startup | One of the 10 env vars missing | Cross-check list in `railway.toml` header |
| `401 Unauthorized` on `/api/pipeline/trigger` | `CRON_SECRET` mismatch between caller + Railway | Regenerate + update caller |
| Supabase `column "xyz" does not exist` | Migration skipped or out of order | Re-run missing migration; they're idempotent only in `CREATE IF NOT EXISTS` blocks, check errors |
| `extension "vector" does not exist` | pgvector not enabled | Supabase → Database → Extensions → enable `vector` |
| Healthcheck fails, container crash loops | Container hits `restartPolicyMaxRetries=3` | Railway logs → read traceback → fix root cause, do NOT just bump retry count |
| Build succeeds, deploy fails with import error | Missing env var at `api.main:create_app` | `config/settings.py` hard-requires env vars; check step 2 |

## Escalation

- **Playwright install fails after 3 retries:** flag in Railway Discord, or open
  a PR adjusting `buildCommand` (e.g. pin Playwright version, swap installer).
- **Migration failure:** operator applies SQL manually via Supabase SQL editor
  and re-deploys. Capture full error output before retrying.
- **Repeated healthcheck failures:** stop the service, inspect logs, fix
  locally before redeploying. Do not loop Railway restart policy.

## Multi-service config (web + scout-daemon)

AIOS deploys as two Railway services from a single repo: the `web` FastAPI
app (public pipeline endpoints) and the `worker` Scout daemon (nightly
pipeline). Source-of-truth rules:

- **`Procfile` at repo root is canonical.** Railway's Nixpacks builder reads
  every line (`web:`, `worker:`) and spawns one service per line. Edit the
  Procfile when adjusting start commands or adding a new long-running
  process.
- **`railway.toml [[services]]` is commented out.** During Task 16.6 review
  we confirmed that running both sources at once caused the worker to
  silently not materialise on first deploy while the web service reported
  success. The `[[services]]` array is the Railway v2 multi-service schema,
  not uniformly GA, and is kept in the file only as a forward-migration
  reference. Do not uncomment without re-testing end-to-end.
- **`railway.toml [build]` + `[deploy]` still apply** — they govern the
  builder, build command (Playwright install), healthcheck path, and the
  default/primary service's deploy policy.

**Verify both services materialise after first deploy:**

1. Railway CLI: `railway service list` → expect entries for both `web` and
   `worker` (names come from the Procfile keys).
2. Railway dashboard: project → Services pane → confirm two tiles, each
   with a green "Deployed" status.
3. Logs check — `web` service logs should show `Uvicorn running on ...`;
   `worker` service logs should show `daemon startup cron=... dry_run=...
   env=...` (emitted by `aios.daemon.main.run_daemon`).
4. If `worker` is missing: check that Nixpacks detected the Procfile (build
   logs will mention "Using Procfile"). If not, force a fresh build
   (Railway → Deployments → Redeploy without cache).

## Automation

- **Task 16.6 (shipped):** Scout daemon runs as the `worker:` process in
  `Procfile`. Nightly cycle iterates every active client. See "Multi-service
  config" above for deploy verification.
- **Task 17 (pending):** end-to-end dry-run validates the full pipeline
  post-deploy as part of CI before promoting a release.
- **Not automated:** Supabase project creation, migration application, per-client
  context authoring. All remain operator-driven until Plan 2.

## Change log

- v1.0 — 2026-04-22 — initial. Closes backlog item 19 (Playwright install on Railway).
- v1.1 — 2026-04-22 — add "Multi-service config" section clarifying Procfile is
  canonical (Task 16.6 pre-deploy review fix); `[[services]]` in railway.toml
  is commented out as forward-migration reference.
