-- 023_outreach_drafts_predicted_grade.sql
--
-- Plan 2 Phase 5 Task 2.5.4: cold email copy grader skill output column.
--
-- The grade-cold-email-copy skill (operator-interactive, runs via
-- Claude Code Max-plan credits) produces a JSON verdict per draft:
--
--   {
--     "predicted_reply_rate": 0.07,
--     "tier": "B",
--     "critique": ["...", "...", "..."],
--     "graded_at": "2026-04-27T12:00:00Z"
--   }
--
-- When the operator runs the skill on a persisted draft, the verdict
-- lands in this column. When run on a variant before approval, the
-- verdict goes to data/captures/copy_grades/<key>-<ts>.yaml instead
-- (no DB write).
--
-- Phase 5 Task 2.5.5 (grader calibration) reads this column to
-- correlate predicted_reply_rate with actual outreach_reply outcomes.

ALTER TABLE outreach_drafts
    ADD COLUMN IF NOT EXISTS predicted_grade JSONB;

CREATE INDEX IF NOT EXISTS idx_drafts_with_grade
    ON outreach_drafts ((predicted_grade IS NOT NULL))
    WHERE predicted_grade IS NOT NULL;
