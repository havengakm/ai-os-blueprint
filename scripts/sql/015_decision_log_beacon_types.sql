-- 015_decision_log_beacon_types.sql
--
-- Plan 2 Task 2.0.2: extend decision_log.decision_type CHECK constraint
-- with the Beacon-era types that Phase 2 (send) and Phase 3 (reply)
-- emit sites will use.
--
-- Bundling these now (Phase 0 hardening) so schema work doesn't gate
-- the per-phase implementation PRs later.
--
-- Existing types (kept):
--   Plan 1 task vocabulary (added in 005_foundation_completion.sql):
--     copy_variant, icp_threshold, template_choice, signal_weight,
--     send_timing, channel_selection, meeting_booking, reply_handling,
--     manual_override, system_config, enrichment_choice,
--     framework_selection, research_contact, render_draft,
--     component_selection, screen_contact, identity_lookup,
--     source_selection, enrich_contact
--
-- New types (Plan 2 Beacon era):
--   send_attempt           — emitted per send by send_stage (Phase 2)
--   reply_received         — emitted by ESP webhook ingest (Phase 3)
--   reply_classification   — emitted by Haiku classifier (Phase 3)
--
-- Note: follow-ups-plan1.md items 14 + 22 originally called out
-- `source_selection` and `identity_lookup` as missing from the
-- constraint. Both were added in 005_foundation_completion.sql before
-- Plan 1 shipped. The follow-up doc was outdated by the time Plan 2
-- kicked off; only the 3 Beacon types remain to add here.

ALTER TABLE decision_log
    DROP CONSTRAINT IF EXISTS decision_log_decision_type_check;

ALTER TABLE decision_log
    ADD CONSTRAINT decision_log_decision_type_check CHECK (
        decision_type IN (
            -- Original 001_foundation.sql values (retained for back-compat)
            'copy_variant', 'icp_threshold', 'template_choice',
            'signal_weight', 'send_timing', 'channel_selection',
            'meeting_booking', 'reply_handling', 'manual_override',
            'system_config', 'enrichment_choice', 'framework_selection',
            -- Plan 1 additions (2026-04-21)
            'research_contact', 'render_draft', 'component_selection',
            'screen_contact', 'identity_lookup', 'source_selection',
            'enrich_contact',
            -- Plan 2 Beacon additions (2026-04-27)
            'send_attempt', 'reply_received', 'reply_classification'
        )
    );
