-- 006_component_registry.sql
-- Micro-granularity component registry per Task 13 of the Plan 1 roadmap.
-- Complements the macro-framework `templates` table from 002_scout.sql: templates
-- stay as the sequence-level skeleton; `component_variants` carries the individual
-- swappable pieces (subject lines, icebreakers, pain hooks, offer frames, CTAs,
-- signatures) that the Task 15 composer assembles at send-time.
--
-- The outreach_drafts.component_selections JSONB column records the exact variant
-- tuple chosen for each rendered draft, giving Plan 7's cohort evaluator
-- component-level attribution when outcome events arrive.
--
-- Idempotent: uses CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS /
-- CREATE OR REPLACE for every mutation so re-runs are safe.

BEGIN;

-- ── component_variants ────────────────────────────────────────────────────────
-- One row per swappable component variant. The UNIQUE key
-- (client_id, niche, offer_label, component_type, variant_key) gives the YAML
-- loader a stable identity: re-running the sync keeps the same row UUID, which
-- is required so attribution events emitted months apart still resolve to the
-- same variant. `variant_key` is the YAML-author-controlled stable handle
-- (snake_case, e.g. "agency_growth_hook_v1"); UUIDs stay an implementation
-- detail.
--
-- `win_rate` + `sample_size` are populated by Plan 2's cohort evaluator;
-- `ab_epsilon` is the per-variant exploration rate for the Plan 2 bandit.
-- `status` gates which variants the composer is allowed to pick from
-- ('approved' + 'draft' eligible during warm-up; 'paused'/'killed' excluded).

CREATE TABLE IF NOT EXISTS component_variants (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    component_type      TEXT NOT NULL CHECK (component_type IN (
        'subject_line', 'icebreaker', 'pain_hook', 'offer_frame', 'cta', 'signature',
        'who_i_am', 'credibility'
    )),
    variant_key         TEXT NOT NULL,
    variant_content     TEXT NOT NULL,
    niche               TEXT NOT NULL,
    offer_label         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
        'draft', 'approved', 'paused', 'killed'
    )),
    metadata            JSONB NOT NULL DEFAULT '{}',
    win_rate            FLOAT NULL CHECK (win_rate IS NULL OR (win_rate >= 0 AND win_rate <= 1)),
    sample_size         INT NOT NULL DEFAULT 0,
    ab_epsilon          FLOAT NOT NULL DEFAULT 0.1 CHECK (ab_epsilon >= 0 AND ab_epsilon <= 1),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (client_id, niche, offer_label, component_type, variant_key)
);

-- Selection index: composer reads by (client, niche, offer, type, status) at
-- compose-time — this index covers that predicate directly.
CREATE INDEX IF NOT EXISTS idx_component_variants_selection
    ON component_variants (client_id, niche, offer_label, component_type, status);

-- Winners index: Plan 2's bandit periodically asks "top N approved variants by
-- win_rate for this client" — a partial index on (client_id, win_rate DESC)
-- filtered to `status = 'approved'` and a non-null win_rate keeps the working
-- set small.
CREATE INDEX IF NOT EXISTS idx_component_variants_winners
    ON component_variants (client_id, win_rate DESC)
    WHERE status = 'approved' AND win_rate IS NOT NULL;

ALTER TABLE component_variants ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE TRIGGER component_variants_updated_at
    BEFORE UPDATE ON component_variants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ── outreach_drafts.component_selections ─────────────────────────────────────
-- Records the exact variant tuple chosen at compose-time. Mirrors the existing
-- `placeholder_fills` pattern (also JSONB DEFAULT '{}') added by 002_scout.sql.
-- Shape:
--   {
--     "subject_line": "<uuid>",
--     "icebreaker":   "<uuid>",
--     "pain_hook":    "<uuid>",
--     "offer_frame":  "<uuid>",
--     "cta":          "<uuid>",
--     "signature":    "<uuid>"
--   }
-- A sparse map is fine — not every draft uses every component type.

ALTER TABLE outreach_drafts
    ADD COLUMN IF NOT EXISTS component_selections JSONB NOT NULL DEFAULT '{}';

COMMENT ON COLUMN outreach_drafts.component_selections IS
    'Records the exact component variant tuple chosen at compose-time: {"subject_line": "<uuid>", "icebreaker": "<uuid>", "pain_hook": "<uuid>", "offer_frame": "<uuid>", "cta": "<uuid>", "signature": "<uuid>"}. Used by Plan 7 cohort evaluator for component-level attribution.';

COMMIT;
