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
