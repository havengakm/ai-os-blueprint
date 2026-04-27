-- 017_decision_log_send_event.sql
--
-- Plan 2 Phase 2 Task 2.2.4: extend decision_log.decision_type CHECK
-- with the ``send_event`` type that the Beacon webhook handler emits
-- for ESP status-changing events (sent / bounced / deferred / failed
-- / complained).
--
-- Distinct from ``send_attempt`` (Phase 2 Task 2.2.3) which is emitted
-- by SendStage when Beacon decides to send. ``send_event`` is the
-- downstream record of what actually happened to that send, as
-- reported by the ESP via webhook.
--
-- All other decision_log types from 015 are retained.

ALTER TABLE decision_log
    DROP CONSTRAINT IF EXISTS decision_log_decision_type_check;

ALTER TABLE decision_log
    ADD CONSTRAINT decision_log_decision_type_check CHECK (
        decision_type IN (
            -- Original 001_foundation.sql values
            'copy_variant', 'icp_threshold', 'template_choice',
            'signal_weight', 'send_timing', 'channel_selection',
            'meeting_booking', 'reply_handling', 'manual_override',
            'system_config', 'enrichment_choice', 'framework_selection',
            -- Plan 1 additions (2026-04-21)
            'research_contact', 'render_draft', 'component_selection',
            'screen_contact', 'identity_lookup', 'source_selection',
            'enrich_contact',
            -- Plan 2 Beacon additions (2026-04-27)
            'send_attempt', 'reply_received', 'reply_classification',
            -- Plan 2 Task 2.2.4 webhook ingest
            'send_event'
        )
    );
