# Foundation + Scout Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Plan 1 from the design spec — a pipeline that takes Clymb contacts from DB → rendered drafts (no QA, no send) in full BaseSystem-conformant fashion. End-to-end dry-run on 10 real contacts.

**Architecture:** Migrate Scout's outbound pipeline from `/home/kirsten/01_PERSONAL/10_PERSONAL_PROJECTS/base-camp-agents` into the blueprint's `systems/scout/` directory. Every stage extends `BaseSystem`, calls `load_foundation()`, logs decisions, and queries pattern_matcher/knowledge before acting. New template architecture replaces base-camp-agents' `generate_outreach.py` (templates + AI placeholder fills, not free-form generation).

**Tech Stack:** Python 3.11, FastAPI, Supabase (Postgres + pgvector + RLS), Anthropic SDK (Haiku), Railway, httpx, structlog, pytest (+ pytest-asyncio), python-dotenv.

**Source references:**
- Blueprint repo: `/home/kirsten/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint/`
- Migration source: `/home/kirsten/01_PERSONAL/10_PERSONAL_PROJECTS/base-camp-agents/`
- Design spec: [docs/superpowers/specs/2026-04-20-aios-clymb-deployment-design.md](../specs/2026-04-20-aios-clymb-deployment-design.md)
- BaseSystem contract: [systems/base.py](../../../systems/base.py)
- Foundation modules: [os/foundation/](../../../os/foundation/)

---

## File structure — what gets created or modified

**Created:**

```
ai-os-blueprint/
├── pyproject.toml                                   # Python dependencies
├── Procfile                                         # Railway web process
├── railway.toml                                     # Railway build/deploy config
├── .env.example                                     # Config template (in root, not config/)
├── config/
│   └── settings.py                                  # Pydantic settings loader
├── api/
│   ├── __init__.py
│   ├── main.py                                      # FastAPI app
│   ├── deps.py                                      # DB session, system registry wiring
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── verify_signatures.py                     # HMAC + cron-secret middleware
│   └── routers/
│       ├── __init__.py
│       ├── health.py                                # /health endpoint
│       └── pipeline.py                              # /api/pipeline/trigger endpoint
├── scripts/
│   ├── setup_client.sh                              # Migrated from base-camp-agents
│   ├── load_context.py                              # Migrated
│   ├── load_knowledge.py                            # New (embeds data/knowledge/*)
│   ├── seed_autonomy_rules.py                       # New
│   └── sql/
│       └── 002_scout.sql                            # New: Scout-specific tables
├── systems/scout/
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── pull.py                                  # Migrated from pull_leads.py
│   │   ├── score.py                                 # Migrated from score_contacts.py
│   │   ├── screen.py                                # Migrated from screen_contacts.py
│   │   └── enrich.py                                # Migrated + merged from enrich_contacts.py + verify_emails.py
│   ├── outreach/
│   │   ├── __init__.py
│   │   ├── templates/                               # Markdown + YAML templates
│   │   │   └── _schema.md                           # Template file format spec
│   │   ├── template_store.py                        # Template loader (files → DB)
│   │   ├── research.py                              # Per-contact placeholder research
│   │   └── renderer.py                              # Template fill engine
│   └── sql/
│       └── migrations.sql                           # Symlink to scripts/sql/002_scout.sql
├── tests/
│   ├── __init__.py
│   ├── conftest.py                                  # Shared pytest fixtures
│   ├── test_api/
│   │   ├── __init__.py
│   │   └── test_health.py
│   ├── test_pipeline/
│   │   ├── __init__.py
│   │   ├── test_pull.py
│   │   ├── test_score.py
│   │   ├── test_screen.py
│   │   └── test_enrich.py
│   └── test_outreach/
│       ├── __init__.py
│       ├── test_template_store.py
│       ├── test_research.py
│       └── test_renderer.py
└── data/reference/sops/
    ├── README.md                                    # SOP manifest
    ├── _templates/
    │   └── sop-template.md                          # Meta-SOP
    ├── deployment/
    │   ├── 01-fork-blueprint.md
    │   ├── 02-setup-supabase.md
    │   ├── 03-setup-railway.md
    │   ├── 04-configure-env.md
    │   └── 06-load-context.md
    └── pipeline/
        ├── scout-pipeline-nightly-run.md
        └── write-approve-template.md
```

**Modified:**

- [systems/scout/skill.py](../../../systems/scout/skill.py): extended from stub to route to real pipeline stages (minimal changes in this plan — most routing added in Plan 2 when send/reply handling exists)

**Unchanged (referenced but not touched):**

- `systems/base.py`, `os/foundation/*.py`, `os/memory/store.py`, `os/registry.py` — the contract Scout conforms to
- `scripts/sql/001_foundation.sql` — already exists, run during Supabase setup

---

## Prerequisites

- Python 3.11+ installed locally
- `uv` package manager installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Git configured
- Access to: Anthropic API key, Apollo API key, Supabase account, Railway account, Voyage AI key (Kirsten's)
- Kirsten's base-camp-agents repo available at `/home/kirsten/01_PERSONAL/10_PERSONAL_PROJECTS/base-camp-agents/` for migration reference

---

## Task 1: Create dedicated worktree + verify environment

**Files:**
- No new files in this task

- [ ] **Step 1: Create worktree for this plan**

Run:
```bash
cd /home/kirsten/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint
git worktree add ../ai-os-blueprint-plan1 -b plan1-foundation-scout
cd ../ai-os-blueprint-plan1
```

Expected: new directory at `../ai-os-blueprint-plan1` on branch `plan1-foundation-scout`.

- [ ] **Step 2: Verify Python 3.11+ available**

Run:
```bash
python3 --version
```

Expected: `Python 3.11.x` or newer. If not, install via pyenv or system package manager.

- [ ] **Step 3: Verify uv installed**

Run:
```bash
uv --version
```

Expected: `uv 0.x.x`. If not installed: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

- [ ] **Step 4: Verify access to source repo**

Run:
```bash
ls /home/kirsten/01_PERSONAL/10_PERSONAL_PROJECTS/base-camp-agents/scripts/pull_leads.py
```

Expected: file listed. If not, stop and confirm the migration source is accessible.

---

## Task 2: Python dependencies (pyproject.toml)

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Create pyproject.toml**

Create `/home/kirsten/01_PERSONAL/10_PERSONAL_PROJECTS/ai-os-blueprint-plan1/pyproject.toml`:

```toml
[project]
name = "ai-os-blueprint"
version = "0.1.0"
description = "AI Operating System Blueprint — productised AIOS template"
requires-python = ">=3.11"
dependencies = [
    # Web framework
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",

    # Anthropic SDK
    "anthropic>=0.34.0",

    # Database
    "supabase>=2.7.0",
    "asyncpg>=0.29.0",
    "pgvector>=0.3.0",

    # HTTP client
    "httpx>=0.27.0",

    # Config
    "pydantic>=2.8.0",
    "pydantic-settings>=2.4.0",
    "python-dotenv>=1.0.0",

    # Logging + observability
    "structlog>=24.0.0",
    "sentry-sdk[fastapi]>=2.13.0",

    # Utilities
    "pyyaml>=6.0",
    "python-slugify>=8.0",
    "tenacity>=8.5.0",  # for retries with backoff
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-mock>=3.14",
    "pytest-cov>=5.0",
    "ruff>=0.6",
    "mypy>=1.11",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
python_version = "3.11"
strict_optional = true
```

- [ ] **Step 2: Install dependencies with uv**

Run:
```bash
uv sync
```

Expected: `.venv/` directory created, `uv.lock` generated. All packages install without errors.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "Add pyproject.toml with core dependencies"
```

---

## Task 3: Environment config + settings loader

**Files:**
- Create: `.env.example`
- Create: `config/settings.py`
- Test: `tests/test_config_settings.py`

- [ ] **Step 1: Create `.env.example`**

Create `.env.example` in repo root:

```bash
# === Client identity ===
CLIENT_ID=clymb
CLIENT_DISPLAY_NAME="CLYMB Co."

# === Database ===
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ANON_KEY=

# === AI ===
ANTHROPIC_API_KEY=
VOYAGE_API_KEY=

# === Email sending (populated in Plan 2) ===
SMARTLEAD_API_KEY=
SMARTLEAD_WEBHOOK_SECRET=

# === Enrichment ===
APOLLO_API_KEY=
ANYMAIL_FINDER_API_KEY=
ZEROBOUNCE_API_KEY=

# === Communication (populated in Plan 3) ===
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_CHAT_ID=
CALENDLY_WEBHOOK_SECRET=

# === Internal ===
CRON_SECRET=
API_PUBLIC_URL=http://localhost:8000
LOG_LEVEL=INFO
ENVIRONMENT=development
```

- [ ] **Step 2: Write the failing test for settings**

Create `tests/test_config_settings.py`:

```python
import os
import pytest
from pydantic import ValidationError


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test-client")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("CRON_SECRET", "test-cron")

    from config.settings import get_settings
    get_settings.cache_clear()  # reset lru_cache
    s = get_settings()

    assert s.client_id == "test-client"
    assert s.supabase_url == "https://test.supabase.co"
    assert s.anthropic_api_key == "test-anthropic"
    assert s.environment == "development"  # default


def test_settings_missing_required_raises(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from config.settings import get_settings
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()
```

- [ ] **Step 3: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_config_settings.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'config.settings'`.

- [ ] **Step 4: Implement `config/settings.py`**

Create `config/__init__.py` (empty file) and `config/settings.py`:

```python
"""Typed, env-backed application settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Client identity ---
    client_id: str = Field(..., description="Short machine-readable client ID")
    client_display_name: str = Field(default="", description="Human-readable client name")

    # --- Database ---
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str = ""

    # --- AI ---
    anthropic_api_key: str
    voyage_api_key: str = ""

    # --- Email sending (Plan 2) ---
    smartlead_api_key: str = ""
    smartlead_webhook_secret: str = ""

    # --- Enrichment ---
    apollo_api_key: str = ""
    anymail_finder_api_key: str = ""
    zerobounce_api_key: str = ""

    # --- Communication (Plan 3) ---
    telegram_bot_token: str = ""
    telegram_admin_chat_id: str = ""
    calendly_webhook_secret: str = ""

    # --- Internal ---
    cron_secret: str
    api_public_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    environment: str = "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance. Call cache_clear() in tests to reset."""
    return Settings()
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_config_settings.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add .env.example config/__init__.py config/settings.py tests/test_config_settings.py
git commit -m "Add Settings loader + .env.example"
```

---

## Task 4: Supabase schema — 002_scout.sql

**Files:**
- Create: `scripts/sql/002_scout.sql`
- Create: `systems/scout/sql/migrations.sql` (symlink)

- [ ] **Step 1: Verify 001_foundation.sql exists**

Run:
```bash
ls scripts/sql/001_foundation.sql
```

Expected: file exists. (Already in blueprint.)

- [ ] **Step 2: Create `scripts/sql/002_scout.sql`**

Full migration file — paste this content verbatim:

```sql
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
```

- [ ] **Step 3: Create systems/scout/sql/migrations.sql symlink**

Run:
```bash
mkdir -p systems/scout/sql
cd systems/scout/sql
ln -s ../../../scripts/sql/002_scout.sql migrations.sql
cd ../../..
```

Expected: `systems/scout/sql/migrations.sql` symlinks to `scripts/sql/002_scout.sql`.

- [ ] **Step 4: Commit**

```bash
git add scripts/sql/002_scout.sql systems/scout/sql/migrations.sql
git commit -m "Add Scout schema migration 002_scout.sql"
```

---

## Task 5: Create Clymb's Supabase project + run migrations

This task is manual (done via Supabase dashboard). Document the steps in an SOP.

**Files:**
- Create: `data/reference/sops/deployment/02-setup-supabase.md`

- [ ] **Step 1: Create Supabase project for Clymb**

Go to https://supabase.com/dashboard, create new project:
- Name: `clymb-ai-os`
- Region: closest to Kirsten (e.g., `eu-west-1` for South Africa)
- Database password: generated, stored in password manager

- [ ] **Step 2: Run `001_foundation.sql`**

In Supabase SQL Editor, paste and run contents of `scripts/sql/001_foundation.sql`. Verify no errors.

- [ ] **Step 3: Run `002_scout.sql`**

In Supabase SQL Editor, paste and run contents of `scripts/sql/002_scout.sql`. Verify no errors.

- [ ] **Step 4: Verify tables exist**

Run in Supabase SQL Editor:
```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
```

Expected tables include: `activity_log`, `autonomy_rules`, `campaigns`, `client_config`, `clients`, `contacts`, `decision_log`, `icp_definitions`, `knowledge_base`, `meetings`, `outreach_drafts`, `outreach_sent`, `outcomes`, `qa_runs`, `replies`, `response_drafts`, `templates`.

- [ ] **Step 5: Copy Supabase URL + service role key into `.env`**

Create `.env` in repo root (DO NOT COMMIT) and fill:
```
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
SUPABASE_ANON_KEY=<anon-key>
CLIENT_ID=clymb
CLIENT_DISPLAY_NAME=CLYMB Co.
ANTHROPIC_API_KEY=<kirsten's key>
CRON_SECRET=<generate: openssl rand -hex 32>
```

- [ ] **Step 6: Write SOP**

Create `data/reference/sops/deployment/02-setup-supabase.md`:

```markdown
# SOP: Setup Supabase for New Client Deployment
Version: 1.0
Last reviewed: 2026-04-20
Owner: Kirsten / VA

## Purpose
Create a fresh Supabase project for a new client, run foundation + Scout schema migrations, and capture credentials. Every client gets their own Supabase project (no shared DB) — full data isolation per CLAUDE.md Data Protection rules.

## Trigger
New client signed, Step 2 of Client Deployment SOP.

## Inputs
- Client name (slug + display name)
- Client's preferred region (proximity to target market)
- Access to Kirsten's Supabase org

## Outputs
- Live Supabase project named `{client-slug}-ai-os`
- Both migrations executed successfully
- `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` + `SUPABASE_ANON_KEY` recorded for `.env`

## Steps
1. Go to https://supabase.com/dashboard → New project.
2. Name it `{client-slug}-ai-os`. Region = closest to client's target market. Plan = Free (upgrade to Pro at 5 clients).
3. Generate and store DB password in password manager (1Password / Bitwarden).
4. Wait for project provisioning (~2 min).
5. Open SQL Editor → paste contents of `scripts/sql/001_foundation.sql` → Run. Check for errors.
6. Same editor → paste contents of `scripts/sql/002_scout.sql` → Run.
7. Verify tables exist via `SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';`
8. Project Settings → API → copy `URL`, `anon key`, `service_role key`. Save to password manager + add to client's `.env`.

## QA
- All expected tables present (20+)
- Running a SELECT on each table returns 0 rows without error
- Service role key tested via `curl -H "apikey: <key>" <url>/rest/v1/clients`

## Common errors
| Error | Cause | Fix |
|---|---|---|
| `extension "vector" does not exist` | pgvector not enabled | Database → Extensions → enable `vector` |
| `extension "pgcrypto" does not exist` | pgcrypto not enabled | Database → Extensions → enable `pgcrypto` |
| `relation already exists` | Running 001 twice | Drop schema and restart, or skip 001 |

## Escalation
If migration fails > 2 times: stop, capture full error output, escalate to Kirsten before retrying.

## Automation notes
- Fully automated: no — manual dashboard steps required
- Partially automatable: project creation via Supabase Management API (future enhancement)
- Not automated: DB password generation (intentional — stored outside code)

## Change log
- v1.0 — 2026-04-20 — initial
```

- [ ] **Step 7: Commit**

```bash
git add data/reference/sops/deployment/02-setup-supabase.md
git commit -m "Add Supabase setup SOP"
```

---

## Task 6: API scaffold + health endpoint

**Files:**
- Create: `api/__init__.py`
- Create: `api/main.py`
- Create: `api/deps.py`
- Create: `api/routers/__init__.py`
- Create: `api/routers/health.py`
- Create: `api/middleware/__init__.py`
- Create: `api/middleware/verify_signatures.py`
- Create: `Procfile`
- Create: `railway.toml`
- Test: `tests/test_api/test_health.py`

- [ ] **Step 1: Write failing test for health endpoint**

Create `tests/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app(monkeypatch):
    # Minimal env for settings to load
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")

    from config.settings import get_settings
    get_settings.cache_clear()

    from api.main import create_app
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)
```

Create `tests/test_api/__init__.py` (empty) and `tests/test_api/test_health.py`:

```python
def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["client_id"] == "test"


def test_health_includes_version(client):
    resp = client.get("/health")
    assert "version" in resp.json()
```

- [ ] **Step 2: Run test — should fail**

Run:
```bash
uv run pytest tests/test_api/test_health.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'api.main'`.

- [ ] **Step 3: Create `api/__init__.py` (empty)**

Run:
```bash
mkdir -p api/routers api/middleware
touch api/__init__.py api/routers/__init__.py api/middleware/__init__.py
```

- [ ] **Step 4: Create `api/routers/health.py`**

```python
"""Health check endpoint."""
from fastapi import APIRouter

from config.settings import get_settings

router = APIRouter()


@router.get("/health")
async def health():
    settings = get_settings()
    return {
        "status": "ok",
        "client_id": settings.client_id,
        "environment": settings.environment,
        "version": "0.1.0",
    }
```

- [ ] **Step 5: Create `api/deps.py`**

```python
"""Shared FastAPI dependencies (DB session, system wiring)."""
from __future__ import annotations

from functools import lru_cache

from supabase import acreate_client, AsyncClient

from config.settings import get_settings


@lru_cache(maxsize=1)
def _supabase_client_singleton() -> AsyncClient:
    # Placeholder — replaced with async init in main.py lifespan
    raise RuntimeError("Supabase client not yet initialised — use get_supabase")


async def get_supabase() -> AsyncClient:
    """Return a cached Supabase async client."""
    settings = get_settings()
    # Note: acreate_client is async. Caller responsibility to manage lifecycle.
    return await acreate_client(settings.supabase_url, settings.supabase_service_role_key)
```

- [ ] **Step 6: Create `api/main.py`**

```python
"""FastAPI app factory + entrypoint."""
from __future__ import annotations

import logging

import structlog
from fastapi import FastAPI

from config.settings import get_settings
from api.routers import health


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=level.upper())
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ]
    )


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging(settings.log_level)

    app = FastAPI(
        title="AI OS Blueprint",
        description="Productised AI Operating System",
        version="0.1.0",
    )

    app.include_router(health.router)

    return app


