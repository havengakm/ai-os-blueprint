-- AIOS Plan 1 bootstrap bundle — generated 2026-04-23T07:20:59Z
-- Wipes public schema (tables + non-extension functions + custom types), then applies all 8 Plan 1 migrations.
-- Paste into Supabase SQL Editor and run once.  Destructive: drops tables + your functions + enums.
-- Extension-owned objects (pgvector, pgcrypto) are preserved.

-- ── 0a. Drop all tables in public schema ──────────────────────────────────
do $wipe_tables$
declare r record;
begin
  for r in (select tablename from pg_tables where schemaname = 'public')
  loop
    execute 'drop table if exists public.' || quote_ident(r.tablename) || ' cascade';
  end loop;
end
$wipe_tables$;

-- ── 0b. Drop non-extension functions in public schema ─────────────────────
-- Skips functions owned by extensions (pgvector, pgcrypto, etc.) via pg_depend join.
do $wipe_funcs$
declare r record;
begin
  for r in (
    select p.proname, pg_get_function_identity_arguments(p.oid) as args
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    left join pg_depend d on d.objid = p.oid and d.deptype = 'e'
    where n.nspname = 'public' and d.objid is null
  )
  loop
    execute 'drop function if exists public.' || quote_ident(r.proname) || '(' || r.args || ') cascade';
  end loop;
end
$wipe_funcs$;

-- ── 0c. Drop custom enum types in public schema (extension-owned types preserved) ──
do $wipe_types$
declare r record;
begin
  for r in (
    select t.typname
    from pg_type t
    join pg_namespace n on n.oid = t.typnamespace
    left join pg_depend d on d.objid = t.oid and d.deptype = 'e'
    where n.nspname = 'public' and t.typtype = 'e' and d.objid is null
  )
  loop
    execute 'drop type if exists public.' || quote_ident(r.typname) || ' cascade';
  end loop;
end
$wipe_types$;


-- ╔══════════════════════════════════════════════════════════════════════╗
-- ║  scripts/sql/001_foundation.sql
-- ╚══════════════════════════════════════════════════════════════════════╝
-- ── AI OS Foundation Schema ─────────────────────────────────────────────────
-- Run this in Supabase SQL editor to set up the foundation tables.
-- Requires: pgvector extension (enabled by default on Supabase).
-- All tables are client_id scoped with RLS enabled.

-- Enable required extensions
create extension if not exists vector;
create extension if not exists pgcrypto;


-- ── Clients ───────────────────────────────────────────────────────────────────
-- Identity row for the deployed client. Every productised deployment has exactly
-- one row here (the client whose AIOS this is). All other tables FK to clients(id)
-- so cascade deletes propagate cleanly when a client record is removed.

