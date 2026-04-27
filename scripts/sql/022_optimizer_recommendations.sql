-- 022_optimizer_recommendations.sql
--
-- Plan 2 Phase 5 Task 2.5.2: Optimizer recommendation persistence.
--
-- The Optimizer agent (Task 2.5.1) emits read-only recommendations; the
-- operator approves or rejects via the inbox-style API at
-- ``api/routers/optimizer.py``. Approved recommendations are applied by
-- the Task 2.5.3 applicators (bandit weight adjustments, variant
-- retirement, adapter scoring weights, autonomy promotions).
--
-- Plan-doc-numbering note: spec named this migration 019; renumbered to
-- 022 because 019 (cool-off), 020 (cost rollup), 021 (coverage rollup)
-- were used in earlier Phase 3 + Phase 4 slices. Same semantics.

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS optimizer_recommendation (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    category        TEXT NOT NULL CHECK (category IN (
        'bandit_weight_adjustment',
        'variant_retirement',
        'adapter_score_weight',
        'autonomy_promotion',
        'grader_calibration',
        'send_time_shift',
        'cool_off_threshold'
    )),
    payload         JSONB NOT NULL DEFAULT '{}'::JSONB,
    confidence      NUMERIC(3,2) CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
    ),
    reasoning       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'approved', 'rejected', 'expired'
    )),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_by     TEXT,                   -- operator email
    reviewed_at     TIMESTAMPTZ,
    applied_at      TIMESTAMPTZ,            -- set when applicator runs successfully
    apply_error     TEXT                    -- set when applicator fails
);

-- Operator dashboard query: pending recommendations, newest first.
CREATE INDEX IF NOT EXISTS idx_optimizer_rec_pending
    ON optimizer_recommendation (client_id, created_at DESC)
    WHERE status = 'pending';

-- Auto-expire query: pending rows older than the threshold.
CREATE INDEX IF NOT EXISTS idx_optimizer_rec_pending_age
    ON optimizer_recommendation (created_at)
    WHERE status = 'pending';
