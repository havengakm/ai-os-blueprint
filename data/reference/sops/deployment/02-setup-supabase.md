# SOP: Setup Supabase for New Client Deployment
Version: 1.0
Last reviewed: 2026-04-20
Owner: Kirsten / VA

## Purpose
Create a fresh Supabase project for a new client, run foundation + Scout schema migrations, and capture credentials. Every client gets their own Supabase project (no shared DB) — full data isolation per CLAUDE.md Data Protection rules.

## Trigger
New client signed, Step 2 of Client Deployment SOP.

## Inputs
- Client name (slug + display name)
- Client's preferred region (proximity to target market)
- Access to Kirsten's Supabase org

## Outputs
- Live Supabase project named `{client-slug}-ai-os`
- Both migrations executed successfully
- `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` + `SUPABASE_ANON_KEY` recorded for `.env`

## Steps
1. Go to https://supabase.com/dashboard → New project.
2. Name it `{client-slug}-ai-os`. Region = closest to client's target market. Plan = Free (upgrade to Pro at 5 clients).
3. Generate and store DB password in password manager (1Password / Bitwarden).
4. Wait for project provisioning (~2 min).
5. Open SQL Editor → paste contents of `scripts/sql/001_foundation.sql` → Run. Check for errors.
6. Same editor → paste contents of `scripts/sql/002_scout.sql` → Run.
7. Verify tables exist via `SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';`
8. Project Settings → API → copy `URL`, `anon key`, `service_role key`. Save to password manager + add to client's `.env`.

## QA
- All expected tables present (20+)
- Running a SELECT on each table returns 0 rows without error
- Service role key tested via `curl -H "apikey: <key>" <url>/rest/v1/clients`

## Common errors
| Error | Cause | Fix |
|---|---|---|
| `extension "vector" does not exist` | pgvector not enabled | Database → Extensions → enable `vector` |
| `extension "pgcrypto" does not exist` | pgcrypto not enabled | Database → Extensions → enable `pgcrypto` |
| `relation already exists` | Running 001 twice | Drop schema and restart, or skip 001 |

## Escalation
If migration fails > 2 times: stop, capture full error output, escalate to Kirsten before retrying.

## Automation notes
- Fully automated: no — manual dashboard steps required
- Partially automatable: project creation via Supabase Management API (future enhancement)
- Not automated: DB password generation (intentional — stored outside code)

## Change log
- v1.0 — 2026-04-20 — initial
