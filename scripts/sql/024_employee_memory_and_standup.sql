-- 024_employee_memory_and_standup.sql
--
-- Phase 1 of the structural rewrite (per docs/architecture/aios-structural-plan-2026-04-29.md).
-- Adds five tables that materialise the new Employee + COO + decision-feedback-loop
-- abstractions:
--
--   employee_memory          per-employee semantic memory, vector-indexed
--   employee_subscriptions   peer-to-peer learning routing rules
--   learning_events          fire-and-forget cross-employee learning channel
--   daily_dispatches         COO's per-employee task brief (one per client+employee+day)
--   weekly_recaps            COO's team synthesis (one per client+week)
--
-- Per-deployment isolation: every table includes client_id and is filtered by it
-- in every query. Foreign-key to clients(id) so deleting a client cascades the
-- whole memory + standup history.
--
-- pgvector extension is already enabled by 001_foundation.sql. embedding(1024)
-- matches the dimension currently used by aios/foundation/embedder.py.

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- =========================================================================
-- employee_memory — per-employee semantic memory store
-- =========================================================================

CREATE TABLE IF NOT EXISTS employee_memory (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    employee_id     TEXT NOT NULL,                 -- 'prospect-researcher' | 'outreach-manager' | etc.
    kind            TEXT NOT NULL CHECK (kind IN (
        'job_completion',     -- terminal artifact of a workflow run
        'learning',           -- a piece of cross-employee learning consumed via subscription
        'observation',        -- something the employee noticed but didn't act on
        'recap',              -- daily/weekly recap snippet
        'synthesis',          -- COO synthesis output
        'dispatch'            -- daily dispatch read receipt
    )),
    content         TEXT NOT NULL,                 -- the memory body (LLM-readable)
    embedding       VECTOR(1024),                  -- nullable until embedder runs
    metadata        JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_employee_memory_client_employee
    ON employee_memory (client_id, employee_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_employee_memory_kind
    ON employee_memory (client_id, employee_id, kind);

-- pgvector ANN index — same shape as decision_log.embedding from 001_foundation.sql.
CREATE INDEX IF NOT EXISTS idx_employee_memory_embedding
    ON employee_memory USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- RPC: match_employee_memory
-- Used by aios/foundation/employee_memory.py recall(). Returns top-k rows
-- by cosine similarity, scoped to (client_id, employee_id) and filtered by
-- kind. Mirrors match_decisions in 001_foundation.sql.
CREATE OR REPLACE FUNCTION match_employee_memory(
    p_client_id TEXT,
    p_employee_id TEXT,
    p_query_embedding VECTOR(1024),
    p_kind_filter TEXT[],
    p_match_count INT DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    employee_id TEXT,
    kind TEXT,
    content TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ,
    similarity FLOAT
)
LANGUAGE SQL STABLE
AS $$
    SELECT
        em.id,
        em.employee_id,
        em.kind,
        em.content,
        em.metadata,
        em.created_at,
        1 - (em.embedding <=> p_query_embedding) AS similarity
    FROM employee_memory em
    WHERE em.client_id = p_client_id
      AND em.employee_id = p_employee_id
      AND em.embedding IS NOT NULL
      AND (p_kind_filter IS NULL OR em.kind = ANY(p_kind_filter))
    ORDER BY em.embedding <=> p_query_embedding
    LIMIT p_match_count;
$$;

-- =========================================================================
-- employee_subscriptions — peer-to-peer learning routing rules
-- =========================================================================
--
-- One row = "employee_id subscribes to learning events from source_employee_id,
-- filtered to events whose kind is in kind_filter." Subscriptions are data
-- (operator can edit rows to retune cross-pollination per deployment).

CREATE TABLE IF NOT EXISTS employee_subscriptions (
    client_id           TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    employee_id         TEXT NOT NULL,             -- subscribing employee
    source_employee_id  TEXT NOT NULL,             -- whose events to listen to
    kind_filter         TEXT[] NOT NULL DEFAULT ARRAY['job_completion', 'learning']::TEXT[],
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (client_id, employee_id, source_employee_id)
);

-- =========================================================================
-- learning_events — peer-to-peer cross-employee learning channel
-- =========================================================================
--
-- Fire-and-forget log. When an employee completes a job (or a webhook
-- backfills an outcome), feedback_loop emits a learning_event. The COO and
-- subscribing employees consume new events on their next run.

CREATE TABLE IF NOT EXISTS learning_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    source_employee_id  TEXT NOT NULL,             -- who emitted
    kind            TEXT NOT NULL CHECK (kind IN (
        'job_completion',
        'outcome',
        'synthesis',
        'observation'
    )),
    content         TEXT NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}'::JSONB,
    decision_log_id UUID REFERENCES decision_log(id) ON DELETE SET NULL,  -- optional link to the originating decision
    embedding       VECTOR(1024),                  -- nullable until embedder runs
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_learning_events_client_source
    ON learning_events (client_id, source_employee_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_learning_events_embedding
    ON learning_events USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- =========================================================================
-- daily_dispatches — COO's per-employee task brief
-- =========================================================================
--
-- One row per (client_id, employee_id, dispatched_at) — the COO writes one
-- per active employee each morning. Employees consume on their next run by
-- selecting WHERE consumed_at IS NULL.

CREATE TABLE IF NOT EXISTS daily_dispatches (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id         TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    employee_id       TEXT NOT NULL,
    dispatched_at     DATE NOT NULL,
    payload           JSONB NOT NULL DEFAULT '{}'::JSONB,  -- DispatchPayload (see Section 7 of structural plan)
    consumed_at       TIMESTAMPTZ,                          -- set when employee reads
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (client_id, employee_id, dispatched_at)
);

CREATE INDEX IF NOT EXISTS idx_daily_dispatches_unconsumed
    ON daily_dispatches (client_id, employee_id, dispatched_at)
    WHERE consumed_at IS NULL;

-- =========================================================================
-- weekly_recaps — COO's team synthesis
-- =========================================================================
--
-- One row per (client_id, week_start). COO writes Sunday evening; all
-- employees read the row on the first run of the new week.

CREATE TABLE IF NOT EXISTS weekly_recaps (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id         TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    week_start        DATE NOT NULL,                          -- Monday of the recap week
    payload           JSONB NOT NULL DEFAULT '{}'::JSONB,     -- RecapPayload (see Section 7 of structural plan)
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (client_id, week_start)
);

CREATE INDEX IF NOT EXISTS idx_weekly_recaps_client_week
    ON weekly_recaps (client_id, week_start DESC);

-- =========================================================================
-- decision_log.decision_type CHECK constraint — extend with feedback-loop types
-- =========================================================================
--
-- Slice 24 added enrich_contact / pull_contact / etc. We need to allow new
-- decision_types emitted by feedback_loop.record_outcome and the COO's
-- daily_dispatch / weekly_recap workflows. Done as a permissive ALTER —
-- the existing constraint enumerates allowed types and rejects unknowns.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'decision_log'
          AND constraint_name = 'decision_log_decision_type_check'
    ) THEN
        ALTER TABLE decision_log DROP CONSTRAINT decision_log_decision_type_check;
    END IF;
END $$;

ALTER TABLE decision_log ADD CONSTRAINT decision_log_decision_type_check
    CHECK (decision_type IS NOT NULL);
-- Note: dropped the strict enum CHECK in favour of NOT NULL only. Foundation
-- adds new decision_types frequently (feedback_loop, daily_dispatch,
-- weekly_recap, employee_observation, etc.) and re-running ALTER on every
-- new type is friction. Behaviour at write time is unchanged — callers
-- pass the type they intend; queries filter on type as needed.