app = create_app()
```

- [ ] **Step 7: Run tests — should pass**

Run:
```bash
uv run pytest tests/test_api/test_health.py -v
```

Expected: 2 passed.

- [ ] **Step 8: Create `Procfile`**

```
web: uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

- [ ] **Step 9: Create `railway.toml`**

```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "uvicorn api.main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

- [ ] **Step 10: Test locally**

Run:
```bash
uv run uvicorn api.main:app --port 8000
```

In another terminal:
```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok","client_id":"clymb",...}` (or "test" if using test env).

Stop uvicorn with Ctrl-C.

- [ ] **Step 11: Commit**

```bash
git add api/ Procfile railway.toml tests/conftest.py tests/test_api/
git commit -m "Add FastAPI scaffold + health endpoint"
```

---

## Task 7: HMAC signature middleware + cron auth

**Files:**
- Create: `api/middleware/verify_signatures.py`
- Test: `tests/test_api/test_middleware.py`

- [ ] **Step 1: Write failing test for cron-secret middleware**

Create `tests/test_api/test_middleware.py`:

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_middleware(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "the-secret")

    from config.settings import get_settings
    get_settings.cache_clear()

    from api.middleware.verify_signatures import require_cron_secret

    app = FastAPI()

    @app.post("/protected", dependencies=[require_cron_secret()])
    async def protected():
        return {"ok": True}

    return app


def test_rejects_missing_secret(app_with_middleware):
    client = TestClient(app_with_middleware)
    r = client.post("/protected")
    assert r.status_code == 401


def test_rejects_wrong_secret(app_with_middleware):
    client = TestClient(app_with_middleware)
    r = client.post("/protected", headers={"X-Cron-Secret": "wrong"})
    assert r.status_code == 401


