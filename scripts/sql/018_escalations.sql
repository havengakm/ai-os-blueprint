-- 018_escalations.sql
--
-- Plan 2 Phase 3 Task 2.3.3: human-attention escalation queue.
--
-- Replies that need operator triage (low-confidence classifications,
-- cannot_classify, auto-respond skips, spam-marked, OOO replies, manual
-- flags) land here. Operator triages via the inbox API
-- (api/routers/inbox.py) — resolves or dismisses each row.
--
-- escalation_type CHECK values must match
-- ``systems.beacon.reply.escalation.ESCALATION_TYPES``.
-- Tested in test_canonical_escalation_types_match_schema.

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS escalations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    contact_id          UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    reply_id            UUID REFERENCES outreach_reply(id) ON DELETE SET NULL,
    escalation_type     TEXT NOT NULL CHECK (escalation_type IN (
        'low_confidence_reply',
        'cannot_classify_reply',
        'auto_respond_failed',
        'spam_marked_reply',
        'out_of_office_reply',
        'manual_flag'
    )),
    summary             TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'open' CHECK (status IN (
        'open', 'resolved', 'dismissed'
    )),
    raw_data            JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ,
    resolved_by         TEXT
);

-- Operator dashboard query: open escalations for a client, newest first.
CREATE INDEX IF NOT EXISTS idx_escalations_open_recent
    ON escalations (client_id, created_at DESC)
    WHERE status = 'open';

-- Reverse-lookup for "what got escalated for this contact?"
CREATE INDEX IF NOT EXISTS idx_escalations_contact
    ON escalations (contact_id, created_at DESC);

-- Reverse-lookup for "what got escalated for this reply?"
CREATE INDEX IF NOT EXISTS idx_escalations_reply
    ON escalations (reply_id)
    WHERE reply_id IS NOT NULL;
