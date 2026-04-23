-- 008_budget_tracking.sql
-- Adds rolling per-tier spend tracking to client_config for
-- SupabaseBudgetTracker. Depends on 003_client_config_extensions.sql
-- (which introduced tier_budgets_cents with the same tier keys).
--
-- SupabaseBudgetTracker computes remaining = tier_budgets_cents[tier] -
-- tier_spent_cents[tier] and fails safe (remaining = 0) when either side
-- is missing. Monthly reset is a future scheduler job (Task 16.6).
--
-- Idempotent: ADD COLUMN IF NOT EXISTS + DEFAULT '{}' so re-runs are safe.

BEGIN;

ALTER TABLE client_config
    ADD COLUMN IF NOT EXISTS tier_spent_cents JSONB NOT NULL DEFAULT '{}';

COMMENT ON COLUMN client_config.tier_spent_cents IS
    'Rolling per-tier spend in cents, map {tier: cents_spent}. SupabaseBudgetTracker reads this subtracted from tier_budgets_cents to compute remaining budget. Reset monthly by scheduler (Task 16.6).';

COMMIT;