create table if not exists clients (
    id              text primary key,
    name            text not null,
    status          text not null default 'active' check (
        status in ('active', 'paused', 'churned')
    ),
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

alter table clients enable row level security;


-- ── Context Registry ──────────────────────────────────────────────────────────
-- Structured context beyond RAG chunks: people, strategies, objectives, projects
-- The AI OS reads this to understand WHO it's working for and WHAT they want.

create table if not exists context_registry (
    id              uuid primary key default gen_random_uuid(),
    client_id       text not null,
    context_type    text not null check (context_type in (
        'person', 'strategy', 'objective', 'project',
        'integration', 'preference', 'brand', 'metric'
    )),
    key             text not null,
    value           jsonb not null,
    summary         text not null,
    embedding       vector(1024),
    source          text not null default 'manual',
    active          boolean not null default true,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    unique (client_id, context_type, key)
);

create index if not exists idx_context_registry_client
    on context_registry (client_id, context_type, active);

-- Vector similarity search for context
create or replace function match_context_registry(
    query_embedding vector(1024),
    client_id_filter text,
    match_count int default 5
)
returns table (
    id uuid, client_id text, context_type text,
    key text, summary text, similarity float
)
language plpgsql as $$
begin
    return query
    select cr.id, cr.client_id, cr.context_type, cr.key, cr.summary,
           1 - (cr.embedding <=> query_embedding) as similarity
    from context_registry cr
    where cr.client_id = client_id_filter
      and cr.active = true
      and cr.embedding is not null
    order by cr.embedding <=> query_embedding
    limit match_count;
end;
$$;

alter table context_registry enable row level security;


-- ── Knowledge Base ────────────────────────────────────────────────────────────
-- Expert knowledge: frameworks, templates, principles, swipe files.
-- client_id = 'global' for shared knowledge, specific client_id for client-specific.
-- The AI OS queries this to apply expert thinking to decisions.

create table if not exists knowledge_base (
    id              uuid primary key default gen_random_uuid(),
    client_id       text not null default 'global',
    source          text not null,
    category        text not null check (category in (
        'framework', 'template', 'principle', 'tactic',
        'case_study', 'swipe_file', 'research'
    )),
    title           text not null,
    content         text not null,
    embedding       vector(1024),
    tags            text[] not null default '{}',
    active          boolean not null default true,
    created_at      timestamptz not null default now()
);

create index if not exists idx_knowledge_base_source
    on knowledge_base (client_id, source, category, active);

-- Vector similarity search for knowledge (searches both global + client-specific)
create or replace function match_knowledge_base(
    query_embedding vector(1024),
    client_id_filter text,
    source_filter text default null,
    match_count int default 3
)
returns table (
    id uuid, client_id text, source text, category text,
    title text, content text, similarity float
)
language plpgsql as $$
begin
    return query
    select kb.id, kb.client_id, kb.source, kb.category, kb.title, kb.content,
           1 - (kb.embedding <=> query_embedding) as similarity
    from knowledge_base kb
    where (kb.client_id = client_id_filter or kb.client_id = 'global')
      and kb.active = true
      and kb.embedding is not null
      and (source_filter is null or kb.source = source_filter)
    order by kb.embedding <=> query_embedding
    limit match_count;
end;
$$;

alter table knowledge_base enable row level security;


-- ── Decision Log ──────────────────────────────────────────────────────────────
-- Every significant decision gets logged here with context, reasoning, and outcome.
-- This is the core of the learning engine. Outcomes backfill when results arrive.

create table if not exists decision_log (
    id              uuid primary key default gen_random_uuid(),
    client_id       text not null,
    decision_type   text not null check (decision_type in (
        'copy_variant', 'icp_threshold', 'template_choice',
        'signal_weight', 'send_timing', 'channel_selection',
        'meeting_booking', 'reply_handling', 'manual_override',
        'system_config', 'enrichment_choice', 'framework_selection'
    )),
    context         jsonb not null,
    decision        text not null,
    reasoning       text,
    outcome         text check (outcome in ('positive', 'negative', 'neutral')),
    outcome_data    jsonb not null default '{}',
    outcome_at      timestamptz,
    source          text not null default 'system' check (source in (
        'system', 'human', 'ai_recommended'
    )),
    confidence      float check (confidence >= 0 and confidence <= 1),
    embedding       vector(1024),
    created_at      timestamptz not null default now()
);

create index if not exists idx_decision_log_type
    on decision_log (client_id, decision_type, created_at desc);

create index if not exists idx_decision_log_outcome
    on decision_log (client_id, outcome, created_at desc);

create index if not exists idx_decision_log_pending
    on decision_log (client_id, created_at desc)
    where outcome is null;

-- Vector similarity search for past decisions
create or replace function match_decisions(
    query_embedding vector(1024),
    client_id_filter text,
    decision_type_filter text default null,
    match_count int default 5
)
returns table (
    id uuid, client_id text, decision_type text,
    decision text, reasoning text, outcome text,
    outcome_data jsonb, confidence float, similarity float
)
language plpgsql as $$
begin
    return query
    select dl.id, dl.client_id, dl.decision_type,
           dl.decision, dl.reasoning, dl.outcome,
           dl.outcome_data, dl.confidence,
           1 - (dl.embedding <=> query_embedding) as similarity
    from decision_log dl
    where dl.client_id = client_id_filter
      and dl.embedding is not null
      and (decision_type_filter is null or dl.decision_type = decision_type_filter)
    order by dl.embedding <=> query_embedding
    limit match_count;
end;
$$;

alter table decision_log enable row level security;


-- ── Autonomy Rules ────────────────────────────────────────────────────────────
-- Per-client, per-action-type permissions. Tracks what the system can do autonomously.
-- Starts at 'suggest' for everything. Promotions require human approval.

create table if not exists autonomy_rules (
    id              uuid primary key default gen_random_uuid(),
    client_id       text not null,
    action_type     text not null,
    autonomy_level  text not null default 'suggest' check (
        autonomy_level in ('suggest', 'draft', 'act_notify', 'autonomous')
    ),
    conditions      jsonb not null default '{
        "min_confidence": 0.85,
        "min_sample_size": 50,
        "min_success_rate": 0.80,
        "min_days_at_current_level": 30,
        "requires_human_approval": true
    }',
    decisions_at_level  int not null default 0,
    success_rate        float,
    promoted_at         timestamptz,
    approved_by         text,
    approved_at         timestamptz,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    unique (client_id, action_type)
);

