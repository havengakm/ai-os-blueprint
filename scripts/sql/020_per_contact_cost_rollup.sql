-- 020_per_contact_cost_rollup.sql
--
-- Plan 2 Phase 4 Task 2.4.2: per-contact cost rollup view + RPC.
--
-- Replaces the v1 Python full-table-scan in
-- ``SupabaseSendBackend.get_contact_total_cost_cents`` with an O(log n)
-- index lookup via a SQL view.
--
-- The view aggregates ``decision_log.context.cost_cents`` per
-- ``context.contact_id``, broken down by ``decision_type`` so
-- dashboards can attribute spend per pipeline stage.
--
-- Two surfaces:
--   v_contact_cost_rollup     — view, one row per (contact_id, decision_type)
--   get_contact_cost(uuid)    — RPC returning total cents for one contact
--
-- Plan-doc note: spec named this migration 018; renumbered to 020 because
-- 018 was used for the escalations table (Task 2.3.3) and 019 for
-- contacts.cool_off (Task 2.3.4). The semantics are unchanged.

CREATE OR REPLACE VIEW v_contact_cost_rollup AS
SELECT
    (context->>'contact_id')::TEXT      AS contact_id,
    decision_type,
    COUNT(*)                            AS event_count,
    COALESCE(
        SUM((context->>'cost_cents')::INTEGER),
        0
    )                                   AS total_cost_cents
FROM decision_log
WHERE
    context ? 'contact_id'
    AND context ? 'cost_cents'
GROUP BY
    (context->>'contact_id'),
    decision_type;


-- Per-contact total. Returns 0 when the contact has no logged cost rows.
CREATE OR REPLACE FUNCTION get_contact_cost(contact_id_param TEXT)
RETURNS INTEGER
LANGUAGE SQL
STABLE
AS $$
    SELECT COALESCE(SUM(total_cost_cents), 0)::INTEGER
    FROM v_contact_cost_rollup
    WHERE contact_id = contact_id_param
$$;


-- A future migration may add similar surfaces for per-client / per-tier
-- rollups; those are dashboard-side concerns and live with Task 2.4.4.
