-- 002_scout.sql
-- Scout system tables. Depends on 001_foundation.sql (clients, decision_log,
-- autonomy_rules, knowledge_base, business_context, context_registry).
-- Every table carries client_id. RLS enforces isolation.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────
-- ICP definitions (per niche, per client)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS icp_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    niche TEXT NOT NULL,
    industries TEXT[] DEFAULT '{}',
    titles TEXT[] DEFAULT '{}',
    seniorities TEXT[] DEFAULT '{}',
    employee_min INT,
    employee_max INT,
    revenue_min_usd BIGINT,
    revenue_max_usd BIGINT,
    geographies TEXT[] DEFAULT '{}',
    blacklist_companies TEXT[] DEFAULT '{}',
    blacklist_domains TEXT[] DEFAULT '{}',
    weights JSONB DEFAULT '{}',  -- per-signal scoring weights
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (client_id, niche)
);
CREATE INDEX IF NOT EXISTS idx_icp_client ON icp_definitions (client_id);

-- ─────────────────────────────────────────────────────────────────────────
-- Client Scout config (sending windows, daily caps, active niches)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS client_config (
    client_id TEXT PRIMARY KEY REFERENCES clients(id) ON DELETE CASCADE,
    active_niches TEXT[] DEFAULT '{}',
    daily_send_cap INT DEFAULT 150,
    send_window_start_hour INT DEFAULT 9,
    send_window_end_hour INT DEFAULT 17,
    send_window_timezone TEXT DEFAULT 'UTC',
    business_days INT[] DEFAULT '{1,2,3,4,5}',  -- Mon-Fri
    enrichment_budget_per_contact_cents INT DEFAULT 5,
    ai_budget_per_contact_cents INT DEFAULT 30,
    config JSONB DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────
-- Templates (approved copy per niche × offer)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    template_key TEXT NOT NULL,      -- e.g., "agencyos_offer_a"
    version INT NOT NULL DEFAULT 1,
    niche TEXT NOT NULL,
    offer_label TEXT NOT NULL,        -- "A — pipeline pain" etc.
    status TEXT NOT NULL DEFAULT 'draft',  -- draft | approved | paused | killed | superseded
    body TEXT NOT NULL,               -- full template with {{placeholders}}
    placeholders JSONB DEFAULT '[]',  -- list of placeholder specs
    metadata JSONB DEFAULT '{}',
    offer_score JSONB DEFAULT '{}',   -- 27-constraint scorecard
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (client_id, template_key, version)
);
CREATE INDEX IF NOT EXISTS idx_templates_status ON templates (client_id, status);

-- ─────────────────────────────────────────────────────────────────────────
-- Campaigns (one per test cell — niche × offer tuple)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    niche TEXT NOT NULL,
    template_id UUID REFERENCES templates(id),
    status TEXT NOT NULL DEFAULT 'active',  -- active | paused | killed | completed
    daily_volume_cap INT DEFAULT 50,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    UNIQUE (client_id, niche, template_id)
);
CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns (client_id, status);

