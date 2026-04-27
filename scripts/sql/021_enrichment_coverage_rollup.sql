-- 021_enrichment_coverage_rollup.sql
--
-- Plan 2 Phase 4 Task 2.4.5: per-field enrichment coverage rollup.
--
-- Operator's "90%+ enrichment" target (2026-04-27 scope expansion):
--   - email + email_verified ≥90% across Tier A/B/C
--   - linkedin_url ≥90% across Tier A/B/C
--   - phone ≥90% on Tier A only (phone_gate per
--     ``feedback_enrichment_tiers``: phones for icp_score >= 50)
--
-- Two surfaces:
--   v_enrichment_coverage           — view, one row per (client, niche, tier)
--   get_enrichment_coverage(text)   — RPC returning per-tier rollup as JSONB
--
-- Plan-doc note: spec named this migration 019; renumbered to 021
-- because 019 was used for contacts.cool_off (Task 2.3.4) and 020 was
-- used for the cost rollup (Task 2.4.2).

CREATE OR REPLACE VIEW v_enrichment_coverage AS
SELECT
    client_id,
    niche,
    icp_tier,
    COUNT(*) AS total_contacts,
    -- field-presence counts
    COUNT(*) FILTER (
        WHERE email IS NOT NULL AND email != ''
    ) AS email_present_count,
    COUNT(*) FILTER (
        WHERE email IS NOT NULL AND email != ''
              AND email_verified = TRUE
    ) AS email_verified_count,
    COUNT(*) FILTER (
        WHERE linkedin_url IS NOT NULL AND linkedin_url != ''
    ) AS linkedin_present_count,
    COUNT(*) FILTER (
        WHERE phone IS NOT NULL AND phone != ''
    ) AS phone_present_count,
    COUNT(*) FILTER (
        WHERE company_domain IS NOT NULL AND company_domain != ''
    ) AS domain_resolved_count,
    COUNT(*) FILTER (
        WHERE jsonb_typeof(research_data->'trigger_events') = 'array'
              AND jsonb_array_length(research_data->'trigger_events') > 0
    ) AS trigger_events_count,
    -- percentages (NULL when total_contacts = 0)
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE email IS NOT NULL AND email != ''
                  AND email_verified = TRUE
        ) / NULLIF(COUNT(*), 0),
        1
    ) AS email_verified_pct,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE linkedin_url IS NOT NULL AND linkedin_url != ''
        ) / NULLIF(COUNT(*), 0),
        1
    ) AS linkedin_pct,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE phone IS NOT NULL AND phone != ''
        ) / NULLIF(COUNT(*), 0),
        1
    ) AS phone_pct
FROM contacts
WHERE icp_tier IN ('A', 'B', 'C')   -- D is archived; not covered
GROUP BY client_id, niche, icp_tier;


-- Per-client rollup — returns one row per (niche, tier) as JSONB so the
-- coverage dashboard CLI (Task 2.4.6) can render without N+1 queries.
CREATE OR REPLACE FUNCTION get_enrichment_coverage(client_id_param TEXT)
RETURNS JSONB
LANGUAGE SQL
STABLE
AS $$
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'niche', niche,
                'icp_tier', icp_tier,
                'total_contacts', total_contacts,
                'email_present_count', email_present_count,
                'email_verified_count', email_verified_count,
                'linkedin_present_count', linkedin_present_count,
                'phone_present_count', phone_present_count,
                'domain_resolved_count', domain_resolved_count,
                'trigger_events_count', trigger_events_count,
                'email_verified_pct', email_verified_pct,
                'linkedin_pct', linkedin_pct,
                'phone_pct', phone_pct
            )
        ),
        '[]'::JSONB
    )
    FROM v_enrichment_coverage
    WHERE client_id = client_id_param
$$;