alter table autonomy_rules enable row level security;


-- ── Auto-update updated_at trigger ────────────────────────────────────────────
-- Reuse if it already exists from base-camp-agents migration

create or replace function update_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create or replace trigger clients_updated_at
    before update on clients
    for each row execute function update_updated_at();

create or replace trigger context_registry_updated_at
    before update on context_registry
    for each row execute function update_updated_at();

create or replace trigger autonomy_rules_updated_at
    before update on autonomy_rules
    for each row execute function update_updated_at();


-- ── Seed default autonomy rules ───────────────────────────────────────────────
-- All action types start at 'suggest'. Human must approve any promotion.

-- This is a template. Run with the actual client_id after deployment.
-- INSERT INTO autonomy_rules (client_id, action_type) VALUES
--     ('client-id-here', 'copy_variant'),
--     ('client-id-here', 'icp_threshold'),
--     ('client-id-here', 'template_choice'),
--     ('client-id-here', 'signal_weight'),
--     ('client-id-here', 'send_timing'),
--     ('client-id-here', 'channel_selection'),
--     ('client-id-here', 'meeting_booking'),
--     ('client-id-here', 'reply_handling'),
--     ('client-id-here', 'enrichment_choice'),
--     ('client-id-here', 'framework_selection');

-- ╔══════════════════════════════════════════════════════════════════════╗
-- ║  scripts/sql/002_scout.sql
-- ╚══════════════════════════════════════════════════════════════════════╝
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

-- ╔══════════════════════════════════════════════════════════════════════╗
-- ║  scripts/sql/003_client_config_extensions.sql
-- ╚══════════════════════════════════════════════════════════════════════╝
-- 003_client_config_extensions.sql
-- Extends client_config for the lead-sourcing + tiered-enrichment architecture
-- (decision 2026-04-20). Adds active_directories, scoring weights, per-tier budgets,
-- and tier thresholds. Depends on 002_scout.sql (client_config table).

BEGIN;

-- Active directories per client (list of directory keys this client pulls from)
ALTER TABLE client_config
    ADD COLUMN IF NOT EXISTS active_directories TEXT[] DEFAULT '{}';
-- Example: '{"clutch_agencies","g2_saas_buyers","fca_register"}'

-- Scoring weights (overrides code defaults)
ALTER TABLE client_config
    ADD COLUMN IF NOT EXISTS weights JSONB DEFAULT '{
        "fit": 40,
        "intent": 30,
        "reach": 20,
        "recency": 10
    }';