-- ─────────────────────────────────────────────────────────────────────────
-- Contacts (leads pulled from sources)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    campaign_id UUID REFERENCES campaigns(id),
    niche TEXT,
    source TEXT NOT NULL,  -- apollo | clutch | manual | webhook | csv
    source_id TEXT,         -- e.g., apollo_id for dedup
    name TEXT,
    first_name TEXT,
    last_name TEXT,
    title TEXT,
    company TEXT,
    company_domain TEXT,
    email TEXT,
    email_verified BOOLEAN DEFAULT FALSE,
    email_catch_all BOOLEAN DEFAULT FALSE,
    linkedin_url TEXT,
    phone TEXT,
    industry TEXT,
    employees INT,
    revenue_usd BIGINT,
    geography TEXT,
    city TEXT,
    state TEXT,
    icp_score INT,                -- 0-100 from scoring stage
    icp_tier TEXT,                -- A | B | C | D
    status TEXT NOT NULL DEFAULT 'new',  -- new | screened | enriched | ready | drafted | sent | replied | meeting_booked | dead
    screened_at TIMESTAMPTZ,
    enriched_at TIMESTAMPTZ,
    last_contacted_at TIMESTAMPTZ,
    raw_data JSONB DEFAULT '{}',  -- original source payload
    research_data JSONB DEFAULT '{}',  -- placeholder research results
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (client_id, source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_contacts_client_status ON contacts (client_id, status);
CREATE INDEX IF NOT EXISTS idx_contacts_campaign ON contacts (campaign_id);
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts (client_id, email);
CREATE INDEX IF NOT EXISTS idx_contacts_domain ON contacts (client_id, company_domain);

-- ─────────────────────────────────────────────────────────────────────────
-- Outreach drafts (rendered, pre-send)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outreach_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    campaign_id UUID REFERENCES campaigns(id),
    template_id UUID REFERENCES templates(id),
    subject TEXT,
    body TEXT NOT NULL,
    placeholder_fills JSONB DEFAULT '{}',  -- each fill + source URL
    research_sources JSONB DEFAULT '[]',   -- list of source URLs for factuality
    qa_verdict JSONB,                      -- populated by QA agent in Plan 2
    qa_status TEXT DEFAULT 'pending',      -- pending | passed | failed | retrying | escalated
    status TEXT NOT NULL DEFAULT 'rendered',  -- rendered | approved | sent | rejected | failed
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON outreach_drafts (client_id, status);
CREATE INDEX IF NOT EXISTS idx_drafts_contact ON outreach_drafts (contact_id);

-- ─────────────────────────────────────────────────────────────────────────
-- Outreach sent (populated in Plan 2)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outreach_sent (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    draft_id UUID NOT NULL REFERENCES outreach_drafts(id),
    contact_id UUID NOT NULL REFERENCES contacts(id),
    campaign_id UUID REFERENCES campaigns(id),
    smartlead_message_id TEXT,
    inbox_used TEXT,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sequence_position INT DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sent_contact ON outreach_sent (contact_id);
CREATE INDEX IF NOT EXISTS idx_sent_campaign ON outreach_sent (campaign_id);

-- ─────────────────────────────────────────────────────────────────────────
-- Activity log (raw events from webhooks — Plan 2)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activity_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES contacts(id),
    event_type TEXT NOT NULL,  -- sent | opened | clicked | replied | bounced | unsubscribed | spam_complaint
    source TEXT NOT NULL,      -- smartlead | calendly | internal
    payload JSONB DEFAULT '{}',
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_activity_contact ON activity_log (contact_id);
CREATE INDEX IF NOT EXISTS idx_activity_type ON activity_log (client_id, event_type, occurred_at);

-- ─────────────────────────────────────────────────────────────────────────
-- Replies (normalised + classified — Plan 2)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS replies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    contact_id UUID NOT NULL REFERENCES contacts(id),
    activity_log_id UUID REFERENCES activity_log(id),
    body TEXT,
    classification TEXT,  -- positive | neutral | objection | unsubscribe | ooo
    classified_at TIMESTAMPTZ,
    response_draft_id UUID,  -- FK added after response_drafts created
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_replies_contact ON replies (contact_id);

-- ─────────────────────────────────────────────────────────────────────────
-- Response drafts (AI-drafted replies — Plan 2)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS response_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    reply_id UUID NOT NULL REFERENCES replies(id),
    body TEXT NOT NULL,
    qa_verdict JSONB,
    qa_status TEXT DEFAULT 'pending',
    status TEXT NOT NULL DEFAULT 'pending_approval',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE replies
    ADD CONSTRAINT fk_replies_response_draft
    FOREIGN KEY (response_draft_id) REFERENCES response_drafts(id);

-- ─────────────────────────────────────────────────────────────────────────
-- Meetings (Calendly events — Plan 2)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS meetings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES contacts(id),
    calendly_event_uri TEXT,
    status TEXT DEFAULT 'booked',  -- booked | attended | no_show | cancelled | rescheduled
    scheduled_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_meetings_contact ON meetings (contact_id);

-- ─────────────────────────────────────────────────────────────────────────
-- QA runs (per-message QA verdicts — Plan 2)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS qa_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    target_type TEXT NOT NULL,  -- outreach_draft | response_draft
    target_id UUID NOT NULL,
    rubric_version TEXT NOT NULL,
    verdict TEXT NOT NULL,  -- pass | fail
    failures JSONB DEFAULT '[]',
    confidence NUMERIC(3,2),
    retry_guidance TEXT,
    attempt_number INT DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_qa_target ON qa_runs (target_type, target_id);

-- ─────────────────────────────────────────────────────────────────────────
-- Outcomes (materialised view of decision → outcome — Plan 2+)
-- Placeholder table for now; materialised view DDL added in later plan.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    decision_id UUID,  -- FK to decision_log (from 001_foundation.sql)
    outcome_type TEXT NOT NULL,  -- reply | meeting | close | bounce | unsubscribe
    outcome_value JSONB DEFAULT '{}',
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_outcomes_decision ON outcomes (decision_id);

-- ─────────────────────────────────────────────────────────────────────────
-- Row-level security (RLS) — enforce client_id isolation
-- ─────────────────────────────────────────────────────────────────────────
ALTER TABLE icp_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE client_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach_sent ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE replies ENABLE ROW LEVEL SECURITY;
ALTER TABLE response_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;
ALTER TABLE qa_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE outcomes ENABLE ROW LEVEL SECURITY;

-- Service-role policy: full access (bypasses RLS in practice when using service_role key)
-- Example authenticated-user policy for later when clients access their own data:
-- CREATE POLICY client_access ON contacts FOR ALL USING (client_id = current_setting('app.client_id')::text);

COMMIT;
