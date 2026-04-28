-- 019_contacts_cool_off.sql
--
-- Plan 2 Phase 3 Task 2.3.4: cool-off + round-based re-entry.
--
-- Adds two columns to ``contacts``:
--   sequence_round  — which round of outreach this contact is in.
--                     Defaults to 1; increments on cool-off re-entry.
--   cool_off_until  — when the contact's cool-off period ends.
--                     NULL when contact is not cooling off.
--
-- Note on contacts.status:
-- The status column is TEXT with no CHECK constraint (see 002_scout.sql
-- line 119 — values documented as a comment). New status value
-- 'cooling_off' added by code-only — no schema change.
--
-- Idempotent — safe to re-run.

ALTER TABLE contacts
    ADD COLUMN IF NOT EXISTS sequence_round INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS cool_off_until TIMESTAMPTZ;

-- Index for "find contacts ready to re-enter" query: status='cooling_off'
-- + cool_off_until <= now().
CREATE INDEX IF NOT EXISTS idx_contacts_cool_off_ready
    ON contacts (client_id, cool_off_until)
    WHERE cool_off_until IS NOT NULL;