-- Per-tier enrichment budgets in cents per contact
-- Supersedes the single enrichment_budget_per_contact_cents column
ALTER TABLE client_config
    ADD COLUMN IF NOT EXISTS tier_budgets_cents JSONB DEFAULT '{
        "A": 30,
        "B": 15,
        "C": 10,
        "D": 5,
        "archive": 0
    }';

-- Tier thresholds (score ranges + hard gates)
-- phone_gate and research_gate are the hard gates enforced by the enrich orchestrator
ALTER TABLE client_config
    ADD COLUMN IF NOT EXISTS tier_thresholds JSONB DEFAULT '{
        "A": 80,
        "B": 65,
        "C": 50,
        "D": 35,
        "phone_gate": 50,
        "research_gate": 50,
        "archive_floor": 35
    }';

COMMIT;

-- ╔══════════════════════════════════════════════════════════════════════╗
-- ║  scripts/sql/004_contacts_extensions.sql
-- ╚══════════════════════════════════════════════════════════════════════╝
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

-- ╔══════════════════════════════════════════════════════════════════════╗
-- ║  scripts/sql/005_foundation_completion.sql
-- ╚══════════════════════════════════════════════════════════════════════╝
-- 005_foundation_completion.sql
-- Completes the foundation schema per Task 12.5 of the 2026-04-20 foundation-scout
-- migration plan. Adds business_context + client_facts tables (with Obsidian-style
-- graph-link columns from Max webinar 2026-04-21 pt 2), match_* RPCs, and a
-- match_context_graph RPC for breadth-first graph traversal. Extends the
-- decision_log.decision_type CHECK to reflect the Plan 1 task vocabulary. Adds
-- client_config.trigify_search_ids column required by the enrich stage.
--
-- Idempotent: uses CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS /
-- CREATE OR REPLACE for every mutation so re-runs are safe.

BEGIN;

