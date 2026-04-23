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
