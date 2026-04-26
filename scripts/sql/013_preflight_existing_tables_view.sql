-- 013_preflight_existing_tables_view.sql
--
-- Plan 1.5 Task 1.5.1: cross-check preflight schema checks against
-- information_schema.tables explicitly, not just a raw PostgREST SELECT.
--
-- Background: PostgREST returns 200 (with empty data) for tables that
-- match some permission cache state even when the table is absent from
-- the schema. The plan1_acceptance_preflight script can therefore pass
-- on a partially-migrated database. This view exposes the authoritative
-- list of public-schema tables so preflight can cross-check what the
-- REST layer reports.
--
-- Used by: scripts/plan1_acceptance_preflight.py (check_schema function).

CREATE OR REPLACE VIEW public.preflight_existing_tables AS
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public';

-- Service role + the API roles all need read access. The view exposes
-- nothing sensitive: it lists table NAMES only, not contents.
GRANT SELECT ON public.preflight_existing_tables TO service_role;
GRANT SELECT ON public.preflight_existing_tables TO authenticated;
GRANT SELECT ON public.preflight_existing_tables TO anon;

COMMENT ON VIEW public.preflight_existing_tables IS
  'Plan 1.5 Task 1.5.1: read-only list of public-schema table names from '
  'information_schema. Used by scripts/plan1_acceptance_preflight.py to '
  'cross-check PostgREST schema reachability against the authoritative '
  'database catalog. Migration 013.';
