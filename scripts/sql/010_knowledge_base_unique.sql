-- 010_knowledge_base_unique.sql
-- Adds UNIQUE (client_id, source, title) to knowledge_base.
-- Required by scripts/load_knowledge.py which upserts with
-- on_conflict='client_id,source,title'. Migration 001 created the table
-- without this constraint; this fixes that gap non-destructively.
-- Idempotent: ADD CONSTRAINT IF NOT EXISTS via DO-block fallback because
-- Postgres does not support IF NOT EXISTS on ALTER TABLE ADD CONSTRAINT.

BEGIN;

DO $migration_010$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'knowledge_base_client_source_title_key'
          AND conrelid = 'knowledge_base'::regclass
    ) THEN
        ALTER TABLE knowledge_base
            ADD CONSTRAINT knowledge_base_client_source_title_key
            UNIQUE (client_id, source, title);
    END IF;
END
$migration_010$;

COMMIT;