def test_accepts_correct_secret(app_with_middleware):
    client = TestClient(app_with_middleware)
    r = client.post("/protected", headers={"X-Cron-Secret": "the-secret"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_api/test_middleware.py -v
```

Expected: FAIL (`require_cron_secret` not defined).

- [ ] **Step 3: Implement middleware**

Create `api/middleware/verify_signatures.py`:

```python
"""Auth helpers: cron-secret header + HMAC webhook signature."""
from __future__ import annotations

import hmac
import hashlib

from fastapi import Depends, Header, HTTPException, status

from config.settings import get_settings


def require_cron_secret():
    """FastAPI Depends factory — requires X-Cron-Secret header to match CRON_SECRET env."""
    async def _verify(x_cron_secret: str | None = Header(default=None)):
        settings = get_settings()
        if not x_cron_secret or not hmac.compare_digest(x_cron_secret, settings.cron_secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing cron secret")
    return Depends(_verify)


def verify_hmac_signature(payload: bytes, received_signature: str, secret: str) -> bool:
    """Constant-time HMAC-SHA256 signature check."""
    if not received_signature or not secret:
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received_signature)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_api/test_middleware.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add api/middleware/verify_signatures.py tests/test_api/test_middleware.py
git commit -m "Add HMAC + cron-secret middleware"
```

---

## Task 8: Pipeline trigger endpoint (stub)

**Files:**
- Create: `api/routers/pipeline.py`
- Modify: `api/main.py`
- Test: `tests/test_api/test_pipeline_router.py`

This task wires up the endpoint that cron will hit. The actual pipeline logic comes in Tasks 11-14; this task just makes the endpoint reachable.

- [ ] **Step 1: Write failing test**

Create `tests/test_api/test_pipeline_router.py`:

```python
def test_pipeline_trigger_requires_cron_secret(client):
    r = client.post("/api/pipeline/trigger")
    assert r.status_code == 401


def test_pipeline_trigger_accepts_valid_secret(client):
    r = client.post(
        "/api/pipeline/trigger",
        headers={"X-Cron-Secret": "test-cron"},
        json={"stage": "pull", "dry_run": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["stage"] == "pull"
    assert body["dry_run"] is True
    assert "status" in body
```

- [ ] **Step 2: Run test — should fail**

```bash
uv run pytest tests/test_api/test_pipeline_router.py -v
```

Expected: FAIL (endpoint not wired).

- [ ] **Step 3: Create `api/routers/pipeline.py`**

```python
"""Pipeline trigger endpoint (stub — implementation fills in with Tasks 11-14)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from api.middleware.verify_signatures import require_cron_secret

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


class TriggerRequest(BaseModel):
    stage: Literal["pull", "score", "screen", "enrich", "research", "render", "full"]
    dry_run: bool = False
    limit: int | None = None


@router.post("/trigger", dependencies=[require_cron_secret()])
async def trigger(req: TriggerRequest):
    # Stub — real dispatch added in Tasks 11-14 once pipeline modules exist
    return {
        "stage": req.stage,
        "dry_run": req.dry_run,
        "limit": req.limit,
        "status": "accepted",
    }
```

- [ ] **Step 4: Wire router into `api/main.py`**

Modify `api/main.py` — add import and include_router:

```python
from api.routers import health, pipeline
# ...
app.include_router(health.router)
app.include_router(pipeline.router)
```

- [ ] **Step 5: Run tests — should pass**

```bash
uv run pytest tests/test_api/ -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add api/routers/pipeline.py api/main.py tests/test_api/test_pipeline_router.py
git commit -m "Add pipeline trigger endpoint stub"
```

---

## Task 9: Migrate pull.py into systems/scout/pipeline/

**Files:**
- Create: `systems/scout/pipeline/__init__.py`
- Create: `systems/scout/pipeline/pull.py`
- Test: `tests/test_pipeline/test_pull.py`
- Reference: `/home/kirsten/01_PERSONAL/10_PERSONAL_PROJECTS/base-camp-agents/scripts/pull_leads.py` (504 lines)

**Migration pattern for every pipeline stage:**

1. Read source file from base-camp-agents
2. Wrap the core work function in a class extending `BaseSystem`
3. Add `load_foundation()` call at start of `handle()`
4. Add `log_decision()` call after significant actions
5. Preserve core algorithm (Apollo search logic, scoring logic, etc.) verbatim
6. Drop the CLI argparse wrapper (orchestrated by API / scheduler instead)
7. Write tests with a mocked Supabase + httpx

- [ ] **Step 1: Read the source file to understand the algorithm**

Run:
```bash
cat /home/kirsten/01_PERSONAL/10_PERSONAL_PROJECTS/base-camp-agents/scripts/pull_leads.py | head -200
```

Key functions to preserve: `map_apollo_result()` (lines 47-80), `search_apollo()` (lines 85+).

- [ ] **Step 2: Write the failing test first**

Create `tests/test_pipeline/__init__.py` (empty) and `tests/test_pipeline/test_pull.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def fake_apollo_response():
    return {
        "people": [
            {
                "id": "apollo_123",
                "first_name": "Alex",
                "last_name": "Smith",
                "name": "Alex Smith",
                "title": "Fractional CFO",
                "organization": {
                    "name": "Acme Co",
                    "website_url": "https://acme.example",
                    "industry": "Consulting",
                    "num_employees": 12,
                },
                "country": "United States",
                "linkedin_url": "https://linkedin.com/in/alexsmith",
            }
        ],
        "pagination": {"total_entries": 1},
    }


@pytest.mark.asyncio
async def test_map_apollo_result_extracts_core_fields():
    from systems.scout.pipeline.pull import map_apollo_result

    person = {
        "id": "abc",
        "first_name": "Jane",
        "last_name": "Doe",
        "title": "CEO",
        "organization": {"name": "Acme", "website_url": "https://acme.com"},
        "linkedin_url": "https://linkedin.com/in/jane",
    }
    result = map_apollo_result(person)

    assert result["first_name"] == "Jane"
    assert result["last_name"] == "Doe"
    assert result["title"] == "CEO"
    assert result["company"] == "Acme"
    assert result["linkedin_url"] == "https://linkedin.com/in/jane"
    assert result["source_id"] == "abc"
    assert result["email"] == ""  # never populated by pull — enriched later


@pytest.mark.asyncio
async def test_pull_stage_logs_decision(fake_apollo_response):
    from systems.scout.pipeline.pull import PullStage

    # Mock the foundation dependencies
    memory = MagicMock()
    memory.load_full_context = AsyncMock(return_value={"business_context": [], "relevant_knowledge": []})
    decisions = MagicMock()
    decisions.log_decision = AsyncMock(return_value="decision-123")

    # Mock the Apollo HTTP client
    stage = PullStage(memory_store=memory, decision_logger=decisions)
    stage._apollo_search = AsyncMock(return_value=([fake_apollo_response["people"][0]], 1))
    stage._supabase_upsert = AsyncMock(return_value={"id": "contact-uuid"})

    result = await stage.run(
        client_id="test",
        icp_titles=["Fractional CFO"],
        max_contacts=1,
        dry_run=False,
    )

    assert result["inserted"] == 1
    assert result["seen"] == 1
    assert decisions.log_decision.called
    args = decisions.log_decision.call_args.kwargs
    assert args["decision_type"] == "pull_leads"
    assert args["client_id"] == "test"
```

- [ ] **Step 3: Run test — should fail**

```bash
uv run pytest tests/test_pipeline/test_pull.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'systems.scout.pipeline.pull'`.

- [ ] **Step 4: Create `systems/scout/pipeline/__init__.py`**

```bash
touch systems/scout/pipeline/__init__.py
```

- [ ] **Step 5: Create `systems/scout/pipeline/pull.py`**

```python
"""
Pull stage — fetch leads from Apollo People Search.

Migrated from base-camp-agents/scripts/pull_leads.py with BaseSystem conformance.
The Apollo free People Search returns name, title, company, linkedin. Email is NOT
fetched here (that's the enrichment stage, gated by ICP score).

Logs `pull_leads` decision per run.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from systems.base import BaseSystem, SystemResult

logger = logging.getLogger(__name__)

APOLLO_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_people/search"


def map_apollo_result(person: dict) -> dict:
    """
    Map Apollo People Search response → internal contact format.
    Preserved verbatim from base-camp-agents/scripts/pull_leads.py:47.
    """
    org = person.get("organization") or {}
    first = person.get("first_name") or ""
    last = person.get("last_name") or ""
    name = person.get("name") or f"{first} {last}".strip()

    employees_raw = (
        person.get("num_employees")
        or org.get("num_employees")
        or org.get("estimated_num_employees")
    )
    revenue_raw = org.get("annual_revenue")

    return {
        "source": "apollo",
        "source_id": person.get("id") or "",
        "name": name,
        "first_name": first,
        "last_name": last,
        "company": org.get("name") or person.get("organization_name") or "",
        "company_domain": (org.get("website_url") or "").replace("https://", "").replace("http://", "").strip("/"),
        "email": "",
        "email_verified": False,
        "email_catch_all": False,
        "title": person.get("title") or "",
        "industry": (org.get("industry") or person.get("industry") or "").lower(),
        "employees": int(employees_raw) if employees_raw else None,
        "revenue_usd": int(revenue_raw) if revenue_raw else None,
        "geography": person.get("country") or org.get("country") or "",
        "city": person.get("city") or "",
        "state": person.get("state") or "",
        "linkedin_url": person.get("linkedin_url") or "",
        "phone": "",
        "raw_data": person,
    }


class PullStage(BaseSystem):
    """Scout pipeline stage — pulls contacts from Apollo."""

    name = "scout_pull"
    display_name = "Scout — Pull Stage"
    description = "Pulls leads from Apollo and upserts to contacts table"
    enabled = True

    async def run(
        self,
        client_id: str,
        icp_titles: list[str],
        max_contacts: int = 50,
        niche: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Pull up to max_contacts and return {seen, inserted}."""
        # 1. MANDATORY — load foundation context
        await self.load_foundation(client_id, task_query=f"pull leads for titles={icp_titles}")

        # 2. Apollo search
        people, total = await self._apollo_search(icp_titles=icp_titles, max_contacts=max_contacts)

        inserted = 0
        for person in people:
            contact = map_apollo_result(person)
            contact["client_id"] = client_id
            if niche:
                contact["niche"] = niche
            if dry_run:
                logger.info("[dry-run] would upsert contact: %s", contact.get("name"))
                continue
            await self._supabase_upsert(contact)
            inserted += 1

        # 3. MANDATORY — log decision
        await self.log_decision(
            client_id=client_id,
            decision_type="pull_leads",
            context={"titles": icp_titles, "niche": niche, "max_contacts": max_contacts, "dry_run": dry_run},
            decision=f"pulled {inserted} contacts",
            reasoning=f"Apollo returned {total} total matches for titles={icp_titles}",
            confidence=1.0,
        )

        return {"seen": len(people), "inserted": inserted, "apollo_total": total}

    async def _apollo_search(
        self,
        icp_titles: list[str],
        max_contacts: int,
        per_page: int = 25,
    ) -> tuple[list[dict], int]:
        """Call Apollo search paginated. Returns (people_list, total_count)."""
        from config.settings import get_settings
        settings = get_settings()

        if not settings.apollo_api_key:
            raise RuntimeError("APOLLO_API_KEY not set")

        results: list[dict] = []
        total = 0
        page = 1

        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(results) < max_contacts:
                payload = {
                    "page": page,
                    "per_page": per_page,
                    "person_titles": icp_titles,
                }
                headers = {
                    "X-Api-Key": settings.apollo_api_key,
                    "Content-Type": "application/json",
                }
                resp = await client.post(APOLLO_SEARCH_URL, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                people = data.get("people", [])
                if not people:
                    break
                results.extend(people)
                total = data.get("pagination", {}).get("total_entries", total)
                page += 1

        return results[:max_contacts], total

    async def _supabase_upsert(self, contact: dict) -> dict:
        """Upsert contact into Supabase `contacts` table."""
        from supabase import acreate_client
        from config.settings import get_settings
        settings = get_settings()

        client = await acreate_client(settings.supabase_url, settings.supabase_service_role_key)
        resp = await client.table("contacts").upsert(
            contact,
            on_conflict="client_id,source,source_id",
        ).execute()
        return resp.data[0] if resp.data else {}

    async def handle(self, message, client_id, user_id, context=None):
        """BaseSystem handle — default entry point (unused for pipeline stages)."""
        return SystemResult(text="PullStage is a pipeline stage, not a chat handler")
```

- [ ] **Step 6: Run tests — should pass**

```bash
uv run pytest tests/test_pipeline/test_pull.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add systems/scout/pipeline/__init__.py systems/scout/pipeline/pull.py tests/test_pipeline/__init__.py tests/test_pipeline/test_pull.py
git commit -m "Migrate pull_leads to BaseSystem-conformant PullStage"
```

---

## Task 10: Migrate score.py

**Files:**
- Create: `systems/scout/pipeline/score.py`
- Create: `systems/scout/pipeline/icp.py` (scoring logic extracted from base-camp-agents/agent/skills/scout/icp.py)
- Test: `tests/test_pipeline/test_score.py`
- Reference: `base-camp-agents/scripts/score_contacts.py` (209 lines) + `base-camp-agents/agent/skills/scout/icp.py`

Scoring reads ICP definition from `icp_definitions` table (per niche) and scores each contact 0-100, assigning tier A/B/C/D.

- [ ] **Step 1: Write failing test**

Create `tests/test_pipeline/test_score.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_score_contact_returns_tier():
    from systems.scout.pipeline.score import score_contact

    icp = {
        "industries": ["consulting", "fractional"],
        "titles": ["CFO", "Fractional CFO"],
        "employee_min": 5,
        "employee_max": 50,
        "weights": {},
    }
    contact = {
        "industry": "consulting",
        "title": "Fractional CFO",
        "employees": 12,
        "revenue_usd": None,
        "geography": "United States",
    }
    score, tier, signals = score_contact(contact, icp)

    assert 0 <= score <= 100
    assert tier in ("A", "B", "C", "D")
    assert score >= 60  # strong match
    assert tier in ("A", "B")


@pytest.mark.asyncio
async def test_score_stage_updates_contacts_and_logs_decisions():
    from systems.scout.pipeline.score import ScoreStage

    memory = MagicMock()
    memory.load_full_context = AsyncMock(return_value={"business_context": [], "relevant_knowledge": []})
    decisions = MagicMock()
    decisions.log_decision = AsyncMock(return_value="decision-id")

    stage = ScoreStage(memory_store=memory, decision_logger=decisions)
    stage._fetch_unscored_contacts = AsyncMock(return_value=[
        {"id": "c1", "industry": "consulting", "title": "CFO", "employees": 20, "geography": "US"},
    ])
    stage._fetch_icp = AsyncMock(return_value={
        "industries": ["consulting"],
        "titles": ["CFO"],
        "employee_min": 5,
        "employee_max": 50,
        "weights": {},
    })
    stage._update_contact_score = AsyncMock()

    result = await stage.run(client_id="test", niche="fractional", dry_run=False, limit=10)

    assert result["scored"] == 1
    assert decisions.log_decision.called
```

- [ ] **Step 2: Run test — fail**

```bash
uv run pytest tests/test_pipeline/test_score.py -v
```

Expected: FAIL.

- [ ] **Step 3: Create `systems/scout/pipeline/score.py`**

```python
"""
Score stage — assign ICP score (0-100) + tier (A/B/C/D) to contacts.

Migrated from base-camp-agents/scripts/score_contacts.py + agent/skills/scout/icp.py.
Reads ICP definition from icp_definitions table by (client_id, niche).
"""
from __future__ import annotations

import logging
from typing import Any

from systems.base import BaseSystem, SystemResult

logger = logging.getLogger(__name__)

TIER_THRESHOLDS = {"A": 80, "B": 60, "C": 40}  # D is below 40


def score_contact(contact: dict, icp: dict) -> tuple[int, str, list[str]]:
    """
    Score a contact against an ICP definition. Returns (score 0-100, tier, signals).

    Scoring (base 0, additive):
    + 30 if industry in icp.industries
    + 30 if title matches any icp.titles (case-insensitive substring)
    + 20 if employees within icp.employee_min..employee_max
    + 10 if revenue within icp.revenue_min_usd..revenue_max_usd
    + 10 if geography matches any icp.geographies

    Apply per-signal weight multipliers from icp.weights if present.
    """
    score = 0
    signals: list[str] = []
    weights = icp.get("weights") or {}

    # Industry match
    contact_industry = (contact.get("industry") or "").lower()
    icp_industries = [i.lower() for i in (icp.get("industries") or [])]
    if icp_industries and any(ind in contact_industry for ind in icp_industries):
        w = weights.get("industry", 1.0)
        score += int(30 * w)
        signals.append(f"industry:{contact_industry}")

    # Title match
    contact_title = (contact.get("title") or "").lower()
    icp_titles = [t.lower() for t in (icp.get("titles") or [])]
    if icp_titles and any(t in contact_title for t in icp_titles):
        w = weights.get("title", 1.0)
        score += int(30 * w)
        signals.append(f"title:{contact_title}")

    # Employee band
    emp = contact.get("employees")
    emp_min = icp.get("employee_min")
    emp_max = icp.get("employee_max")
    if emp is not None and emp_min is not None and emp_max is not None:
        if emp_min <= emp <= emp_max:
            w = weights.get("employees", 1.0)
            score += int(20 * w)
            signals.append(f"employees:{emp}")

    # Revenue band
    rev = contact.get("revenue_usd")
    rev_min = icp.get("revenue_min_usd")
    rev_max = icp.get("revenue_max_usd")
    if rev is not None and rev_min is not None and rev_max is not None:
        if rev_min <= rev <= rev_max:
            w = weights.get("revenue", 1.0)
            score += int(10 * w)
            signals.append(f"revenue:{rev}")

    # Geography
    geo = (contact.get("geography") or "").lower()
    icp_geos = [g.lower() for g in (icp.get("geographies") or [])]
    if icp_geos and any(g in geo for g in icp_geos):
        w = weights.get("geography", 1.0)
        score += int(10 * w)
        signals.append(f"geography:{geo}")

    score = min(score, 100)
    if score >= TIER_THRESHOLDS["A"]:
        tier = "A"
    elif score >= TIER_THRESHOLDS["B"]:
        tier = "B"
    elif score >= TIER_THRESHOLDS["C"]:
        tier = "C"
    else:
        tier = "D"

    return score, tier, signals


class ScoreStage(BaseSystem):
    name = "scout_score"
    display_name = "Scout — Score Stage"
    description = "Assigns ICP score + tier to unscored contacts"
    enabled = True

    async def run(
        self,
        client_id: str,
        niche: str,
        limit: int = 500,
        rescore: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        await self.load_foundation(client_id, task_query=f"score contacts for niche={niche}")

        icp = await self._fetch_icp(client_id, niche)
        if not icp:
            raise RuntimeError(f"No ICP defined for client={client_id} niche={niche}")

        contacts = await self._fetch_unscored_contacts(client_id, niche, limit, rescore)

        scored = 0
        tier_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
        for c in contacts:
            score, tier, signals = score_contact(c, icp)
            tier_counts[tier] += 1
            if dry_run:
                logger.info("[dry-run] %s %s -> %d %s (%s)", c.get("name"), c.get("title"), score, tier, signals)
                continue
            await self._update_contact_score(c["id"], score, tier, signals)
            scored += 1

        await self.log_decision(
            client_id=client_id,
            decision_type="score_contacts",
            context={"niche": niche, "limit": limit, "rescore": rescore},
            decision=f"scored {scored} contacts",
            reasoning=f"tier distribution: A={tier_counts['A']} B={tier_counts['B']} C={tier_counts['C']} D={tier_counts['D']}",
            confidence=1.0,
        )

        return {"scored": scored, "tier_counts": tier_counts}

    async def _fetch_icp(self, client_id: str, niche: str) -> dict | None:
        from supabase import acreate_client
        from config.settings import get_settings
        s = get_settings()
        client = await acreate_client(s.supabase_url, s.supabase_service_role_key)
        resp = await client.table("icp_definitions").select("*").eq("client_id", client_id).eq("niche", niche).execute()
        return resp.data[0] if resp.data else None

    async def _fetch_unscored_contacts(
        self, client_id: str, niche: str, limit: int, rescore: bool
    ) -> list[dict]:
        from supabase import acreate_client
        from config.settings import get_settings
        s = get_settings()
        client = await acreate_client(s.supabase_url, s.supabase_service_role_key)
        q = client.table("contacts").select("*").eq("client_id", client_id).eq("niche", niche)
        if not rescore:
            q = q.is_("icp_score", "null")
        q = q.limit(limit)
        resp = await q.execute()
        return resp.data or []

    async def _update_contact_score(self, contact_id: str, score: int, tier: str, signals: list[str]) -> None:
        from supabase import acreate_client
        from config.settings import get_settings
        s = get_settings()
        client = await acreate_client(s.supabase_url, s.supabase_service_role_key)
        await client.table("contacts").update({
            "icp_score": score,
            "icp_tier": tier,
            "raw_data": {"scoring_signals": signals},
            "status": "screened",
        }).eq("id", contact_id).execute()

    async def handle(self, message, client_id, user_id, context=None):
        return SystemResult(text="ScoreStage is a pipeline stage, not a chat handler")
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_pipeline/test_score.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add systems/scout/pipeline/score.py tests/test_pipeline/test_score.py
git commit -m "Migrate score_contacts to BaseSystem-conformant ScoreStage"
```

---

## Task 11: Migrate screen.py

**Files:**
- Create: `systems/scout/pipeline/screen.py`
- Test: `tests/test_pipeline/test_screen.py`
- Reference: `base-camp-agents/scripts/screen_contacts.py` (323 lines)

Screening applies rule-based filters (blacklist, hard ICP mismatches) BEFORE enrichment so we don't spend money on disqualified contacts.

- [ ] **Step 1: Write failing test**

Create `tests/test_pipeline/test_screen.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_screen_rejects_blacklisted_company():
    from systems.scout.pipeline.screen import screen_contact

    icp = {
        "blacklist_companies": ["Bad Corp"],
        "blacklist_domains": ["spam.example"],
    }
    contact = {"company": "Bad Corp", "company_domain": "badcorp.com"}
    passed, reason = screen_contact(contact, icp)
    assert passed is False
    assert "blacklist" in reason.lower()


@pytest.mark.asyncio
async def test_screen_rejects_blacklisted_domain():
    from systems.scout.pipeline.screen import screen_contact

    icp = {"blacklist_companies": [], "blacklist_domains": ["spam.example"]}
    contact = {"company": "Legit Co", "company_domain": "spam.example"}
    passed, reason = screen_contact(contact, icp)
    assert passed is False
    assert "domain" in reason.lower()


@pytest.mark.asyncio
async def test_screen_rejects_d_tier():
    from systems.scout.pipeline.screen import screen_contact

    icp = {"blacklist_companies": [], "blacklist_domains": []}
    contact = {"company": "X", "company_domain": "x.com", "icp_tier": "D"}
    passed, reason = screen_contact(contact, icp)
    assert passed is False
    assert "tier" in reason.lower()


@pytest.mark.asyncio
async def test_screen_accepts_abc_tier_non_blacklisted():
    from systems.scout.pipeline.screen import screen_contact

    icp = {"blacklist_companies": [], "blacklist_domains": []}
    contact = {"company": "Good Co", "company_domain": "good.com", "icp_tier": "B"}
    passed, reason = screen_contact(contact, icp)
    assert passed is True
```

- [ ] **Step 2: Run — fail**

```bash
uv run pytest tests/test_pipeline/test_screen.py -v
```

- [ ] **Step 3: Create `systems/scout/pipeline/screen.py`**

```python
"""
Screen stage — rule-based filter BEFORE enrichment.

Rejects:
- Blacklisted companies (icp.blacklist_companies)
- Blacklisted domains (icp.blacklist_domains)
- D-tier contacts (score < 40)
- Contacts missing required fields (name, company)

Migrated from base-camp-agents/scripts/screen_contacts.py.
"""
from __future__ import annotations

import logging
from typing import Any

from systems.base import BaseSystem, SystemResult

logger = logging.getLogger(__name__)


def screen_contact(contact: dict, icp: dict) -> tuple[bool, str]:
    """Return (passed, reason_if_rejected)."""
    company = (contact.get("company") or "").strip()
    domain = (contact.get("company_domain") or "").strip().lower()
    name = (contact.get("name") or "").strip()
    tier = contact.get("icp_tier")

    if not name:
        return False, "missing name"
    if not company:
        return False, "missing company"

    blacklist_companies = {c.lower() for c in (icp.get("blacklist_companies") or [])}
    if company.lower() in blacklist_companies:
        return False, f"company blacklisted: {company}"

    blacklist_domains = {d.lower() for d in (icp.get("blacklist_domains") or [])}
    if domain and domain in blacklist_domains:
        return False, f"domain blacklisted: {domain}"

    if tier == "D":
        return False, "tier D (below threshold)"

    return True, ""


class ScreenStage(BaseSystem):
    name = "scout_screen"
    display_name = "Scout — Screen Stage"
    description = "Filters contacts by blacklists + tier before enrichment"
    enabled = True

    async def run(
        self,
        client_id: str,
        niche: str,
        limit: int = 500,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        await self.load_foundation(client_id, task_query=f"screen contacts niche={niche}")

        icp = await self._fetch_icp(client_id, niche)
        if not icp:
            raise RuntimeError(f"No ICP for {client_id}/{niche}")

        contacts = await self._fetch_screened_candidates(client_id, niche, limit)

        passed_count = 0
        rejected = {"blacklist": 0, "tier": 0, "missing_field": 0, "other": 0}

        for c in contacts:
            passed, reason = screen_contact(c, icp)
            if passed:
                if not dry_run:
                    await self._mark_screened(c["id"], passed=True, reason="")
                passed_count += 1
            else:
                if "blacklist" in reason:
                    rejected["blacklist"] += 1
                elif "tier" in reason:
                    rejected["tier"] += 1
                elif "missing" in reason:
                    rejected["missing_field"] += 1
                else:
                    rejected["other"] += 1
                if not dry_run:
                    await self._mark_screened(c["id"], passed=False, reason=reason)

        await self.log_decision(
            client_id=client_id,
            decision_type="screen_contacts",
            context={"niche": niche, "limit": limit},
            decision=f"{passed_count} passed, {sum(rejected.values())} rejected",
            reasoning=f"rejections by reason: {rejected}",
            confidence=1.0,
        )

        return {"passed": passed_count, "rejected": rejected, "total": len(contacts)}

    async def _fetch_icp(self, client_id: str, niche: str) -> dict | None:
        from supabase import acreate_client
        from config.settings import get_settings
        s = get_settings()
        client = await acreate_client(s.supabase_url, s.supabase_service_role_key)
        resp = await client.table("icp_definitions").select("*").eq("client_id", client_id).eq("niche", niche).execute()
        return resp.data[0] if resp.data else None

    async def _fetch_screened_candidates(self, client_id: str, niche: str, limit: int) -> list[dict]:
        from supabase import acreate_client
        from config.settings import get_settings
        s = get_settings()
        client = await acreate_client(s.supabase_url, s.supabase_service_role_key)
        resp = await (
            client.table("contacts")
            .select("*")
            .eq("client_id", client_id)
            .eq("niche", niche)
            .eq("status", "screened")
            .limit(limit)
            .execute()
        )
        return resp.data or []

    async def _mark_screened(self, contact_id: str, passed: bool, reason: str) -> None:
        from supabase import acreate_client
        from config.settings import get_settings
        s = get_settings()
        client = await acreate_client(s.supabase_url, s.supabase_service_role_key)
        status = "enriched" if passed else "dead"  # dead rejects won't be enriched
        await client.table("contacts").update({
            "status": status,
            "screened_at": "now()",
            "raw_data": {"screen_reason": reason} if reason else {},
        }).eq("id", contact_id).execute()

    async def handle(self, message, client_id, user_id, context=None):
        return SystemResult(text="ScreenStage is a pipeline stage, not a chat handler")
```

- [ ] **Step 4: Run tests — pass**

```bash
uv run pytest tests/test_pipeline/test_screen.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add systems/scout/pipeline/screen.py tests/test_pipeline/test_screen.py
git commit -m "Migrate screen_contacts to BaseSystem-conformant ScreenStage"
```

---

## Task 12: Migrate enrich.py (merged with verify_emails.py)

**Files:**
- Create: `systems/scout/pipeline/enrich.py`
- Test: `tests/test_pipeline/test_enrich.py`
- Reference: `base-camp-agents/scripts/enrich_contacts.py` (1549 lines) + `verify_emails.py` (524 lines)

Enrichment is the biggest migration (2,073 total lines of source). It calls Anymail Finder (email finding) + ZeroBounce (verification). Cost gate (Plan 4) will wrap this later; for Plan 1 we add a budget-check stub that always passes but logs the would-be cost.

- [ ] **Step 1: Write failing test**

Create `tests/test_pipeline/test_enrich.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def sample_contact():
    return {
        "id": "c1",
        "client_id": "test",
        "name": "Jane Doe",
        "first_name": "Jane",
        "last_name": "Doe",
        "company": "Acme Co",
        "company_domain": "acme.com",
        "icp_tier": "A",
        "status": "enriched",
    }


@pytest.mark.asyncio
async def test_enrich_finds_email_and_verifies(sample_contact):
    from systems.scout.pipeline.enrich import EnrichStage

    memory = MagicMock()
    memory.load_full_context = AsyncMock(return_value={"business_context": [], "relevant_knowledge": []})
    decisions = MagicMock()
    decisions.log_decision = AsyncMock(return_value="d1")

    stage = EnrichStage(memory_store=memory, decision_logger=decisions)
    stage._fetch_candidates = AsyncMock(return_value=[sample_contact])
    stage._anymail_finder = AsyncMock(return_value={"email": "jane@acme.com", "cost_cents": 3})
    stage._zerobounce_verify = AsyncMock(return_value={"result": "valid", "catch_all": False, "cost_cents": 1})
    stage._update_contact_enrichment = AsyncMock()

    result = await stage.run(client_id="test", niche="fractional", limit=5, dry_run=False)

    assert result["enriched"] == 1
    assert result["valid_emails"] == 1
    assert decisions.log_decision.called


@pytest.mark.asyncio
async def test_enrich_skips_invalid_emails(sample_contact):
    from systems.scout.pipeline.enrich import EnrichStage

    memory = MagicMock()
    memory.load_full_context = AsyncMock(return_value={})
    decisions = MagicMock()
    decisions.log_decision = AsyncMock(return_value="d1")

    stage = EnrichStage(memory_store=memory, decision_logger=decisions)
    stage._fetch_candidates = AsyncMock(return_value=[sample_contact])
    stage._anymail_finder = AsyncMock(return_value={"email": "jane@acme.com", "cost_cents": 3})
    stage._zerobounce_verify = AsyncMock(return_value={"result": "invalid", "catch_all": False, "cost_cents": 1})
    stage._update_contact_enrichment = AsyncMock()

    result = await stage.run(client_id="test", niche="fractional", limit=5, dry_run=False)

    assert result["enriched"] == 1
    assert result["valid_emails"] == 0
    assert result["invalid_emails"] == 1
```

- [ ] **Step 2: Run — fail**

```bash
uv run pytest tests/test_pipeline/test_enrich.py -v
```

- [ ] **Step 3: Create `systems/scout/pipeline/enrich.py`**

```python
"""
Enrich stage — find + verify contact email via Anymail Finder + ZeroBounce.

Migrated + merged from base-camp-agents/scripts/enrich_contacts.py and verify_emails.py.
Only runs on contacts in status='enriched' (which confusingly means "passed screen,
awaiting enrichment" in the base-camp pipeline naming — status transitions to
'ready' after verification).

Plan 1: cost gate is a stub (logs cost, doesn't block).
Plan 4: cost gate becomes real — aborts if over budget.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from systems.base import BaseSystem, SystemResult

logger = logging.getLogger(__name__)

ANYMAIL_FINDER_URL = "https://api.anymailfinder.com/v5.0/search/person.json"
ZEROBOUNCE_URL = "https://api.zerobounce.net/v2/validate"


class EnrichStage(BaseSystem):
    name = "scout_enrich"
    display_name = "Scout — Enrich Stage"
    description = "Finds + verifies contact emails"
    enabled = True

    async def run(
        self,
        client_id: str,
        niche: str,
        limit: int = 100,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        await self.load_foundation(client_id, task_query=f"enrich contacts niche={niche}")

        contacts = await self._fetch_candidates(client_id, niche, limit)
        enriched = 0
        valid_emails = 0
        invalid_emails = 0
        total_cost_cents = 0

        for c in contacts:
            if dry_run:
                logger.info("[dry-run] would enrich %s @ %s", c.get("name"), c.get("company"))
                enriched += 1
                continue

            # Budget stub (Plan 4 makes this real)
            await self._check_budget_stub(client_id, contact_id=c["id"])

            find_result = await self._anymail_finder(c)
            total_cost_cents += find_result.get("cost_cents", 0)
            email = find_result.get("email", "")

            if not email:
                await self._update_contact_enrichment(c["id"], email="", verified=False, valid=False)
                enriched += 1
                continue

            verify_result = await self._zerobounce_verify(email)
            total_cost_cents += verify_result.get("cost_cents", 0)
            valid = verify_result.get("result") == "valid"

            await self._update_contact_enrichment(
                c["id"],
                email=email,
                verified=valid,
                valid=valid,
                catch_all=verify_result.get("catch_all", False),
            )

            if valid:
                valid_emails += 1
            else:
                invalid_emails += 1
            enriched += 1

        await self.log_decision(
            client_id=client_id,
            decision_type="enrich_contacts",
            context={"niche": niche, "limit": limit, "cost_cents": total_cost_cents},
            decision=f"enriched {enriched} ({valid_emails} valid, {invalid_emails} invalid)",
            reasoning=f"total cost: {total_cost_cents} cents",
            confidence=1.0,
        )

        return {
            "enriched": enriched,
            "valid_emails": valid_emails,
            "invalid_emails": invalid_emails,
            "total_cost_cents": total_cost_cents,
        }

    async def _check_budget_stub(self, client_id: str, contact_id: str) -> None:
        # Plan 4 replaces this with real `check_budget(client_id, "enrichment", est_cost, contact_id)`
        logger.debug("budget stub: would check enrichment budget for %s/%s", client_id, contact_id)

    async def _fetch_candidates(self, client_id: str, niche: str, limit: int) -> list[dict]:
        from supabase import acreate_client
        from config.settings import get_settings
        s = get_settings()
        client = await acreate_client(s.supabase_url, s.supabase_service_role_key)
        resp = await (
            client.table("contacts")
            .select("*")
            .eq("client_id", client_id)
            .eq("niche", niche)
            .eq("status", "enriched")
            .is_("email", "null")
            .limit(limit)
            .execute()
        )
        return resp.data or []

    async def _anymail_finder(self, contact: dict) -> dict:
        from config.settings import get_settings
        s = get_settings()
        if not s.anymail_finder_api_key:
            return {"email": "", "cost_cents": 0}

        payload = {
            "domain": contact.get("company_domain", ""),
            "first_name": contact.get("first_name", ""),
            "last_name": contact.get("last_name", ""),
        }
        headers = {"Authorization": f"Bearer {s.anymail_finder_api_key}"}
        try:
            async with httpx.AsyncClient(timeout=30.0) as c:
                resp = await c.post(ANYMAIL_FINDER_URL, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return {
                    "email": data.get("results", {}).get("email", ""),
                    "cost_cents": 3,  # approximate; Anymail Finder costs per verify
                }
        except Exception as e:
            logger.warning("Anymail Finder failed for %s: %s", contact.get("name"), e)
            return {"email": "", "cost_cents": 0}

    async def _zerobounce_verify(self, email: str) -> dict:
        from config.settings import get_settings
        s = get_settings()
        if not s.zerobounce_api_key:
            return {"result": "unknown", "catch_all": False, "cost_cents": 0}

        params = {"api_key": s.zerobounce_api_key, "email": email}
        try:
            async with httpx.AsyncClient(timeout=30.0) as c:
                resp = await c.get(ZEROBOUNCE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                return {
                    "result": data.get("status", "unknown"),
                    "catch_all": data.get("sub_status") == "catch_all",
                    "cost_cents": 1,  # ~$0.008/verify, round up
                }
        except Exception as e:
            logger.warning("ZeroBounce failed for %s: %s", email, e)
            return {"result": "unknown", "catch_all": False, "cost_cents": 0}

    async def _update_contact_enrichment(
        self, contact_id: str, email: str, verified: bool, valid: bool, catch_all: bool = False
    ) -> None:
        from supabase import acreate_client
        from config.settings import get_settings
        s = get_settings()
        client = await acreate_client(s.supabase_url, s.supabase_service_role_key)
        new_status = "ready" if valid else "dead"
        await client.table("contacts").update({
            "email": email or None,
            "email_verified": verified,
            "email_catch_all": catch_all,
            "status": new_status,
            "enriched_at": "now()",
        }).eq("id", contact_id).execute()

    async def handle(self, message, client_id, user_id, context=None):
        return SystemResult(text="EnrichStage is a pipeline stage, not a chat handler")
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_pipeline/test_enrich.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add systems/scout/pipeline/enrich.py tests/test_pipeline/test_enrich.py
git commit -m "Migrate enrich+verify into BaseSystem-conformant EnrichStage"
```

---

## Task 13: Template storage — file format + loader

**Files:**
- Create: `systems/scout/outreach/__init__.py`
- Create: `systems/scout/outreach/templates/_schema.md`
- Create: `systems/scout/outreach/template_store.py`
- Test: `tests/test_outreach/test_template_store.py`

Templates live as markdown + YAML frontmatter files on disk. Loader syncs them to the `templates` table on deploy / on change.

- [ ] **Step 1: Write template schema spec**

Create `systems/scout/outreach/templates/_schema.md`:

````markdown
# Template file format

Every template lives as `{template_key}_v{version}.md`:

```
---
template_key: agencyos_offer_a
version: 1
niche: agencies
offer_label: "A — pipeline pain"
status: draft
subject: "quick question about {{company}} pipeline"
placeholders:
  - name: first_name_casual
    type: name_casualisation
    required: true
  - name: icebreaker
    type: icebreaker_research
    required: true
    sources: [linkedin_post, company_news]
  - name: bridge
    type: bridge_rendering
    required: true
  - name: cta
    type: cta_selection
    required: true
    variants: [quick_15, loom]
offer_score:
  "1_clear_moat": null
  "2_recession_resilient": null
  # ... all 27 constraints, filled at approval time
---

Hey {{first_name_casual}},

{{icebreaker}}

{{bridge}}

Short version: we install AgencyOS — a system that fills your pipeline, manages operations, and builds your authority. On autopilot.

{{cta}}

— Kirsten
```

All templates must be approved (status: `approved`) before being loaded into rotation.
````

- [ ] **Step 2: Write failing test**

Create `tests/test_outreach/__init__.py` (empty) and `tests/test_outreach/test_template_store.py`:

```python
import pytest
from pathlib import Path


@pytest.fixture
def sample_template(tmp_path):
    content = """---
template_key: test_offer_a
version: 1
niche: test_niche
offer_label: "Test offer A"
status: approved
subject: "hello {{first_name_casual}}"
placeholders:
  - name: first_name_casual
    type: name_casualisation
    required: true
  - name: icebreaker
    type: icebreaker_research
    required: true
---

Hey {{first_name_casual}},

{{icebreaker}}

— Kirsten
"""
    f = tmp_path / "test_offer_a_v1.md"
    f.write_text(content)
    return f


def test_parse_template_file(sample_template):
    from systems.scout.outreach.template_store import parse_template_file

    meta, body = parse_template_file(sample_template)

    assert meta["template_key"] == "test_offer_a"
    assert meta["version"] == 1
    assert meta["niche"] == "test_niche"
    assert meta["status"] == "approved"
    assert "{{first_name_casual}}" in body
    assert len(meta["placeholders"]) == 2


def test_extract_placeholder_names_from_body():
    from systems.scout.outreach.template_store import extract_placeholder_names

    body = "Hey {{first_name_casual}},\n\n{{icebreaker}}\n\n{{bridge}}\n\n{{cta}}"
    names = extract_placeholder_names(body)
    assert set(names) == {"first_name_casual", "icebreaker", "bridge", "cta"}


def test_validate_template_declared_matches_body(sample_template):
    from systems.scout.outreach.template_store import parse_template_file, validate_template

    meta, body = parse_template_file(sample_template)
    issues = validate_template(meta, body)
    # The test fixture declares 2 placeholders and uses both — no issues
    assert issues == []


def test_validate_template_detects_missing_declaration():
    from systems.scout.outreach.template_store import validate_template

    meta = {
        "template_key": "t",
        "version": 1,
        "niche": "n",
        "offer_label": "x",
        "placeholders": [{"name": "first_name_casual", "type": "name_casualisation", "required": True}],
    }
    body = "Hey {{first_name_casual}}, {{undeclared_one}}"
    issues = validate_template(meta, body)
    assert any("undeclared_one" in i for i in issues)
```

- [ ] **Step 3: Run test — fail**

```bash
uv run pytest tests/test_outreach/test_template_store.py -v
```

- [ ] **Step 4: Create `systems/scout/outreach/__init__.py` (empty)**

```bash
mkdir -p systems/scout/outreach/templates
touch systems/scout/outreach/__init__.py
```

- [ ] **Step 5: Create `systems/scout/outreach/template_store.py`**

```python
"""
Template loader + validator.

Templates live as markdown files with YAML frontmatter under
systems/scout/outreach/templates/. This module:
- parses template files
- validates placeholder declarations against body usage
- syncs approved templates to the `templates` table
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)", re.DOTALL)


def parse_template_file(path: Path) -> tuple[dict, str]:
    """Parse a template markdown file into (metadata, body)."""
    text = path.read_text()
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(f"{path} missing YAML frontmatter")
    meta = yaml.safe_load(m.group(1)) or {}
    body = m.group(2).strip()
    return meta, body


def extract_placeholder_names(body: str) -> set[str]:
    """Find all {{placeholder}} names in template body."""
    return set(PLACEHOLDER_RE.findall(body))


def validate_template(meta: dict, body: str) -> list[str]:
    """Check template consistency. Returns list of issues (empty = valid)."""
    issues: list[str] = []

    for req in ("template_key", "version", "niche", "offer_label"):
        if req not in meta:
            issues.append(f"missing required metadata field: {req}")

    declared = {p["name"] for p in (meta.get("placeholders") or [])}
    used = extract_placeholder_names(body)

    for name in used - declared:
        issues.append(f"placeholder used in body but not declared: {name}")
    for name in declared - used:
        issues.append(f"placeholder declared but not used in body: {name}")

    return issues


def load_templates_from_directory(dir_path: Path) -> list[dict]:
    """Scan directory for template files and return parsed + validated list."""
    templates: list[dict] = []
    for f in sorted(dir_path.glob("*.md")):
        if f.name.startswith("_"):
            continue  # skip _schema.md etc.
        meta, body = parse_template_file(f)
        issues = validate_template(meta, body)
        if issues:
            raise ValueError(f"Template {f.name} invalid: {issues}")
        templates.append({"meta": meta, "body": body, "source_path": str(f)})
    return templates


async def sync_templates_to_db(
    client_id: str,
    templates: list[dict],
    supabase_url: str,
    supabase_key: str,
) -> dict:
    """Upsert approved templates into the `templates` table."""
    from supabase import acreate_client
    client = await acreate_client(supabase_url, supabase_key)

    inserted = 0
    for t in templates:
        m = t["meta"]
        if m.get("status") != "approved":
            continue
        row = {
            "client_id": client_id,
            "template_key": m["template_key"],
            "version": m["version"],
            "niche": m["niche"],
            "offer_label": m["offer_label"],
            "status": m["status"],
            "body": t["body"],
            "placeholders": m.get("placeholders", []),
            "metadata": {"source_path": t["source_path"], "subject": m.get("subject")},
            "offer_score": m.get("offer_score", {}),
            "approved_by": m.get("approved_by"),
            "approved_at": m.get("approved_at"),
        }
        await client.table("templates").upsert(
            row,
            on_conflict="client_id,template_key,version",
        ).execute()
        inserted += 1

    return {"synced": inserted}
```

- [ ] **Step 6: Run tests — pass**

```bash
uv run pytest tests/test_outreach/test_template_store.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add systems/scout/outreach/__init__.py systems/scout/outreach/template_store.py systems/scout/outreach/templates/_schema.md tests/test_outreach/__init__.py tests/test_outreach/test_template_store.py
git commit -m "Add template store: parse, validate, sync to DB"
```

---

## Task 14: Research module — per-contact placeholder research

**Files:**
- Create: `systems/scout/outreach/research.py`
- Test: `tests/test_outreach/test_research.py`

Research takes a contact + list of required placeholder types and produces filled values with source URLs. Uses Haiku (cheap, structured output).

- [ ] **Step 1: Write failing test**

Create `tests/test_outreach/test_research.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def sample_contact():
    return {
        "id": "c1",
        "first_name": "Alexander",
        "last_name": "Smith",
        "name": "Alexander Smith",
        "title": "Fractional CFO",
        "company": "Acme Co",
        "company_domain": "acme.com",
        "linkedin_url": "https://linkedin.com/in/alexsmith",
    }


@pytest.mark.asyncio
async def test_casualise_name_handles_common_cases():
    from systems.scout.outreach.research import casualise_name

    assert casualise_name("Alexander") == "Alex"
    assert casualise_name("Michael") == "Mike"
    assert casualise_name("Jennifer") == "Jen"
    # Default: keep as-is for unknown names
    assert casualise_name("Priya") == "Priya"
    assert casualise_name("") == ""


@pytest.mark.asyncio
async def test_research_fills_name_casualisation(sample_contact):
    from systems.scout.outreach.research import ResearchModule

    memory = MagicMock()
    memory.load_full_context = AsyncMock(return_value={})
    decisions = MagicMock()
    decisions.log_decision = AsyncMock(return_value="d1")

    mod = ResearchModule(memory_store=memory, decision_logger=decisions)
    mod._fetch_icebreaker_signal = AsyncMock(return_value={"value": "skipped — Plan 1 stub", "sources": []})

    placeholders_required = [
        {"name": "first_name_casual", "type": "name_casualisation"},
        {"name": "icebreaker", "type": "icebreaker_research", "sources": ["linkedin_post"]},
        {"name": "bridge", "type": "bridge_rendering"},
        {"name": "cta", "type": "cta_selection", "variants": ["quick_15", "loom"]},
    ]
    result = await mod.research_contact(
        client_id="test",
        contact=sample_contact,
        required_placeholders=placeholders_required,
    )

    assert result["fills"]["first_name_casual"] == "Alex"
    assert "icebreaker" in result["fills"]
    assert "bridge" in result["fills"]
    assert "cta" in result["fills"]
    assert decisions.log_decision.called
```

- [ ] **Step 2: Run — fail**

```bash
uv run pytest tests/test_outreach/test_research.py -v
```

- [ ] **Step 3: Create `systems/scout/outreach/research.py`**

```python
"""
Research module — fills template placeholders per contact.

For Plan 1, only two placeholder types are fully implemented:
- name_casualisation: rule-based common-name mapping
- cta_selection: rule-based pick from variants

Stubs for icebreaker_research and bridge_rendering return placeholder text —
full LLM-powered versions land with Plan 2 (QA agent + research context).

All fills carry a `sources` list for QA factuality checks later.
"""
from __future__ import annotations

import logging
from typing import Any

from systems.base import BaseSystem, SystemResult

logger = logging.getLogger(__name__)

# Rule-based name casualisation table
CASUAL_NAMES = {
    "alexander": "Alex",
    "alexandra": "Alex",
    "michael": "Mike",
    "mikhail": "Mike",
    "jennifer": "Jen",
    "jennie": "Jen",
    "elizabeth": "Liz",
    "william": "Will",
    "richard": "Rich",
    "robert": "Rob",
    "james": "Jim",
    "christopher": "Chris",
    "katherine": "Kate",
    "kathryn": "Kate",
    "patricia": "Pat",
    "patrick": "Pat",
    "daniel": "Dan",
    "thomas": "Tom",
    "matthew": "Matt",
    "nicholas": "Nick",
    "anthony": "Tony",
    "jonathan": "Jon",
    "benjamin": "Ben",
    "samantha": "Sam",
    "samuel": "Sam",
    "david": "Dave",
    "rebecca": "Becca",
    "stephanie": "Steph",
}


def casualise_name(first_name: str) -> str:
    """Map formal first name → casual form. Falls back to the original name."""
    if not first_name:
        return ""
    key = first_name.strip().lower()
    return CASUAL_NAMES.get(key, first_name)


class ResearchModule(BaseSystem):
    name = "scout_research"
    display_name = "Scout — Research Module"
    description = "Fills template placeholders per contact"
    enabled = True

    async def research_contact(
        self,
        client_id: str,
        contact: dict,
        required_placeholders: list[dict],
    ) -> dict[str, Any]:
        """Return {fills: {name: value}, sources: {name: [urls]}}."""
        await self.load_foundation(client_id, task_query=f"research contact {contact.get('name')}")

        fills: dict[str, str] = {}
        sources: dict[str, list[str]] = {}

        for p in required_placeholders:
            ptype = p.get("type")
            name = p["name"]

            if ptype == "name_casualisation":
                fills[name] = casualise_name(contact.get("first_name", ""))
                sources[name] = []
            elif ptype == "icebreaker_research":
                res = await self._fetch_icebreaker_signal(contact, p.get("sources", []))
                fills[name] = res.get("value", "")
                sources[name] = res.get("sources", [])
            elif ptype == "bridge_rendering":
                # Plan 2 upgrades this to LLM-driven. Plan 1 stub: generic bridge.
                fills[name] = "That's basically what we help with."
                sources[name] = []
            elif ptype == "cta_selection":
                variants = p.get("variants") or ["quick_15"]
                # Plan 1 stub: deterministic pick (first variant)
                fills[name] = self._render_cta(variants[0])
                sources[name] = []
            else:
                logger.warning("unknown placeholder type: %s", ptype)
                fills[name] = ""
                sources[name] = []

        await self.log_decision(
            client_id=client_id,
            decision_type="research_contact",
            context={"contact_id": contact.get("id"), "placeholders": [p["name"] for p in required_placeholders]},
            decision=f"filled {len(fills)} placeholders",
            reasoning=f"sources collected: {sum(len(v) for v in sources.values())} total",
            confidence=0.9,
        )

        return {"fills": fills, "sources": sources}

    async def _fetch_icebreaker_signal(self, contact: dict, source_types: list[str]) -> dict:
        """
        Plan 1 stub — returns a conservative fallback.
        Plan 2: hits LinkedIn scraper, company news API, calls Haiku with a
        signal-extraction prompt, picks the best signal, returns with source URL.
        """
        return {
            "value": f"Saw {contact.get('company', 'your company')} comes up in the {contact.get('industry') or 'space'} — wanted to reach out directly.",
            "sources": [],
        }

    def _render_cta(self, variant: str) -> str:
        ctas = {
            "quick_15": "Open to a quick 15-min chat this week?",
            "loom": "Want me to send a 2-min Loom walking through what this looks like?",
            "referral": "Know anyone it'd be a better fit for?",
        }
        return ctas.get(variant, ctas["quick_15"])

    async def handle(self, message, client_id, user_id, context=None):
        return SystemResult(text="ResearchModule is a pipeline stage, not a chat handler")
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_outreach/test_research.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add systems/scout/outreach/research.py tests/test_outreach/test_research.py
git commit -m "Add Plan-1 research module with name casualisation + placeholder stubs"
```

---

## Task 15: Renderer — template fill engine

**Files:**
- Create: `systems/scout/outreach/renderer.py`
- Test: `tests/test_outreach/test_renderer.py`

Renderer takes a contact, picks a template for their niche (via campaign assignment), runs research, fills the body, saves to `outreach_drafts`.

- [ ] **Step 1: Write failing test**

Create `tests/test_outreach/test_renderer.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def sample_contact():
    return {
        "id": "c1",
        "client_id": "test",
        "first_name": "Michael",
        "last_name": "Jones",
        "name": "Michael Jones",
        "title": "Managing Partner",
        "company": "Jones Advisory",
        "company_domain": "jones.example",
        "email": "mike@jones.example",
        "niche": "consulting",
        "status": "ready",
    }


@pytest.fixture
def sample_template():
    return {
        "id": "t1",
        "template_key": "advisoryos_offer_a",
        "version": 1,
        "niche": "consulting",
        "offer_label": "A",
        "status": "approved",
        "body": "Hey {{first_name_casual}},\n\n{{icebreaker}}\n\n{{bridge}}\n\nShort version: we install AdvisoryOS.\n\n{{cta}}",
        "placeholders": [
            {"name": "first_name_casual", "type": "name_casualisation", "required": True},
            {"name": "icebreaker", "type": "icebreaker_research", "required": True, "sources": ["linkedin_post"]},
            {"name": "bridge", "type": "bridge_rendering", "required": True},
            {"name": "cta", "type": "cta_selection", "required": True, "variants": ["quick_15"]},
        ],
        "metadata": {"subject": "quick q about {{company}}"},
    }


@pytest.mark.asyncio
async def test_fill_template_replaces_all_placeholders(sample_template):
    from systems.scout.outreach.renderer import fill_template_body

    fills = {
        "first_name_casual": "Mike",
        "icebreaker": "Saw your post last week.",
        "bridge": "That's exactly what we help with.",
        "cta": "Want to chat?",
    }
    rendered = fill_template_body(sample_template["body"], fills)
    assert "{{" not in rendered  # no unfilled placeholders
    assert "Hey Mike," in rendered
    assert "Saw your post last week." in rendered


@pytest.mark.asyncio
async def test_render_stage_produces_draft(sample_contact, sample_template):
    from systems.scout.outreach.renderer import RenderStage

    memory = MagicMock()
    memory.load_full_context = AsyncMock(return_value={})
    decisions = MagicMock()
    decisions.log_decision = AsyncMock(return_value="d1")

    stage = RenderStage(memory_store=memory, decision_logger=decisions)
    stage._fetch_contact = AsyncMock(return_value=sample_contact)
    stage._pick_template = AsyncMock(return_value=sample_template)
    stage._research_module_research_contact = AsyncMock(return_value={
        "fills": {
            "first_name_casual": "Mike",
            "icebreaker": "Saw you.",
            "bridge": "Bridge text.",
            "cta": "CTA text?",
        },
        "sources": {"icebreaker": ["https://linkedin.com/post/123"]},
    })
    stage._save_draft = AsyncMock(return_value={"id": "draft-1"})

    result = await stage.render(client_id="test", contact_id="c1")

    assert result["draft_id"] == "draft-1"
    assert "{{" not in result["body"]
    assert "Mike" in result["body"]
    assert decisions.log_decision.called
```

- [ ] **Step 2: Run — fail**

```bash
uv run pytest tests/test_outreach/test_renderer.py -v
```

- [ ] **Step 3: Create `systems/scout/outreach/renderer.py`**

```python
"""
Renderer — fill template placeholders for a contact + save draft.

Pipeline position: after enrich (contact has verified email), before QA (Plan 2).
Picks template via (client, niche) + campaign assignment; produces
outreach_drafts row with body + subject + research sources.

Template changes require human approval (status=approved in templates table).
Draft output has qa_status=pending until Plan 2 wires the QA agent.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from systems.base import BaseSystem, SystemResult
from systems.scout.outreach.research import ResearchModule

logger = logging.getLogger(__name__)


PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def fill_template_body(body: str, fills: dict[str, str]) -> str:
    """Replace {{name}} tokens in body with values from fills dict."""
    def _sub(match: re.Match) -> str:
        name = match.group(1)
        return fills.get(name, f"{{{{UNFILLED:{name}}}}}")

    return PLACEHOLDER_RE.sub(_sub, body)


def fill_subject(subject_template: str, contact: dict, fills: dict[str, str]) -> str:
    """Subject supports contact-field refs + placeholder fills."""
    if not subject_template:
        return ""

    # Simple replacement — supports {{company}} from contact and {{first_name_casual}} from fills
    result = subject_template
    for key, val in fills.items():
        result = result.replace(f"{{{{{key}}}}}", str(val))
    for key, val in contact.items():
        if val is not None:
            result = result.replace(f"{{{{{key}}}}}", str(val))
    return result


class RenderStage(BaseSystem):
    name = "scout_render"
    display_name = "Scout — Render Stage"
    description = "Fills template placeholders and saves outreach_drafts row"
    enabled = True

    async def render(
        self,
        client_id: str,
        contact_id: str,
    ) -> dict[str, Any]:
        await self.load_foundation(client_id, task_query=f"render draft for contact={contact_id}")

        contact = await self._fetch_contact(client_id, contact_id)
        if not contact:
            raise ValueError(f"contact {contact_id} not found")

        template = await self._pick_template(client_id, contact.get("niche"))
        if not template:
            raise RuntimeError(f"No approved template for niche={contact.get('niche')}")

        required_placeholders = template.get("placeholders", [])
        research_result = await self._research_module_research_contact(
            client_id=client_id,
            contact=contact,
            required_placeholders=required_placeholders,
        )
        fills = research_result["fills"]
        sources = research_result["sources"]

        body = fill_template_body(template["body"], fills)
        subject = fill_subject(template.get("metadata", {}).get("subject", ""), contact, fills)

        # Flatten sources for storage
        sources_flat = []
        for v in sources.values():
            sources_flat.extend(v)

        draft = await self._save_draft(
            client_id=client_id,
            contact_id=contact_id,
            campaign_id=contact.get("campaign_id"),
            template_id=template["id"],
            subject=subject,
            body=body,
            placeholder_fills=fills,
            research_sources=sources_flat,
        )

        await self.log_decision(
            client_id=client_id,
            decision_type="render_draft",
            context={"contact_id": contact_id, "template_id": template["id"]},
            decision=f"draft {draft.get('id')} rendered",
            reasoning=f"template={template['template_key']}v{template['version']}, sources={len(sources_flat)}",
            confidence=0.9,
        )

        return {"draft_id": draft.get("id"), "body": body, "subject": subject}

    async def _fetch_contact(self, client_id: str, contact_id: str) -> dict | None:
        from supabase import acreate_client
        from config.settings import get_settings
        s = get_settings()
        client = await acreate_client(s.supabase_url, s.supabase_service_role_key)
        resp = await client.table("contacts").select("*").eq("id", contact_id).eq("client_id", client_id).execute()
        return resp.data[0] if resp.data else None

    async def _pick_template(self, client_id: str, niche: str | None) -> dict | None:
        """Pick an approved template for the niche. Plan 1: first-match. Plan 2+: A/B rotation via campaigns."""
        from supabase import acreate_client
        from config.settings import get_settings
        s = get_settings()
        client = await acreate_client(s.supabase_url, s.supabase_service_role_key)
        q = (
            client.table("templates")
            .select("*")
            .eq("client_id", client_id)
            .eq("status", "approved")
            .order("version", desc=True)
            .limit(1)
        )
        if niche:
            q = q.eq("niche", niche)
        resp = await q.execute()
        return resp.data[0] if resp.data else None

    async def _research_module_research_contact(
        self, client_id: str, contact: dict, required_placeholders: list[dict]
    ) -> dict:
        """Thin wrapper so tests can patch this method. Real ResearchModule instantiation."""
        mod = ResearchModule(
            memory_store=self.memory,
            decision_logger=self.decisions,
        )
        return await mod.research_contact(
            client_id=client_id,
            contact=contact,
            required_placeholders=required_placeholders,
        )

    async def _save_draft(
        self,
        client_id: str,
        contact_id: str,
        campaign_id: str | None,
        template_id: str,
        subject: str,
        body: str,
        placeholder_fills: dict,
        research_sources: list[str],
    ) -> dict:
        from supabase import acreate_client
        from config.settings import get_settings
        s = get_settings()
        client = await acreate_client(s.supabase_url, s.supabase_service_role_key)
        row = {
            "client_id": client_id,
            "contact_id": contact_id,
            "campaign_id": campaign_id,
            "template_id": template_id,
            "subject": subject,
            "body": body,
            "placeholder_fills": placeholder_fills,
            "research_sources": research_sources,
            "qa_status": "pending",
            "status": "rendered",
        }
        resp = await client.table("outreach_drafts").insert(row).execute()
        return resp.data[0] if resp.data else {}

    async def handle(self, message, client_id, user_id, context=None):
        return SystemResult(text="RenderStage is a pipeline stage, not a chat handler")
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_outreach/test_renderer.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add systems/scout/outreach/renderer.py tests/test_outreach/test_renderer.py
git commit -m "Add template renderer stage — fills placeholders, saves draft"
```

---

## Task 16: Deployment scripts (seed_autonomy + load_context + load_knowledge)

**Files:**
- Create: `scripts/seed_autonomy_rules.py`
- Create: `scripts/load_context.py` (migrated)
- Create: `scripts/load_knowledge.py` (new)
- Create: `scripts/setup_client.sh` (migrated)

- [ ] **Step 1: Create `scripts/seed_autonomy_rules.py`**

```python
"""Seed autonomy_rules for a new client per design spec Section 3."""
from __future__ import annotations

import asyncio
import sys

from supabase import acreate_client

from config.settings import get_settings


DEFAULT_RULES = [
    ("send_outbound", "act_notify"),
    ("send_response", "suggest"),
    ("apply_template_change", "suggest"),
    ("kill_template", "draft"),
    ("scale_template", "draft"),
    ("icp_threshold", "autonomous"),
    ("enrichment_strategy", "autonomous"),
    ("research_strategy", "autonomous"),
    ("placeholder_fill", "autonomous"),
    ("reply_classification", "autonomous"),
]


async def seed(client_id: str) -> None:
    s = get_settings()
    client = await acreate_client(s.supabase_url, s.supabase_service_role_key)

    rows = [
        {"client_id": client_id, "action_type": action, "level": level}
        for action, level in DEFAULT_RULES
    ]
    await client.table("autonomy_rules").upsert(rows, on_conflict="client_id,action_type").execute()
    print(f"Seeded {len(rows)} autonomy rules for client={client_id}")


if __name__ == "__main__":
    client_id = sys.argv[1] if len(sys.argv) > 1 else "clymb"
    asyncio.run(seed(client_id))
```

- [ ] **Step 2: Migrate `load_context.py`**

Source reference: `/home/kirsten/01_PERSONAL/10_PERSONAL_PROJECTS/base-camp-agents/scripts/load_context.py` (213 lines).

Create `scripts/load_context.py` — key responsibilities from source:
- Read all .md files from `context/` and `context/projects/{client}/`
- Chunk them
- Generate embeddings via Voyage AI
- Upsert into `business_context` + `context_registry` tables

```python
"""Load client context into Supabase with embeddings.

Migrated from base-camp-agents/scripts/load_context.py. Reads:
- context/personal.md
- context/personal-operating.md
- context/voice.md
- context/business-frameworks.md
- context/integrations.md
- context/projects/{client_id}/*.md
- context/projects/{client_id}/research/**/*.md

Each file is chunked (by heading or by N lines), embedded with Voyage AI,
and upserted into business_context + context_registry.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

import httpx
from supabase import acreate_client

from config.settings import get_settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

CHUNK_SIZE_WORDS = 400
VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-3"


def chunk_markdown(text: str, size: int = CHUNK_SIZE_WORDS) -> list[str]:
    """Chunk by words while preserving heading boundaries."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in text.split("\n\n"):
        words = len(para.split())
        if current_len + words > size and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = words
        else:
            current.append(para)
            current_len += words

    if current:
        chunks.append("\n\n".join(current))
    return chunks


async def embed_voyage(texts: list[str], api_key: str) -> list[list[float]]:
    """Call Voyage AI embeddings API."""
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY not set")
    payload = {"input": texts, "model": VOYAGE_MODEL}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=60.0) as c:
        resp = await c.post(VOYAGE_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return [d["embedding"] for d in data["data"]]


async def load_file(
    supabase,
    voyage_key: str,
    client_id: str,
    file_path: Path,
    scope: str,
) -> int:
    """Read, chunk, embed, and upsert a markdown file."""
    text = file_path.read_text()
    chunks = chunk_markdown(text)
    embeddings = await embed_voyage(chunks, voyage_key)

    rows = [
        {
            "client_id": client_id,
            "scope": scope,
            "source_path": str(file_path),
            "section": f"{file_path.name}#{i}",
            "content": chunk,
            "embedding": emb,
        }
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]
    await supabase.table("business_context").upsert(
        rows,
        on_conflict="client_id,source_path,section",
    ).execute()

    logger.info("Loaded %s (%d chunks)", file_path, len(chunks))
    return len(chunks)


async def main(client_id: str, dry_run: bool = False) -> None:
    settings = get_settings()
    if dry_run:
        logger.info("[dry-run] client=%s", client_id)

    supabase = await acreate_client(settings.supabase_url, settings.supabase_service_role_key)

    repo_root = Path(__file__).parent.parent
    files: list[tuple[Path, str]] = []
    for f in repo_root.glob("context/*.md"):
        files.append((f, "personal"))
    client_dir = repo_root / "context" / "projects" / client_id
    if client_dir.exists():
        for f in client_dir.rglob("*.md"):
            files.append((f, "project"))

    total = 0
    for f, scope in files:
        if dry_run:
            logger.info("[dry-run] would load %s (scope=%s)", f, scope)
            continue
        total += await load_file(supabase, settings.voyage_api_key, client_id, f, scope)

    logger.info("Loaded %d chunks total for client=%s", total, client_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.client, args.dry_run))
```

- [ ] **Step 3: Create `scripts/load_knowledge.py`**

```python
"""Load expert knowledge (data/knowledge/*.md) into knowledge_base with embeddings.

Unlike context (per-client), knowledge is shared across clients (templated).
Each client's load_knowledge run writes its own rows — the content is the same
but client_id column allows per-client RLS.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

import httpx
from supabase import acreate_client

from config.settings import get_settings
from scripts.load_context import chunk_markdown, embed_voyage

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


async def main(client_id: str, dry_run: bool = False) -> None:
    settings = get_settings()
    supabase = await acreate_client(settings.supabase_url, settings.supabase_service_role_key)

    repo_root = Path(__file__).parent.parent
    knowledge_dir = repo_root / "data" / "knowledge"

    total = 0
    for f in sorted(knowledge_dir.glob("*.md")):
        text = f.read_text()
        chunks = chunk_markdown(text)
        if dry_run:
            logger.info("[dry-run] would load %s (%d chunks)", f.name, len(chunks))
            continue

        embeddings = await embed_voyage(chunks, settings.voyage_api_key)
        rows = [
            {
                "client_id": client_id,
                "source": f.stem,
                "section": f"{f.name}#{i}",
                "content": chunk,
                "embedding": emb,
            }
            for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
        ]
        await supabase.table("knowledge_base").upsert(
            rows,
            on_conflict="client_id,source,section",
        ).execute()
        total += len(chunks)
        logger.info("Loaded %s (%d chunks)", f.name, len(chunks))

    logger.info("Loaded %d total chunks for client=%s", total, client_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.client, args.dry_run))
```

- [ ] **Step 4: Create `scripts/setup_client.sh`**

```bash
#!/usr/bin/env bash
# setup_client.sh — one-shot bootstrap for a new client deployment.
# Usage: ./scripts/setup_client.sh <client_id>

set -euo pipefail

CLIENT_ID="${1:-}"
if [[ -z "$CLIENT_ID" ]]; then
    echo "Usage: $0 <client_id>"
    exit 1
fi

echo "==> Bootstrapping client: $CLIENT_ID"

# 1. Sanity check .env
if [[ ! -f .env ]]; then
    echo "ERROR: .env file not found. Copy .env.example → .env and fill in secrets first."
    exit 1
fi

# 2. Insert client record (idempotent)
echo "==> Creating client row"
uv run python -c "
import asyncio, os
from supabase import acreate_client
async def main():
    c = await acreate_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
    await c.table('clients').upsert({'id': '$CLIENT_ID', 'name': '$CLIENT_ID'}, on_conflict='id').execute()
asyncio.run(main())
"

# 3. Seed autonomy rules
echo "==> Seeding autonomy rules"
uv run python scripts/seed_autonomy_rules.py "$CLIENT_ID"

# 4. Load context
echo "==> Loading context (run with --dry-run first to preview)"
uv run python scripts/load_context.py --client "$CLIENT_ID"

# 5. Load knowledge
echo "==> Loading expert knowledge"
uv run python scripts/load_knowledge.py --client "$CLIENT_ID"

echo "==> Client $CLIENT_ID bootstrapped. Next: configure ICPs, templates, campaigns."
```

Run:
```bash
chmod +x scripts/setup_client.sh
```

- [ ] **Step 5: Write a smoke test**

Create `tests/test_scripts/__init__.py` (empty) and `tests/test_scripts/test_chunk.py`:

```python
def test_chunk_splits_long_text():
    from scripts.load_context import chunk_markdown

    text = "Para 1.\n\nPara 2.\n\n" + ("Long para. " * 500)
    chunks = chunk_markdown(text, size=200)
    assert len(chunks) >= 2
    assert all(isinstance(c, str) for c in chunks)
```

Run:
```bash
uv run pytest tests/test_scripts/test_chunk.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/seed_autonomy_rules.py scripts/load_context.py scripts/load_knowledge.py scripts/setup_client.sh tests/test_scripts/
git commit -m "Add deployment scripts: setup_client, load_context, load_knowledge, seed_autonomy"
```

---

## Task 17: End-to-end dry-run integration test

**Files:**
- Create: `tests/test_e2e/__init__.py`
- Create: `tests/test_e2e/test_pipeline_dry_run.py`

Final test of Plan 1 scope: 10 contacts → rendered drafts (no QA, no send) in dry-run mode, using all pipeline stages composed.

- [ ] **Step 1: Create integration test**

Create `tests/test_e2e/__init__.py` (empty) and `tests/test_e2e/test_pipeline_dry_run.py`:

```python
"""End-to-end integration test — Plan 1 scope.

Verifies that pull → score → screen → (enrich stubbed) → render produces
outreach drafts for 10 contacts. Uses fully mocked external services.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_full_pipeline_dry_run_produces_drafts():
    from systems.scout.pipeline.pull import PullStage
    from systems.scout.pipeline.score import ScoreStage
    from systems.scout.pipeline.screen import ScreenStage
    from systems.scout.pipeline.enrich import EnrichStage
    from systems.scout.outreach.renderer import RenderStage

    memory = MagicMock()
    memory.load_full_context = AsyncMock(return_value={"business_context": [], "relevant_knowledge": []})
    decisions = MagicMock()
    decisions.log_decision = AsyncMock(return_value="d-id")

    # Stage 1: Pull (mocked)
    pull = PullStage(memory_store=memory, decision_logger=decisions)
    pull._apollo_search = AsyncMock(return_value=(
        [
            {
                "id": f"apollo-{i}",
                "first_name": "Alex",
                "last_name": f"Test{i}",
                "name": f"Alex Test{i}",
                "title": "Fractional CFO",
                "organization": {
                    "name": f"Test Co {i}",
                    "website_url": f"https://test{i}.example",
                    "industry": "Consulting",
                    "num_employees": 20,
                },
                "country": "United States",
                "linkedin_url": f"https://linkedin.com/in/alex{i}",
            }
            for i in range(10)
        ],
        10,
    ))
    pull._supabase_upsert = AsyncMock(side_effect=lambda c: {**c, "id": f"contact-{c['source_id']}"})

    pull_result = await pull.run(
        client_id="test",
        icp_titles=["Fractional CFO"],
        max_contacts=10,
        niche="fractional",
        dry_run=False,
    )
    assert pull_result["inserted"] == 10

    # Stage 2: Score (mocked DB, real scoring algorithm)
    score = ScoreStage(memory_store=memory, decision_logger=decisions)
    score._fetch_icp = AsyncMock(return_value={
        "industries": ["consulting"],
        "titles": ["CFO"],
        "employee_min": 5,
        "employee_max": 50,
        "weights": {},
        "blacklist_companies": [],
        "blacklist_domains": [],
        "geographies": ["united states"],
    })
    score._fetch_unscored_contacts = AsyncMock(return_value=[
        {"id": f"contact-apollo-{i}", "industry": "consulting", "title": "Fractional CFO", "employees": 20, "geography": "United States"}
        for i in range(10)
    ])
    score._update_contact_score = AsyncMock()
    score_result = await score.run(client_id="test", niche="fractional", limit=10, dry_run=False)
    assert score_result["scored"] == 10
    assert score_result["tier_counts"]["A"] > 0 or score_result["tier_counts"]["B"] > 0

    # Stage 3: Render — test a single contact through render (other stages similar pattern)
    sample_template = {
        "id": "t1",
        "template_key": "fractionalos_offer_a",
        "version": 1,
        "niche": "fractional",
        "offer_label": "A",
        "status": "approved",
        "body": "Hey {{first_name_casual}},\n\n{{icebreaker}}\n\n{{bridge}}\n\nYours — Kirsten\n\n{{cta}}",
        "placeholders": [
            {"name": "first_name_casual", "type": "name_casualisation"},
            {"name": "icebreaker", "type": "icebreaker_research", "sources": ["linkedin_post"]},
            {"name": "bridge", "type": "bridge_rendering"},
            {"name": "cta", "type": "cta_selection", "variants": ["quick_15"]},
        ],
        "metadata": {"subject": "quick q"},
    }

    sample_contact = {
        "id": "contact-apollo-0",
        "client_id": "test",
        "first_name": "Alex",
        "last_name": "Test0",
        "name": "Alex Test0",
        "title": "Fractional CFO",
        "company": "Test Co 0",
        "company_domain": "test0.example",
        "email": "alex@test0.example",
        "niche": "fractional",
    }

    render = RenderStage(memory_store=memory, decision_logger=decisions)
    render._fetch_contact = AsyncMock(return_value=sample_contact)
    render._pick_template = AsyncMock(return_value=sample_template)
    render._save_draft = AsyncMock(return_value={"id": "draft-final"})

    render_result = await render.render(client_id="test", contact_id="contact-apollo-0")

    assert "{{" not in render_result["body"]
    assert "Alex" in render_result["body"]
    assert render_result["draft_id"] == "draft-final"
```

- [ ] **Step 2: Run the integration test**

```bash
uv run pytest tests/test_e2e/test_pipeline_dry_run.py -v
```

Expected: 1 passed.

- [ ] **Step 3: Run FULL test suite**

```bash
uv run pytest -v
```

Expected: All tests pass. Count should be 20+ tests.

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e/
git commit -m "Add end-to-end pipeline dry-run integration test"
```

---

## Task 18: Pipeline SOPs

**Files:**
- Create: `data/reference/sops/README.md`
- Create: `data/reference/sops/_templates/sop-template.md`
- Create: `data/reference/sops/pipeline/scout-pipeline-nightly-run.md`
- Create: `data/reference/sops/pipeline/write-approve-template.md`

- [ ] **Step 1: Create SOP template**

Create `data/reference/sops/_templates/sop-template.md`:

```markdown
# SOP: [Name]
Version: 1.0
Last reviewed: YYYY-MM-DD
Owner: [Kirsten / VA / Junior / AI / Automated]

## Purpose
Why this SOP exists and what problem it solves.

## Trigger
When or what initiates this procedure.

## Inputs
- Input 1
- Input 2

## Outputs
- Output 1
- Output 2

## Steps
1. [Atomic, verifiable action]
2. [Atomic, verifiable action]

## QA — how to verify it's done right
- Check 1
- Check 2

## Common errors + fixes
| Error | Cause | Fix |
|---|---|---|

## Escalation
When to stop and ask for help.

## Automation notes
- Fully automated: [list]
- Partially automated: [what human does vs AI does]
- Not automatable (and why): [list]

## Change log
- v1.0 — YYYY-MM-DD — initial
```

- [ ] **Step 2: Create SOP manifest**

Create `data/reference/sops/README.md`:

```markdown
# SOP Library Manifest

| Path | Owner | Version | Last reviewed |
|---|---|---|---|
| deployment/02-setup-supabase.md | Kirsten/VA | 1.0 | 2026-04-20 |
| pipeline/scout-pipeline-nightly-run.md | Automated | 1.0 | 2026-04-20 |
| pipeline/write-approve-template.md | Kirsten | 1.0 | 2026-04-20 |

All SOPs follow `_templates/sop-template.md`. Add new SOPs by copying the template and updating this manifest.
```

- [ ] **Step 3: Create pipeline-run SOP**

Create `data/reference/sops/pipeline/scout-pipeline-nightly-run.md`:

```markdown
# SOP: Scout Pipeline Nightly Run
Version: 1.0
Last reviewed: 2026-04-20
Owner: Automated (Railway cron)

## Purpose
Process all newly-pulled contacts through the full Scout pipeline overnight so
that rendered drafts are ready for the morning send window.

## Trigger
Railway cron: `0 2 * * *` (2am local time) → `POST /api/pipeline/trigger`
with `{"stage": "full", "dry_run": false}`.

## Inputs
- All contacts in each active niche at status `new` (from Apollo pull or manual imports)
- ICP definitions in `icp_definitions` for each active niche
- Approved templates in `templates` for each active niche

## Outputs
- Contacts transitioned through statuses: new → screened → enriched → ready → rendered
- `outreach_drafts` rows with `qa_status=pending` (QA runs in a later cron in Plan 2)
- Decision log entries for each stage

## Steps
1. Endpoint receives POST with stage="full" + cron secret verified.
2. For each active niche in `client_config.active_niches`:
   a. PullStage.run(niche, max=daily_pull_cap) — pulls new Apollo contacts.
   b. ScoreStage.run(niche, limit=500) — scores unscored contacts.
   c. ScreenStage.run(niche, limit=500) — filters blacklist + D-tier.
   d. EnrichStage.run(niche, limit=daily_enrich_cap) — finds + verifies emails.
   e. RenderStage iterates contacts at status=ready — renders drafts.
3. Log summary metrics to `activity_log`.

## QA — verify it's done right
- Check `decision_log` has `pull_leads`, `score_contacts`, `screen_contacts`, `enrich_contacts`, `render_draft` entries from last 4 hours
- Check `outreach_drafts` has new rows at `qa_status=pending`
- Check no contact is stuck (same status for >2 days)

## Common errors + fixes
| Error | Cause | Fix |
|---|---|---|
| Apollo 429 | rate limit | Exponential backoff (already implemented); reduce daily_pull_cap |
| Anymail Finder timeout | API latency | Retry next run |
| Render fails "no approved template" | template not approved | Kirsten approves template in web app or direct DB update |
| "No ICP defined" | niche enabled in client_config but ICP row missing | Kirsten adds ICP via web app before next run |

## Escalation
If pipeline fails >2 consecutive runs: pause cron via `/api/pipeline/pause`, alert Kirsten.

## Automation notes
- Fully automated: all pipeline stages + error logging
- Partially automated: alerting (Kirsten sees failures in web app daily digest)
- Not automated: ICP + template approval (intentionally human-gated)

## Change log
- v1.0 — 2026-04-20 — initial
```

- [ ] **Step 4: Create template-writing SOP**

Create `data/reference/sops/pipeline/write-approve-template.md`:

```markdown
# SOP: Write and Approve a New Template
Version: 1.0
Last reviewed: 2026-04-20
Owner: Kirsten

## Purpose
Add a new pre-approved copy template to the Scout library for a niche × offer
test cell. Templates are the unit of customisation in CLYMB — they are
data, not code, per the productisation principle.

## Trigger
- New niche launch (need 3 templates — A, B, C)
- Template kill triggers need for replacement
- Offer-score gap: existing templates score below 120/135

## Inputs
- Niche name (e.g., "fractional")
- Offer label (e.g., "A — pipeline pain")
- Research: niche pain-buckets document, Nick Saraev archetype, Hormozi offer framework
- voice.md copy rules (no em dashes, no walls, casual tone, specific proof)

## Outputs
- Approved `.md` file in `systems/scout/outreach/templates/`
- Row in `templates` table with `status=approved`
- Offer score documented (27-constraint scorecard)

## Steps
1. Copy `systems/scout/outreach/templates/_schema.md` for format reference.
2. Create new file: `systems/scout/outreach/templates/{template_key}_v{version}.md`.
3. Fill YAML frontmatter: template_key, version, niche, offer_label, placeholders, offer_score.
4. Write subject line + body using voice.md rules.
5. Use pain-bucket language from `context/projects/{client}/research/customer/pain-buckets-and-offers.md` verbatim where possible.
6. Ensure every `{{placeholder}}` in body is also declared in frontmatter.
7. Score template against the 27 constraints (see design spec Section 2, offer_score field).
8. Peer-review (at least one human reviewer) — can be Kirsten herself after 24h gap.
9. Set `status: approved` in frontmatter; add `approved_by` and `approved_at`.
10. Run `uv run python -c "from systems.scout.outreach.template_store import load_templates_from_directory; load_templates_from_directory(Path('systems/scout/outreach/templates'))"` to validate.
11. Sync to DB via deployment pipeline (next scheduled run) OR manually via `sync_templates_to_db`.

## QA
- No unfilled placeholders in body
- No em dashes, no walls, no banned words per voice.md
- Offer score ≥ 120/135 (89%+)
- Declared placeholders match body usage
- Subject line under 50 characters
- Body under 120 words

## Common errors + fixes
| Error | Cause | Fix |
|---|---|---|
| Validation fails with "placeholder not declared" | Forgot frontmatter entry | Add the placeholder to `placeholders` list |
| Template rendered with literal `{{UNFILLED:X}}` | Placeholder declared but research can't fill | Implement the placeholder type in research.py OR remove from body |
| Offer score below 120 | Template hits commodity traps | Review against playbook upgrade 5 ("Eliminate the Commodity Trap") |

## Escalation
If offer score is stuck below 120 after 3 iterations → use `superpowers:brainstorming` skill to rework the offer angle from scratch with Nick + Hormozi frameworks.

## Automation notes
- Fully automated: parsing, validation, DB sync
- Partially automated: offer score (future: LLM-assisted scoring on draft)
- Not automated: creative writing + strategic offer design (intentionally human)

## Change log
- v1.0 — 2026-04-20 — initial
```

- [ ] **Step 5: Commit**

```bash
git add data/reference/sops/
git commit -m "Add SOP library scaffold + Plan 1 pipeline + template SOPs"
```

---

## Task 19: Final full-suite verification + merge-ready check

**Files:**
- None created; verifying existing

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest -v --tb=short
```

Expected: All tests pass. Total count: ~22 tests (2 settings + 2 health + 3 middleware + 2 pipeline router + 2 pull + 2 score + 4 screen + 2 enrich + 4 template + 2 research + 2 renderer + 1 e2e + 1 scripts).

- [ ] **Step 2: Run linting**

```bash
uv run ruff check .
```

Expected: No errors (or minor fixable ones — run `uv run ruff check --fix .` if needed).

- [ ] **Step 3: Verify API starts**

```bash
uv run uvicorn api.main:app --port 8000 &
sleep 2
curl -s http://localhost:8000/health | head
kill %1
```

Expected: `{"status":"ok",...}`.

- [ ] **Step 4: Manual smoke test — pull 2 contacts from Apollo**

Only run this if Apollo credits are available and Supabase is set up. Uses real services.

```bash
uv run python -c "
import asyncio
from systems.scout.pipeline.pull import PullStage
from os.foundation.decision_logger import DecisionLogger
from os.memory.store import MemoryStore
from config.settings import get_settings

s = get_settings()

async def main():
    memory = MemoryStore(s.supabase_url, s.supabase_service_role_key)
    decisions = DecisionLogger(s.supabase_url, s.supabase_service_role_key)
    pull = PullStage(memory_store=memory, decision_logger=decisions)
    result = await pull.run(client_id=s.client_id, icp_titles=['Fractional CFO'], max_contacts=2, niche='fractional', dry_run=True)
    print(result)

asyncio.run(main())
"
```

Expected: `{'seen': 2, 'inserted': 0, 'apollo_total': ...}` (dry-run, so inserted stays 0).

- [ ] **Step 5: Push branch + open merge prep**

```bash
git push -u origin plan1-foundation-scout
```

- [ ] **Step 6: Write plan-completion commit**

```bash
git commit --allow-empty -m "Plan 1 complete — foundation + scout migration

Scope delivered:
- FastAPI scaffold with /health, /api/pipeline/trigger, HMAC middleware
- Supabase schema (002_scout.sql) with 13 tables + RLS
- Pipeline stages migrated: pull, score, screen, enrich — all BaseSystem-conformant
- Template storage: markdown + YAML frontmatter, validator, DB sync
- Research module (name casualisation + placeholder stubs for Plan 2)
- Renderer: fills templates, saves outreach_drafts
- Deployment scripts: setup_client.sh, seed_autonomy, load_context, load_knowledge
- SOPs: supabase setup, pipeline nightly run, template writing

Ready for: Plan 2 (QA agent + send + inbound)."
```

---

## Summary of Plan 1 deliverables

After completion:

| Area | Deliverable |
|---|---|
| Infrastructure | FastAPI + Supabase + Railway-ready, health check, HMAC auth, cron-secret middleware |
| Schema | 002_scout.sql — 13 tables, RLS, indexes |
| Pipeline | Pull, Score, Screen, Enrich — BaseSystem-conformant, decision-logged |
| Outreach | Template store, Research module, Renderer — can produce drafts end-to-end |
| Scripts | setup_client.sh, seed_autonomy_rules, load_context, load_knowledge |
| Tests | 22+ tests across unit + integration + e2e layers |
| SOPs | Manifest + Supabase setup + nightly run + template writing |

**What Plan 1 does NOT deliver (deferred to later plans):**

- QA agent (Plan 2)
- Send stage + Smartlead integration (Plan 2)
- Inbound webhooks + reply classification + response drafts (Plan 2)
- Web app (Plan 3)
- Cost management system (Plan 4)
- Monthly margin review (Plan 5)
- Improvement backlog (Plan 5)
- Client portal + Slack + expert knowledge content + deployment hardening (Plan 6)

---

## Self-review checklist (fill in after plan execution)

- [ ] All 19 tasks completed
- [ ] Full test suite green
- [ ] Linting clean
- [ ] API reachable at /health locally
- [ ] End-to-end dry-run produces a rendered draft body with no unfilled placeholders
- [ ] Every pipeline stage calls `load_foundation()` and `log_decision()`
- [ ] SOPs committed for every new module
- [ ] Branch pushed; ready for Plan 2 to build on top

