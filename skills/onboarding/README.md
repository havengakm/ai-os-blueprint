# Onboarding skills

Skills invoked at client deployment time to seed a new AIOS instance with client-specific context.

## Planned skills

- `onboard-client.md` — top-level orchestrator: creates client_id, provisions context entries, seeds autonomy rules, loads knowledge base, configures default ICP, verifies env. (Plan 1 Task 16)
- `seed-knowledge-base.md` — load expert-framework markdown (Sapp, Saraev, Hormozi, Acosta, Walsh, Brunson, copywriting frameworks) into `knowledge_base` table with embeddings. (Plan 1 Task 16)
- `load-context.md` — load client-specific markdown from `context/{client}/*.md` into `business_context` + `client_facts` tables. (Plan 1 Task 16)
- `configure-trigify-monitors.md` — create the per-client Trigify searches via REST API, store search IDs in `client_config.trigify_search_ids`. (Plan 1 Task 12b.3b follow-up)
- `configure-client-offer.md` — walk operator through the 27-constraint offer-score framework for the client's offer, store in client_config. (Plan 2)
- `configure-channel-stack.md` — select which channels are enabled for this client (email always; LinkedIn / SMS / voicemail / WhatsApp / letters per their compliance posture + audience). (Plan 3+)
- `verify-deployment.md` — preflight check: all tables exist, foundation modules wired, daemon scheduled, test contact can traverse full pipeline in dry-run. (Plan 1 Task 17)