-- ── business_context ──────────────────────────────────────────────────────────
-- Client-specific structured business context: offers, ICP, positioning, brand
-- guidelines, team, integrations. Loaded from markdown in context/{client}/*.md
-- via scripts/load_context.py (Task 16). Operator-authored Obsidian-style
-- [[entity-name]] backlinks resolve into related_context_ids / related_fact_ids
-- at load time.

CREATE TABLE IF NOT EXISTS business_context (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           TEXT NOT NULL,
    title               TEXT NOT NULL,
    body                TEXT NOT NULL,
    section_metadata    JSONB NOT NULL DEFAULT '{}',
    embedding           VECTOR(1024),
    source_path         TEXT,
    related_context_ids UUID[] NOT NULL DEFAULT '{}',
    related_fact_ids    UUID[] NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (client_id, title)
);

CREATE INDEX IF NOT EXISTS idx_business_context_client
    ON business_context (client_id);
CREATE INDEX IF NOT EXISTS idx_business_context_related_ctx
    ON business_context USING GIN (related_context_ids);
CREATE INDEX IF NOT EXISTS idx_business_context_related_facts
    ON business_context USING GIN (related_fact_ids);
-- ivfflat on embedding: lists=100 matches the tuning used for the other 1024-dim
-- embedding indices in this schema (good for <1M rows).
CREATE INDEX IF NOT EXISTS idx_business_context_embedding
    ON business_context USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

ALTER TABLE business_context ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE TRIGGER business_context_updated_at
    BEFORE UPDATE ON business_context
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ── client_facts ──────────────────────────────────────────────────────────────
-- Atomic key/value facts about the client: team members, named offers, integrations,
-- pricing tiers, expert framework alignments. Smaller granularity than
-- business_context (which stores passages). Also supports graph-links.

CREATE TABLE IF NOT EXISTS client_facts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           TEXT NOT NULL,
    key                 TEXT NOT NULL,
    value               JSONB NOT NULL,
    embedding           VECTOR(1024),
    source_urls         TEXT[] NOT NULL DEFAULT '{}',
    related_context_ids UUID[] NOT NULL DEFAULT '{}',
    related_fact_ids    UUID[] NOT NULL DEFAULT '{}',
    confidence          FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (client_id, key)
);

CREATE INDEX IF NOT EXISTS idx_client_facts_client
    ON client_facts (client_id);
CREATE INDEX IF NOT EXISTS idx_client_facts_related_ctx
    ON client_facts USING GIN (related_context_ids);
CREATE INDEX IF NOT EXISTS idx_client_facts_related_facts
    ON client_facts USING GIN (related_fact_ids);
CREATE INDEX IF NOT EXISTS idx_client_facts_embedding
    ON client_facts USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

ALTER TABLE client_facts ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE TRIGGER client_facts_updated_at
    BEFORE UPDATE ON client_facts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ── match_business_context ────────────────────────────────────────────────────
-- Embedding-similarity search over business_context for a given client.

CREATE OR REPLACE FUNCTION match_business_context(
    query_embedding VECTOR(1024),
    client_id_filter TEXT,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    client_id TEXT,
    title TEXT,
    body TEXT,
    section_metadata JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT bc.id, bc.client_id, bc.title, bc.body, bc.section_metadata,
           1 - (bc.embedding <=> query_embedding) AS similarity
    FROM business_context bc
    WHERE bc.client_id = client_id_filter
      AND bc.embedding IS NOT NULL
    ORDER BY bc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;


-- ── match_client_facts ────────────────────────────────────────────────────────
-- Embedding-similarity search over client_facts for a given client.

CREATE OR REPLACE FUNCTION match_client_facts(
    query_embedding VECTOR(1024),
    client_id_filter TEXT,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    client_id TEXT,
    key TEXT,
    value JSONB,
    source_urls TEXT[],
    confidence FLOAT,
    similarity FLOAT
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT cf.id, cf.client_id, cf.key, cf.value, cf.source_urls, cf.confidence,
           1 - (cf.embedding <=> query_embedding) AS similarity
    FROM client_facts cf
    WHERE cf.client_id = client_id_filter
      AND cf.embedding IS NOT NULL
    ORDER BY cf.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;


-- ── match_context_graph ───────────────────────────────────────────────────────
-- Breadth-first graph walk from a starting node up to `max_depth` hops, capped
-- at `max_nodes` reachable rows. Traverses both business_context and
-- client_facts via related_context_ids / related_fact_ids arrays. Returns a
-- flat set of (id, source_table, depth) rows; caller joins back to the actual
-- row data for full payloads.
--
-- Implemented as a recursive CTE: for each frontier node, look up its outgoing
-- edges from whichever table it lives in, emit the neighbours at depth+1, and
-- let the CTE recursion stop at `max_depth`. A `visited_ids` accumulator on
-- each recursion row tracks the ids already seen on that branch; neighbours
-- already in `visited_ids` are filtered out so cycles cannot re-enter. A
-- final DISTINCT pass collapses duplicates that arise when a node is reached
-- by multiple paths, and LIMIT caps the result at `max_nodes`.
--
-- The seed anchor is guarded with EXISTS on (start_id, client_id_filter) in
-- the appropriate source table: if `start_id` does not belong to
-- `client_id_filter`, the seed is empty and the function returns no rows
-- (prevents a one-UUID cross-tenant leak at depth 0).
--
-- Defaults: max_depth=3, max_nodes=50 (plan traversal caps).

CREATE OR REPLACE FUNCTION match_context_graph(
    client_id_filter TEXT,
    start_id UUID,
    start_table TEXT,   -- 'business_context' | 'client_facts'
    max_depth INT DEFAULT 3,
    max_nodes INT DEFAULT 50
)
RETURNS TABLE (
    id UUID,
    source_table TEXT,
    depth INT
)
LANGUAGE sql AS $$
    WITH RECURSIVE graph_walk(id, source_table, depth, visited_ids) AS (
        -- Seed: the start node itself at depth 0. Emitted only when
        -- (start_id, start_table) exists under client_id_filter. Invalid
        -- start_table or cross-tenant start_id → both branches miss → seed
        -- is empty → function returns no rows.
        SELECT start_id, start_table, 0, ARRAY[start_id]::UUID[]
        WHERE (start_table = 'business_context'
               AND EXISTS (SELECT 1 FROM business_context
                           WHERE id = start_id
                             AND client_id = client_id_filter))
           OR (start_table = 'client_facts'
               AND EXISTS (SELECT 1 FROM client_facts
                           WHERE id = start_id
                             AND client_id = client_id_filter))

        UNION ALL

        -- Recurse: for each node on the frontier, expand its outgoing edges
        -- from whichever table it lives in. Both edge arrays
        -- (related_context_ids / related_fact_ids) are unnested and emitted
        -- with the correct target-table label. Neighbours already in
        -- gw.visited_ids are skipped (cycle guard); surviving neighbours
        -- append their id to the visited accumulator for descendant rows.
        SELECT edges.neighbour_id, edges.neighbour_table, gw.depth + 1,
               gw.visited_ids || edges.neighbour_id
        FROM graph_walk gw
        CROSS JOIN LATERAL (
            -- Edges out of a business_context node
            SELECT unnest(bc.related_context_ids) AS neighbour_id,
                   'business_context'::TEXT AS neighbour_table
            FROM business_context bc
            WHERE gw.source_table = 'business_context'
              AND bc.id = gw.id
              AND bc.client_id = client_id_filter
            UNION ALL
            SELECT unnest(bc.related_fact_ids) AS neighbour_id,
                   'client_facts'::TEXT AS neighbour_table
            FROM business_context bc
            WHERE gw.source_table = 'business_context'
              AND bc.id = gw.id
              AND bc.client_id = client_id_filter
            UNION ALL
            -- Edges out of a client_facts node
            SELECT unnest(cf.related_context_ids) AS neighbour_id,
                   'business_context'::TEXT AS neighbour_table
            FROM client_facts cf
            WHERE gw.source_table = 'client_facts'
              AND cf.id = gw.id
              AND cf.client_id = client_id_filter
            UNION ALL
            SELECT unnest(cf.related_fact_ids) AS neighbour_id,
                   'client_facts'::TEXT AS neighbour_table
            FROM client_facts cf
            WHERE gw.source_table = 'client_facts'
              AND cf.id = gw.id
              AND cf.client_id = client_id_filter
        ) edges
        WHERE gw.depth < max_depth
          AND edges.neighbour_id IS NOT NULL
          AND edges.neighbour_id <> ALL(gw.visited_ids)
    )
    SELECT DISTINCT ON (graph_walk.id, graph_walk.source_table)
           graph_walk.id, graph_walk.source_table, graph_walk.depth
    FROM graph_walk
    ORDER BY graph_walk.id, graph_walk.source_table, graph_walk.depth ASC
    LIMIT max_nodes;
$$;


-- ── Extend decision_log.decision_type CHECK ───────────────────────────────────
-- Adds Plan 1 task-specific decision types. Keeps existing values for backward
-- compatibility with prior decision_log entries. Once Plan 1 ships, we can
-- optionally deprecate 'enrichment_choice' after a burn-in period.

ALTER TABLE decision_log DROP CONSTRAINT IF EXISTS decision_log_decision_type_check;
ALTER TABLE decision_log ADD CONSTRAINT decision_log_decision_type_check CHECK (
    decision_type IN (
        -- Original 001_foundation.sql values (retained for back-compat)
        'copy_variant', 'icp_threshold', 'template_choice',
        'signal_weight', 'send_timing', 'channel_selection',
        'meeting_booking', 'reply_handling', 'manual_override',
        'system_config', 'enrichment_choice', 'framework_selection',
        -- Plan 1 additions (2026-04-21)
        'research_contact', 'render_draft', 'component_selection',
        'screen_contact', 'identity_lookup', 'source_selection', 'enrich_contact'
    )
);


-- ── client_config.trigify_search_ids ──────────────────────────────────────────
-- Pre-configured Trigify search IDs for this client. Populated at onboarding
-- via the configure-trigify-monitors skill. Empty array = Trigify adapter will
-- skip with reason='no_monitors_configured'. Required by Task 12d's
-- `get_client_trigify_search_ids` storage method.

ALTER TABLE client_config
    ADD COLUMN IF NOT EXISTS trigify_search_ids TEXT[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN client_config.trigify_search_ids IS
    'Pre-configured Trigify search IDs for this client. Populated at onboarding via configure-trigify-monitors skill. Empty array = Trigify adapter will skip with no_monitors_configured reason.';

COMMIT;

-- ╔══════════════════════════════════════════════════════════════════════╗
-- ║  scripts/sql/006_component_registry.sql
-- ╚══════════════════════════════════════════════════════════════════════╝
-- 006_component_registry.sql
-- Micro-granularity component registry per Task 13 of the Plan 1 roadmap.
-- Complements the macro-framework `templates` table from 002_scout.sql: templates
-- stay as the sequence-level skeleton; `component_variants` carries the individual
-- swappable pieces (subject lines, icebreakers, pain hooks, offer frames, CTAs,
-- signatures) that the Task 15 composer assembles at send-time.
--
-- The outreach_drafts.component_selections JSONB column records the exact variant
-- tuple chosen for each rendered draft, giving Plan 7's cohort evaluator
-- component-level attribution when outcome events arrive.
--
-- Idempotent: uses CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS /
-- CREATE OR REPLACE for every mutation so re-runs are safe.

BEGIN;

-- ── component_variants ────────────────────────────────────────────────────────
-- One row per swappable component variant. The UNIQUE key
-- (client_id, niche, offer_label, component_type, variant_key) gives the YAML
-- loader a stable identity: re-running the sync keeps the same row UUID, which
-- is required so attribution events emitted months apart still resolve to the
-- same variant. `variant_key` is the YAML-author-controlled stable handle
-- (snake_case, e.g. "agency_growth_hook_v1"); UUIDs stay an implementation
-- detail.
--
-- `win_rate` + `sample_size` are populated by Plan 2's cohort evaluator;
-- `ab_epsilon` is the per-variant exploration rate for the Plan 2 bandit.
-- `status` gates which variants the composer is allowed to pick from
-- ('approved' + 'draft' eligible during warm-up; 'paused'/'killed' excluded).

CREATE TABLE IF NOT EXISTS component_variants (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    component_type      TEXT NOT NULL CHECK (component_type IN (
        'subject_line', 'icebreaker', 'pain_hook', 'offer_frame', 'cta', 'signature'
    )),
    variant_key         TEXT NOT NULL,
    variant_content     TEXT NOT NULL,
    niche               TEXT NOT NULL,
    offer_label         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
        'draft', 'approved', 'paused', 'killed'
    )),
    metadata            JSONB NOT NULL DEFAULT '{}',
    win_rate            FLOAT NULL CHECK (win_rate IS NULL OR (win_rate >= 0 AND win_rate <= 1)),
    sample_size         INT NOT NULL DEFAULT 0,
    ab_epsilon          FLOAT NOT NULL DEFAULT 0.1 CHECK (ab_epsilon >= 0 AND ab_epsilon <= 1),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (client_id, niche, offer_label, component_type, variant_key)
);

-- Selection index: composer reads by (client, niche, offer, type, status) at
-- compose-time — this index covers that predicate directly.
CREATE INDEX IF NOT EXISTS idx_component_variants_selection
    ON component_variants (client_id, niche, offer_label, component_type, status);

-- Winners index: Plan 2's bandit periodically asks "top N approved variants by
-- win_rate for this client" — a partial index on (client_id, win_rate DESC)
-- filtered to `status = 'approved'` and a non-null win_rate keeps the working
-- set small.
CREATE INDEX IF NOT EXISTS idx_component_variants_winners
    ON component_variants (client_id, win_rate DESC)
    WHERE status = 'approved' AND win_rate IS NOT NULL;

ALTER TABLE component_variants ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE TRIGGER component_variants_updated_at
    BEFORE UPDATE ON component_variants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ── outreach_drafts.component_selections ─────────────────────────────────────
-- Records the exact variant tuple chosen at compose-time. Mirrors the existing
-- `placeholder_fills` pattern (also JSONB DEFAULT '{}') added by 002_scout.sql.
-- Shape:
--   {
--     "subject_line": "<uuid>",
--     "icebreaker":   "<uuid>",
--     "pain_hook":    "<uuid>",
--     "offer_frame":  "<uuid>",
--     "cta":          "<uuid>",
--     "signature":    "<uuid>"
--   }
-- A sparse map is fine — not every draft uses every component type.

ALTER TABLE outreach_drafts
    ADD COLUMN IF NOT EXISTS component_selections JSONB NOT NULL DEFAULT '{}';

COMMENT ON COLUMN outreach_drafts.component_selections IS
    'Records the exact component variant tuple chosen at compose-time: {"subject_line": "<uuid>", "icebreaker": "<uuid>", "pain_hook": "<uuid>", "offer_frame": "<uuid>", "cta": "<uuid>", "signature": "<uuid>"}. Used by Plan 7 cohort evaluator for component-level attribution.';

COMMIT;

-- ╔══════════════════════════════════════════════════════════════════════╗
-- ║  scripts/sql/008_budget_tracking.sql
-- ╚══════════════════════════════════════════════════════════════════════╝
-- 008_budget_tracking.sql
-- Adds rolling per-tier spend tracking to client_config for
-- SupabaseBudgetTracker. Depends on 003_client_config_extensions.sql
-- (which introduced tier_budgets_cents with the same tier keys).
--
-- SupabaseBudgetTracker computes remaining = tier_budgets_cents[tier] -
-- tier_spent_cents[tier] and fails safe (remaining = 0) when either side
-- is missing. Monthly reset is a future scheduler job (Task 16.6).
--
-- Idempotent: ADD COLUMN IF NOT EXISTS + DEFAULT '{}' so re-runs are safe.

BEGIN;

ALTER TABLE client_config
    ADD COLUMN IF NOT EXISTS tier_spent_cents JSONB NOT NULL DEFAULT '{}';

COMMENT ON COLUMN client_config.tier_spent_cents IS
    'Rolling per-tier spend in cents, map {tier: cents_spent}. SupabaseBudgetTracker reads this subtracted from tier_budgets_cents to compute remaining budget. Reset monthly by scheduler (Task 16.6).';

COMMIT;

-- ╔══════════════════════════════════════════════════════════════════════╗
-- ║  scripts/sql/009_trigify_discovery_config.sql
-- ╚══════════════════════════════════════════════════════════════════════╝
-- 009_trigify_discovery_config.sql
-- Adds per-client Trigify discovery thresholds. Consumed by
-- TrigifyDiscoverySource (Task 1.5.9b). Defaults match Max Mitcham
-- webinar 2026-04-22 (YouTube bKEmJIch0nI).

BEGIN;

ALTER TABLE client_config
    ADD COLUMN IF NOT EXISTS trigify_discovery_config JSONB NOT NULL DEFAULT '{
        "min_engagement_to_pull": 10,
        "cook_time_hours": 24,
        "max_leads_per_run": 100,
        "search_subsets_enabled": ["intent", "competitor", "thought_leader", "brand"]
    }';

COMMENT ON COLUMN client_config.trigify_discovery_config IS
    'Per-client operator-tunable thresholds for TrigifyDiscoverySource. Defaults match Max Mitcham daily-cron pattern (10-like minimum, 24h cook time emergent from daily cadence, 100-lead cap per run, all 4 monitor subsets enabled).';

COMMIT;
