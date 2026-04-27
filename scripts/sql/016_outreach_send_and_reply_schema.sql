-- 016_outreach_send_and_reply_schema.sql
--
-- Plan 2 Phase 2 Task 2.2.1: Beacon send + reply tracking tables.
-- ESP locked to Instantly per docs/superpowers/decisions/2026-04-27-esp-comparison.md.
--
-- Tables created:
--   send_account          — per-client mailbox roster (provider, daily cap, warming state)
--   send_caps_daily       — atomic per-(account, day) sent_count counter
--   outreach_send_log     — one row per send attempt to the ESP
--   outreach_reply        — one row per inbound reply received via webhook
--
-- Plus contacts.touch_state column for Plan 3 cross-channel state.
--
-- Note on superseded placeholders:
--   Plan 1's 002_scout.sql created placeholder tables marked "populated in
--   Plan 2": outreach_sent, activity_log, replies, response_drafts. Those
--   were ESP-specific (hard-coded smartlead_message_id) and shape-incomplete.
--   The Plan-2-plan-doc spec replaces them with the provider-agnostic richer
--   versions in this migration. The old placeholders are LEFT IN PLACE
--   (likely empty in dev) and will be dropped in a future cleanup migration
--   once Phase 2-3 are live and nothing references them.

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()


-- ─────────────────────────────────────────────────────────────────────────
-- send_account
-- Per-client roster of email mailboxes connected to the ESP. Beacon picks
-- accounts from this table when scheduling sends; respects daily_cap +
-- is_active flag.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS send_account (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id               TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    account_email           TEXT NOT NULL,
    provider                TEXT NOT NULL CHECK (provider IN (
        'instantly', 'smartlead', 'plusvibe'
    )),
    esp_account_id          TEXT,                       -- ESP's internal ID for webhook correlation
    daily_cap               INTEGER NOT NULL DEFAULT 25,
    current_warming_stage   TEXT,                       -- 'warming' | 'warm' | 'paused' | NULL
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (client_id, account_email)
);

CREATE INDEX IF NOT EXISTS idx_send_account_active
    ON send_account (client_id, is_active);


-- ─────────────────────────────────────────────────────────────────────────
-- send_caps_daily
-- Per-(account, day) running counter. PRIMARY KEY enables atomic upsert
-- via: INSERT ... ON CONFLICT (account_id, date) DO UPDATE
--      SET sent_count = send_caps_daily.sent_count + 1.
-- This is how Beacon enforces the daily cap without race conditions when
-- multiple sends fire in parallel.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS send_caps_daily (
    account_id              UUID NOT NULL REFERENCES send_account(id) ON DELETE CASCADE,
    date                    DATE NOT NULL,
    sent_count              INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (account_id, date)
);


-- ─────────────────────────────────────────────────────────────────────────
-- outreach_send_log
-- One row per send attempt. Status transitions: accepted (queued at ESP) →
-- sent (delivery confirmed) OR bounced / deferred / failed / complained
-- (ESP webhook events). Beacon updates status when webhooks arrive (Phase 3).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outreach_send_log (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id               TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    contact_id              UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    draft_id                UUID REFERENCES outreach_drafts(id),
    account_id              UUID REFERENCES send_account(id) ON DELETE SET NULL,
    channel                 TEXT NOT NULL DEFAULT 'email' CHECK (channel IN (
        'email', 'linkedin', 'sms', 'whatsapp', 'voicemail', 'letter'
    )),
    esp_message_id          TEXT,                       -- ESP message identifier for webhook correlation
    sent_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status                  TEXT NOT NULL DEFAULT 'accepted' CHECK (status IN (
        'accepted', 'sent', 'bounced', 'deferred', 'failed', 'complained'
    )),
    error                   TEXT,                       -- ESP error message on bounced/deferred/failed
    cost_cents              INTEGER NOT NULL DEFAULT 0, -- per-send cost rollup (Phase 4 cost ledger)
    raw_data                JSONB NOT NULL DEFAULT '{}'::JSONB,  -- ESP webhook payload archive
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_send_log_client_contact
    ON outreach_send_log (client_id, contact_id);
CREATE INDEX IF NOT EXISTS idx_send_log_recent
    ON outreach_send_log (client_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_send_log_account
    ON outreach_send_log (account_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_send_log_esp_msg
    ON outreach_send_log (esp_message_id)
    WHERE esp_message_id IS NOT NULL;


-- ─────────────────────────────────────────────────────────────────────────
-- outreach_reply
-- One row per inbound reply received via webhook. classification is NULL
-- until the Phase 3 classifier runs, then populated with one of the values
-- in the CHECK constraint.
--
-- classification values match Plan 2 Phase 3 Task 2.3.1 (Haiku classifier).
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outreach_reply (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id                   TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    contact_id                  UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    send_log_id                 UUID REFERENCES outreach_send_log(id) ON DELETE SET NULL,
    received_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    from_email                  TEXT NOT NULL,
    subject                     TEXT,
    body                        TEXT NOT NULL,
    replied_to_message_id       TEXT,                   -- ESP message ID being replied to
    classification              TEXT CHECK (classification IS NULL OR classification IN (
        'positive_interest', 'meeting_request',
        'objection_pricing', 'objection_timing',
        'objection_authority', 'objection_other',
        'negative', 'unsubscribe',
        'out_of_office', 'bounce', 'wrong_person', 'spam_marked',
        'cannot_classify'
    )),
    classification_confidence   NUMERIC,                -- 0.0-1.0; NULL until classifier runs
    classified_at               TIMESTAMPTZ,
    raw_data                    JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reply_client_recent
    ON outreach_reply (client_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_reply_send_log
    ON outreach_reply (send_log_id);
CREATE INDEX IF NOT EXISTS idx_reply_contact
    ON outreach_reply (contact_id);
CREATE INDEX IF NOT EXISTS idx_reply_pending_classification
    ON outreach_reply (client_id, received_at)
    WHERE classification IS NULL;


-- ─────────────────────────────────────────────────────────────────────────
-- contacts.touch_state
-- Cross-channel state ("last touched on email, due for LinkedIn next").
-- Added now so Phase 2 doesn't need a follow-up migration. Plan 3
-- surround-sound work uses this column to coordinate touches across
-- channels.
-- ─────────────────────────────────────────────────────────────────────────
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS touch_state TEXT;
