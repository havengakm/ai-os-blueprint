-- 004_contacts_extensions.sql
-- Operator-facing fields (timezone, prospecting_method, buying_signals, key_pain_point)
-- + compliance audit fields (phone_source, phone_consent_basis, phone_found_at,
-- sms_opted_out) + identity_source (which tool resolved the decision-maker).
-- Depends on 002_scout.sql (contacts table).
-- Amendment 2 of the 2026-04-20 lead-sourcing architecture decision.

BEGIN;

ALTER TABLE contacts
    ADD COLUMN IF NOT EXISTS timezone TEXT,
    ADD COLUMN IF NOT EXISTS prospecting_method TEXT,
    ADD COLUMN IF NOT EXISTS buying_signals JSONB DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS key_pain_point TEXT,
    ADD COLUMN IF NOT EXISTS phone_source TEXT,
    ADD COLUMN IF NOT EXISTS phone_consent_basis TEXT,
    ADD COLUMN IF NOT EXISTS phone_found_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS sms_opted_out BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS identity_source TEXT;

COMMENT ON COLUMN contacts.prospecting_method IS
    'How the prospect currently acquires their own customers (e.g., "Referral-based webinars", "Digital marketing content") — research output that signals whether outbound help is needed';
COMMENT ON COLUMN contacts.buying_signals IS
    'Array of observed intent signals: [{signal, source_url, observed_at}]';
COMMENT ON COLUMN contacts.key_pain_point IS
    'Single most salient pain point extracted by research — drives outreach hook selection';
COMMENT ON COLUMN contacts.phone_consent_basis IS
    'Legal basis for SMS-eligible phone number: legitimate_interest | explicit_consent | public_source';
COMMENT ON COLUMN contacts.identity_source IS
    'Tool that resolved decision-maker identity: apollo | hunter | claude_scraper | manual';

COMMIT;
