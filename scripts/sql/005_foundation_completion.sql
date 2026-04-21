-- 005_foundation_completion.sql
-- Completes the foundation schema per Task 12.5 of the 2026-04-20 foundation-scout
-- migration plan. Adds business_context + client_facts tables (with Obsidian-style
-- graph-link columns from Max webinar 2026-04-21 pt 2), match_* RPCs, and a
-- match_context_graph RPC for breadth-first graph traversal. Extends the
-- decision_log.decision_type CHECK to reflect the Plan 1 task vocabulary. Adds
-- client_config.trigify_search_ids column required by the enrich stage.
--
-- Idempotent: uses CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS /
-- CREATE OR REPLACE for every mutation so re-runs are safe.

BEGIN;

-- ── business_context ──────────────────────────────────────────────────────────
-- Client-specific structured business context: offers, ICP, positioning, brand
-- guidelines, team, integrations. Loaded from markdown in context/{client}/*.md
-- via scripts/load_context.py (Task 16). Operator-authored Obsidian-style
-- [[entity-name]] backlinks resolve into related_context_ids / related_fact_ids
-- at load time.

CREATE TABLE IF NOT EXISTS business_context (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           TEXT NOT NULL,
    title               TEXT NOT NULL,
    body                TEXT NOT NULL,
    section_metadata    JSONB NOT NULL DEFAULT '{}',
    embedding           VECTOR(1024),
    source_path         TEXT,
    related_context_ids UUID[] NOT NULL DEFAULT '{}',
    related_fact_ids    UUID[] NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (client_id, title)
);

CREATE INDEX IF NOT EXISTS idx_business_context_client
    ON business_context (client_id);
CREATE INDEX IF NOT EXISTS idx_business_context_related_ctx
    ON business_context USING GIN (related_context_ids);
CREATE INDEX IF NOT EXISTS idx_business_context_related_facts
    ON business_context USING GIN (related_fact_ids);
-- ivfflat on embedding: lists=100 matches the tuning used for the other 1024-dim
-- embedding indices in this schema (good for <1M rows).
CREATE INDEX IF NOT EXISTS idx_business_context_embedding
    ON business_context USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

ALTER TABLE business_context ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE TRIGGER business_context_updated_at
    BEFORE UPDATE ON business_context
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ── client_facts ──────────────────────────────────────────────────────────────
-- Atomic key/value facts about the client: team members, named offers, integrations,
-- pricing tiers, expert framework alignments. Smaller granularity than
-- business_context (which stores passages). Also supports graph-links.

CREATE TABLE IF NOT EXISTS client_facts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           TEXT NOT NULL,
    key                 TEXT NOT NULL,
    value               JSONB NOT NULL,
    embedding           VECTOR(1024),
    source_urls         TEXT[] NOT NULL DEFAULT '{}',
    related_context_ids UUID[] NOT NULL DEFAULT '{}',
    related_fact_ids    UUID[] NOT NULL DEFAULT '{}',
    confidence          FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (client_id, key)
);

CREATE INDEX IF NOT EXISTS idx_client_facts_client
    ON client_facts (client_id);
CREATE INDEX IF NOT EXISTS idx_client_facts_related_ctx
    ON client_facts USING GIN (related_context_ids);
CREATE INDEX IF NOT EXISTS idx_client_facts_related_facts
    ON client_facts USING GIN (related_fact_ids);
CREATE INDEX IF NOT EXISTS idx_client_facts_embedding
    ON client_facts USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

ALTER TABLE client_facts ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE TRIGGER client_facts_updated_at
    BEFORE UPDATE ON client_facts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ── match_business_context ────────────────────────────────────────────────────
-- Embedding-similarity search over business_context for a given client.

CREATE OR REPLACE FUNCTION match_business_context(
    query_embedding VECTOR(1024),
    client_id_filter TEXT,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    client_id TEXT,
    title TEXT,
    body TEXT,
    section_metadata JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT bc.id, bc.client_id, bc.title, bc.body, bc.section_metadata,
           1 - (bc.embedding <=> query_embedding) AS similarity
    FROM business_context bc
    WHERE bc.client_id = client_id_filter
      AND bc.embedding IS NOT NULL
    ORDER BY bc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;


-- ── match_client_facts ────────────────────────────────────────────────────────
-- Embedding-similarity search over client_facts for a given client.

CREATE OR REPLACE FUNCTION match_client_facts(
    query_embedding VECTOR(1024),
    client_id_filter TEXT,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    client_id TEXT,
    key TEXT,
    value JSONB,
    source_urls TEXT[],
    confidence FLOAT,
    similarity FLOAT
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT cf.id, cf.client_id, cf.key, cf.value, cf.source_urls, cf.confidence,
           1 - (cf.embedding <=> query_embedding) AS similarity
    FROM client_facts cf
    WHERE cf.client_id = client_id_filter
      AND cf.embedding IS NOT NULL
    ORDER BY cf.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;


-- ── match_context_graph ───────────────────────────────────────────────────────
-- Breadth-first graph walk from a starting node up to `max_depth` hops, capped
-- at `max_nodes` reachable rows. Traverses both business_context and
-- client_facts via related_context_ids / related_fact_ids arrays. Returns a
-- flat set of (id, source_table, depth) rows; caller joins back to the actual
-- row data for full payloads.
--
-- Implemented as a recursive CTE: for each frontier node, look up its outgoing
-- edges from whichever table it lives in, emit the neighbours at depth+1, and
-- let the CTE recursion stop at `max_depth`. A final DISTINCT pass collapses
-- duplicates that arise when a node is reached by multiple paths, and LIMIT
-- caps the result at `max_nodes`. Cycles are safe because the recursion
-- terminates on depth and DISTINCT de-duplicates visited nodes.
--
-- Defaults: max_depth=3, max_nodes=50 (plan traversal caps).

CREATE OR REPLACE FUNCTION match_context_graph(
    client_id_filter TEXT,
    start_id UUID,
    start_table TEXT,   -- 'business_context' | 'client_facts'
    max_depth INT DEFAULT 3,
    max_nodes INT DEFAULT 50
)
RETURNS TABLE (
    id UUID,
    source_table TEXT,
    depth INT
)
LANGUAGE sql AS $$
    WITH RECURSIVE graph_walk(id, source_table, depth) AS (
        -- Seed: the start node itself at depth 0. Only emit if start_table is
        -- valid; otherwise the CTE yields no rows.
        SELECT start_id, start_table, 0
        WHERE start_table IN ('business_context', 'client_facts')

        UNION

        -- Recurse: for each node on the frontier, expand its outgoing edges
        -- from whichever table it lives in. Both edge arrays
        -- (related_context_ids / related_fact_ids) are unnested and emitted
        -- with the correct target-table label.
        SELECT neighbour_id, neighbour_table, gw.depth + 1
        FROM graph_walk gw
        CROSS JOIN LATERAL (
            -- Edges out of a business_context node
            SELECT unnest(bc.related_context_ids) AS neighbour_id,
                   'business_context'::TEXT AS neighbour_table
            FROM business_context bc
            WHERE gw.source_table = 'business_context'
              AND bc.id = gw.id
              AND bc.client_id = client_id_filter
            UNION ALL
            SELECT unnest(bc.related_fact_ids) AS neighbour_id,
                   'client_facts'::TEXT AS neighbour_table
            FROM business_context bc
            WHERE gw.source_table = 'business_context'
              AND bc.id = gw.id
              AND bc.client_id = client_id_filter
            UNION ALL
            -- Edges out of a client_facts node
            SELECT unnest(cf.related_context_ids) AS neighbour_id,
                   'business_context'::TEXT AS neighbour_table
            FROM client_facts cf
            WHERE gw.source_table = 'client_facts'
              AND cf.id = gw.id
              AND cf.client_id = client_id_filter
            UNION ALL
            SELECT unnest(cf.related_fact_ids) AS neighbour_id,
                   'client_facts'::TEXT AS neighbour_table
            FROM client_facts cf
            WHERE gw.source_table = 'client_facts'
              AND cf.id = gw.id
              AND cf.client_id = client_id_filter
        ) edges
        WHERE gw.depth < max_depth
          AND neighbour_id IS NOT NULL
    )
    SELECT DISTINCT ON (graph_walk.id, graph_walk.source_table)
           graph_walk.id, graph_walk.source_table, graph_walk.depth
    FROM graph_walk
    ORDER BY graph_walk.id, graph_walk.source_table, graph_walk.depth ASC
    LIMIT max_nodes;
$$;


-- ── Extend decision_log.decision_type CHECK ───────────────────────────────────
-- Adds Plan 1 task-specific decision types. Keeps existing values for backward
-- compatibility with prior decision_log entries. Once Plan 1 ships, we can
-- optionally deprecate 'enrichment_choice' after a burn-in period.

ALTER TABLE decision_log DROP CONSTRAINT IF EXISTS decision_log_decision_type_check;
ALTER TABLE decision_log ADD CONSTRAINT decision_log_decision_type_check CHECK (
    decision_type IN (
        -- Original 001_foundation.sql values (retained for back-compat)
        'copy_variant', 'icp_threshold', 'template_choice',
        'signal_weight', 'send_timing', 'channel_selection',
        'meeting_booking', 'reply_handling', 'manual_override',
        'system_config', 'enrichment_choice', 'framework_selection',
        -- Plan 1 additions (2026-04-21)
        'research_contact', 'render_draft', 'component_selection',
        'screen_contact', 'identity_lookup', 'source_selection', 'enrich_contact'
    )
);


-- ── client_config.trigify_search_ids ──────────────────────────────────────────
-- Pre-configured Trigify search IDs for this client. Populated at onboarding
-- via the configure-trigify-monitors skill. Empty array = Trigify adapter will
-- skip with reason='no_monitors_configured'. Required by Task 12d's
-- `get_client_trigify_search_ids` storage method.

ALTER TABLE client_config
    ADD COLUMN IF NOT EXISTS trigify_search_ids TEXT[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN client_config.trigify_search_ids IS
    'Pre-configured Trigify search IDs for this client. Populated at onboarding via configure-trigify-monitors skill. Empty array = Trigify adapter will skip with no_monitors_configured reason.';

COMMIT;
