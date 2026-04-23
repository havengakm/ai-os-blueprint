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
