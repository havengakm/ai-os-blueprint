# Plan 2: Beacon email full-loop (list → enrich → send → reply → optimise) + Productisation

## Context

Plan 1 (foundation + Scout) and Plan 1.5 (cost discipline + body template + acceptance hardening) are both shipped to `main` and tagged. The AIOS now produces validated, rendered outreach drafts at MVP cost (~$0.01-0.03/contact today, $0.002/contact target after this plan).

Plan 2 takes the rendered drafts and **gets them in front of prospects**, closes the reply loop (classification + auto-respond), and adds the optimization layer that lets the system learn and improve. Plus a productisation deployment script so client #2 can be spun up cleanly.

**Scope decision 2026-04-26**: operator chose to push LinkedIn (and all other channels) out of Plan 2. Plan 2 is **email-only, full-loop**: list scraping → enrichment → messaging → replies → optimisation. Multi-channel work moves to Plan 3.

The cost gap from today's $0.01-0.03/contact to the $0.002 target closes during this plan — signal-gated Deep Research + per-contact cost rollup + 5c per-contact hard ceiling are folded into Phase 4. The Optimizer agent (weekly review + adapter ROI + variant performance + recommendations) is folded into Phase 5 as the v1 read-only-recommendations system.

This plan doc is the source of truth. If a decision changes mid-execution, update the plan first, then the code.

## Scope

### In scope

- **Phase 0**: Pre-Plan-2 hardening from `docs/superpowers/plans/follow-ups-plan1.md` items 1-15 (the items explicitly tagged for the Plan-2-kickoff window).
- **Phase 1**: ESP evaluation. ✅ DECIDED 2026-04-27 = **Instantly Growth ($47/mo)** — see `docs/superpowers/decisions/2026-04-27-esp-comparison.md`.
- **Phase 2**: Beacon email send foundation. Schema (outreach_send_log, outreach_reply, send_account, send_caps), Beacon adapter against **Instantly v2 API**, send orchestrator (tier gate + DND check + daily cap + per-contact cost ceiling + autonomy), webhook signature verification, send-time autonomy gating. Signal-presence is a **ranking** factor (signal-having contacts go first within the same tier), not a gate.
- **Phase 3**: Reply ingestion + classification + auto-respond runtime. Webhook ingest, Haiku classifier (positive / negative / objection / unsubscribe / OOO), auto-respond for objections + bookings, human escalation queue, 90-day cool-off + round-based re-entry.
- **Phase 4**: Cost optimiser foundation. Signal-gated Deep Research (only fire `claude_deep_research` when Trigify returned no signal), per-contact cost rollup SQL view + RPC, per-contact 5c hard ceiling, operator cost dashboard (CLI initially).
- **Phase 5**: Optimizer agent v1 (read-only recommendations). Weekly review job that reads decision_log + outreach_send_log + outreach_reply: cost-per-lead / cost-per-reply / cost-per-meeting, variant performance (which subjects/icebreakers convert), adapter ROI (which signals correlate with positive replies), recommendations surfaced to operator. No auto-apply yet — operator approves before changes ship.
- **Phase 6**: Productisation deployment script. Bootstrap a new client AIOS (provisions context/, data/knowledge/personal/, company/, copies experts/ baseline; seeds client_config + autonomy_rules; runs migrations).
- **Phase 7**: Acceptance + merge + tag `plan-2`.

### Out of scope (deferred to later plans)

- **LinkedIn outbound** — operator decision 2026-04-26: prioritise email full-loop first; LinkedIn moves to Plan 3.
- **Other channels** (SMS / WhatsApp / voicemail-drop / letters) → Plan 3.
- **AI voice agent** (still backlog per `feedback_voice_agent_backlog_not_rejected`).
- **Optimizer v2 (auto-apply)** — Phase 5 ships read-only recommendations only. Auto-applying recommendations + autonomy promotion + multi-deployment learning aggregation → future plan once v1 has a usage history.
- **Client web app** (Next.js + Supabase) — operator-facing dashboard for clients → backlog.
- **CRM integrations** (HubSpot / Pipedrive sync) → future plan.

## Branch strategy

1. Branch off `main` (currently at `69bf9a9`, tag `plan-1.5` at `72ece5f`).
2. Branch name: `feat/plan-2-beacon`.
3. Plan 2 lands in **multiple PRs** rather than one giant merge (Plan 1.5 was 30+ commits, ~33 files; Plan 2 will be larger). Suggested split:
   - PR-A: Phase 0 + Phase 1 (hardening + ESP eval doc)
   - PR-B: Phase 2 (Beacon email foundation)
   - PR-C: Phase 3 (Reply runtime)
   - PR-D: Phase 4 (Cost optimiser foundation)
   - PR-E: Phase 5 (Optimizer agent v1)
   - PR-F: Phase 6 (Productisation script)
   - PR-G: Phase 7 acceptance + tag
4. Each PR squash-merges into `feat/plan-2-beacon`; the whole branch merges into `main` at Phase 7 with a single `--no-ff` commit + `plan-2` tag (matching the Plan 1.5 pattern).

## Phase 0: Pre-Plan-2 hardening

Source: `docs/superpowers/plans/follow-ups-plan1.md` items 1-15.

### Task 2.0.1: Webhook signature verification + cron_secret rename

**Source**: follow-up item 1.
**Files**: `api/middleware/verify_signatures.py`, `api/routers/pipeline.py` (call site).

Rename `require_cron_secret` → `cron_secret_dep` (or split into `verify_cron_secret` inner + wrapper). Add a sibling `verify_webhook_signature(secret_field: str)` factory for ESP webhook + LinkedIn webhook signatures. Both used by Phase 2 + Phase 3 + Phase 4.

**Acceptance**:
- [ ] No call site uses `require_cron_secret()`; all use `cron_secret_dep`.
- [ ] `verify_webhook_signature` available + tested with HMAC-SHA256 + raw-body comparison.
- [ ] Existing `tests/test_api/test_cron_auth.py` passes; new `tests/test_api/test_webhook_auth.py` covers happy path + invalid signature + missing header.

### Task 2.0.2: Schema CHECK additions for `decision_type`

**Source**: follow-up items 14 + 22 + (new) `send_attempt`, `reply_received`, `reply_classification`.
**Files**: `scripts/sql/015_decision_log_check_constraint_extensions.sql` (new).

Add `source_selection`, `identity_lookup`, `send_attempt`, `reply_received`, `reply_classification` to `decision_log.decision_type` CHECK allow-list. Update emitting sites: `systems/scout/sources/orchestrator.py`, `systems/scout/identity/*`, plus the new Beacon emit sites coming in Phase 2-3.

**Acceptance**:
- [ ] Migration runs cleanly against current schema.
- [ ] `decision_log` rows can be inserted with all 5 new types.
- [ ] Old `enrichment_choice` rows untouched.

### Task 2.0.3: Test additions to lock contracts

**Source**: follow-up items 2, 3, 4, 7.
**Files**: `tests/test_api/test_pipeline_router.py`, `api/routers/pipeline.py`, `tests/test_config_settings.py`.

Three small additions:
- Test that `/api/pipeline/trigger` returns 422 on invalid stage (locks the `Literal` contract).
- Inline comment on the pipeline-trigger stub clarifying `"accepted"` semantics until real dispatch wires up.
- Case-insensitive env var resolution test (`monkeypatch.setenv("smartlead_api_key", ...)` lowercase resolves the same as `SMARTLEAD_API_KEY`).

**Acceptance**:
- [ ] Three new tests pass.
- [ ] Inline comment lands.

### Task 2.0.4: Module-level `app = create_app()` mitigation

**Source**: follow-up item 5.
**Files**: split `api/main.py` (factory only) + new `api/asgi.py` (module-level `app = create_app()`). Update `Procfile` + `railway.toml` startCommand path.

Address before any test imports `app` at module top level (Phase 3 webhook tests will).

**Acceptance**:
- [ ] `api/main.py` exports `create_app()` only.
- [ ] `api/asgi.py` has `app = create_app()`.
- [ ] Deployment configs point at `api.asgi:app`.
- [ ] `tests/test_api/test_webhook_auth.py` (from Task 2.0.1) imports `create_app` from `api.main`, instantiates fresh per-test, no module-level side-effects.

### Task 2.0.5: ClutchAdapter + identity scraper hardening

**Source**: follow-up items 9, 10, 19, 20.
**Files**: `systems/scout/sources/clutch.py`, `systems/scout/identity/claude_identity_scraper.py`.

Distinguish empty-page vs CAPTCHA / rate-limit / layout-change in pagination. Handle HTTP 429 / 403 / 503 gracefully with retry + decision_log entry rather than aborting the pull. Land before the first live Clutch run + before identity scraper is pointed at live pages.

**Acceptance**:
- [ ] `decision_log` `scout.source.empty_first_page` decision-type emitted on suspicious empty pages.
- [ ] HTTP 429 / 403 / 503 trigger backoff + retry, not abort.
- [ ] Tests cover both paths (mocked HTTP responses).

## Phase 1: ESP evaluation ✅ COMPLETE (2026-04-27 = Instantly Growth)

### Task 2.1.1: ESP comparison doc — Instantly vs Smartlead vs PlusVibe.ai

**Source**: `feedback_esp_evaluation_pending` harness memory.
**File**: `docs/superpowers/decisions/2026-04-XX-esp-comparison.md` (new).

1-page doc covering 4 criteria across 3 candidates:

**Candidates:**
- **Instantly** — Max Mitcham's primary tool (per 2026-04-26 operator note). Strong cadence engine per the Hans/Max webinar pattern. Recommended in `feedback_cold_email_stack_reference`.
- **Smartlead** — operator's current warming destination + better API per first-pass impression. Domains already accumulating reputation here.
- **PlusVibe.ai** — Max Mitcham's experimental tool (per 2026-04-26 operator note). Treat as the speculative option; needs the most discovery work. Eval its API maturity + community traction; if it's pre-MVP, defer to backlog.

**Criteria:**
1. **API quality** — concrete method comparisons (campaign create, sequence step add, send pacing, reply pull, webhook subscribe).
2. **Deliverability + warming** — all three should pass; flag any concerns.
3. **Cost** — at MVP volume (3-5 accounts × 20 emails/day = 60-100 sends/day per client, scaling).
4. **Cadence engine flexibility** — Instantly's was strong per the Hans/Max webinar; verify Smartlead + PlusVibe match.

**Decision rule** (tiebreakers in order):
1. If PlusVibe.ai is still pre-MVP / unstable, drop it from contention; the choice is between Instantly and Smartlead.
2. If Instantly + Smartlead meet deliverability + cadence parity, API quality is the tiebreaker.
3. Smartlead has the head start (operator's domains warming there) — flip to Instantly only if API gap is material **or** Max Mitcham's reference value (already running on Instantly + Trigify integration patterns documented) outweighs the warming-loss cost.

**Acceptance**:
- [ ] Doc landed at `docs/superpowers/decisions/`.
- [ ] Each candidate has a verdict row (in / out / deferred).
- [ ] Operator picks the ESP (recorded in the doc as a final decision row).
- [ ] Subsequent tasks reference the chosen ESP by name; no remaining "TBD ESP" placeholders in the plan.

## Phase 2: Beacon send foundation

### Task 2.2.1: Schema for send tracking + reply tracking

**File**: `scripts/sql/016_outreach_send_and_reply_schema.sql` (new).

New tables:
- `outreach_send_log` — one row per send attempt (`contact_id`, `draft_id`, `channel`, `account_id`, `esp_message_id`, `sent_at`, `status` ∈ {accepted, sent, bounced, deferred, failed}, `error`, `cost_cents`).
- `outreach_reply` — one row per inbound reply (`contact_id`, `send_log_id`, `received_at`, `body`, `from_email`, `subject`, `classification`, `classification_confidence`, `replied_to_message_id`).
- `send_account` — per-client send-account roster (`client_id`, `account_email`, `provider` ∈ {smartlead, instantly}, `daily_cap`, `current_warming_stage`, `is_active`).
- `send_caps_daily` — running counter (`account_id`, `date`, `sent_count`).

Plus `contacts.touch_state` (text, nullable) for cross-channel state tracking.

**Acceptance**:
- [ ] Migration runs clean.
- [ ] `EnrichBackend.persist_send_attempt()` etc. callable from Python.
- [ ] All new columns have sensible defaults; no breaking change to existing reads.

### Task 2.2.2: Beacon adapter (Instantly v2 API)

**File**: `systems/beacon/__init__.py`, `systems/beacon/adapter.py`, `systems/beacon/skill.py`, `systems/beacon/storage/instantly_adapter.py`.

Target endpoints (validated 2026-04-27 against `developer.instantly.ai/llms.txt`):
- `POST /api/v2/campaigns` — create campaign
- `PATCH /api/v2/campaign-subsequences/:id` — update sequence step content (body + subject)
- `POST /api/v2/leads/bulk` — add leads (1000 per request)
- `POST /api/v2/campaigns/:id/activate` — launch / resume
- `GET /api/v2/emails` — pull replies (rate-limited 20 req/min)
- `POST /api/v2/emails/:id/reply` — send reply

Adapter responsibilities:
- `add_lead_to_campaign(client_id, contact_id, draft_id, account_id) -> esp_message_id`
- `pause_account(account_id, reason)`
- `fetch_replies_since(timestamp) -> list[Reply]` (used by Phase 3 reply ingestion)
- `get_send_stats(account_id, date) -> SendStats` (delivery rate, bounces, etc.)

Mirrors the Scout adapter pattern (Apollo, Trigify): protocol-based dependency injection, in-memory fakes for tests, real backend in `storage/`.

**Acceptance**:
- [ ] Adapter contract documented + tested with FakeESP.
- [ ] Real adapter against Instantly v2 API works against a sandbox/test campaign.
- [ ] Cost discipline: Haiku for any LLM-tokenised step, never Opus, Sonnet only when conversational reasoning is required.

### Task 2.2.3: Send orchestrator (tier + DND + daily caps + cost ceiling + autonomy)

**File**: `systems/beacon/pipeline/send_stage.py`, `systems/beacon/storage/send_caps.py`.

Pipeline stage runs after compose. For each contact with a draft and `status='ready_to_send'`:
1. Check `icp_tier` is in {A, B, C}. Tier D and archived contacts blocked. **Note**: signal presence is NOT a gate — it's a ranking factor only. Signal-having contacts get priority within their tier (better reply-rate odds via more relevant outreach), but no-signal contacts are still sendable as a colder list. Per operator clarification 2026-04-27: "Signals = high quality lead because we can approach them with more relevance to their situation which will equal an overall better reply rate. If they don't have signals, we can still message them, they will just be scored lower and be a colder list."
2. Check global DND (`contacts.dnd_at IS NULL` or contact-level opt-out).
3. Check daily cap on the chosen send account (`send_caps_daily.sent_count < send_account.daily_cap`).
4. Check per-contact 5c cost ceiling (Phase 5).
5. Forward to Beacon adapter.
6. Update `outreach_send_log`, `send_caps_daily.sent_count`, `contacts.status='sent'`, `contacts.touch_state`.
7. Log `decision_type='send_attempt'`.

Autonomy levels respected: at `suggest`, queue the send for human review; at `act_notify`, send + notify; at `autonomous`, send without prompt.

**Acceptance**:
- [ ] Send orchestrator dispatches when all gates pass.
- [ ] Send blocked + decision_log entry written when any gate fails.
- [ ] Daily cap enforced atomically (no race conditions on cap exhaustion).
- [ ] 8+ tests covering the gates (DND, cap exhausted, cost ceiling, autonomy gate, success path, dry_run, ranking-by-signal, etc.).

### Task 2.2.4: ESP webhook ingest endpoint

**File**: `api/routers/beacon_webhooks.py` (new), `api/main.py` (router register).

POST endpoint receives ESP webhook events (sent, bounced, delivered, opened, clicked, replied). Verifies signature via `verify_webhook_signature` (Task 2.0.1). Updates `outreach_send_log.status` + emits `decision_log` entry.

Replies arrive on this webhook too — they're routed to Phase 3's reply runtime via `outreach_reply` insert + a `decision_type='reply_received'` decision_log row.

**Acceptance**:
- [x] Webhook signature verification works (rejects on bad signature).
- [x] All status-changing event types (sent / bounced / deferred / failed / complained) update outreach_send_log.status + emit `send_event` decision_log row.
- [x] Engagement events (opened / link_clicked) acknowledged with no status change + no decision_log emit (signal-to-noise).
- [x] Replies inserted into `outreach_reply` + emit `reply_received` decision_log row → picked up by Phase 3 classifier via `idx_reply_pending_classification` partial index.
- [x] Tests with HMAC-signed payloads cover happy path + bad signature + orphan correlations + unknown event types.
- [x] Real Supabase webhook backend (`SupabaseWebhookBackend`) + `SupabaseSendBackend` + `SupabaseDecisionLogger` (handles both SendStage + WebhookHandler shapes); production wiring via `api.deps.get_beacon_webhook_handler` registered as `dependency_override` in `create_app()`.
- [ ] Operator applies migration 017 (`scripts/sql/017_decision_log_send_event.sql`) to dev Supabase.

## Phase 3: Reply ingestion + classification + auto-respond

### Task 2.3.1: Reply classifier (Haiku)

**File**: `systems/beacon/reply/classifier.py`, `systems/beacon/reply/prompts/classify_reply.md`.

Haiku call returning JSON: `{classification: <enum>, confidence: 0-1, summary: <1-line>, recommended_action: <enum>}`.

Classifications: `positive_interest`, `meeting_request`, `objection_pricing`, `objection_timing`, `objection_authority`, `objection_other`, `negative`, `unsubscribe`, `out_of_office`, `bounce`, `wrong_person`, `spam_marked`, `cannot_classify`.

Recommended actions: `auto_respond`, `escalate_to_human`, `archive`, `add_to_dnd`, `wait_for_human_review`.

Cost target: ~$0.0005/reply (Haiku, ~200 tokens).

**Acceptance**:
- [x] Classifier handles all 13 classification enum values via golden-string fixtures (parametrised test).
- [x] Confidence threshold (0.7) overrides recommended_action to `wait_for_human_review` when below; result reason carries `low_confidence:<score>`.
- [x] Tests cover dry_run + no_api_key + parse-failure + invalid-enum + code-fence-wrapped JSON paths.
- [x] Hallucinated classification labels rejected (`invalid_classification_enum` → cannot_classify + escalation). Hallucinated recommended_action rejected (`invalid_action_enum`).
- [ ] Real Haiku call exercised once with a sample reply (deferred until Phase 3 acceptance run).
- [ ] Per-reply cost rollup integration with cost dashboard (lands in Phase 4 Task 2.4.6).

### Task 2.3.2: Auto-respond runtime (objection handling + booking)

**File**: `systems/beacon/reply/auto_respond.py`, `systems/beacon/reply/templates/objection_*.md` (operator-authored).

For each classified reply with `recommended_action='auto_respond'`:
1. Select the right operator-authored template (objection_pricing.md, objection_timing.md, etc.).
2. Fill placeholders from contact + research_data + client_facts (same machinery as the composer).
3. Validate via `skills/meta/validate-writing.md`.
4. Send via Beacon adapter as a follow-up to the existing thread.
5. If the reply was `meeting_request`, send the Calendly link (per `feedback_voice_agent_backlog_not_rejected`).
6. Log `decision_type='reply_classification'` + `decision_type='send_attempt'` (the auto-response).

Templates are operator-authored per `feedback_copy_architecture` — AI fills placeholders only.

**Acceptance**:
- [x] 6 skeleton templates landed at `data/reference/sequences/creative_branding/components/reply_responses/` (objection_pricing/timing/authority/other + meeting_request + positive_interest). Operator can revise.
- [x] Auto-respond fires for confident objections + meeting_request + positive_interest; skips with `skipped:not_auto_respond` for everything else (negative → archive, unsubscribe → add_to_dnd, etc., handled upstream by the classifier action).
- [x] 19 tests in `test_auto_respond.py` covering each template render + skip/failure paths (validator-fail, no-template, no-calendly-url, dry-run, responder-error). 6 production-template smoke tests in `test_auto_respond_production_templates.py` ensure deployed templates pass the validator.
- [ ] `ReplyResponder` Protocol production wiring against Instantly's `POST /api/v2/emails/:id/reply` endpoint — deferred follow-up.
- [ ] Calendly URL stored in `client_facts.calendly_url` per client (operator-side data entry).

### Task 2.3.3: Human escalation queue + Slack/web app surface

**File**: `api/routers/inbox.py` (new), `systems/beacon/reply/escalation.py`.

Replies that need human attention land in `escalations` table + Slack notification (per `feedback_client_ux`: web app or Slack, never Telegram). Operator triages, optionally responds via web app, marks resolved.

Defer the Next.js web app side to a later plan; this task only ships the **API + Slack** surface so escalations reach the operator.

**Acceptance**:
- [x] Escalations land in `escalations` table (migration 018) + Slack channel via incoming-webhook POST.
- [x] Operator marks resolved via `POST /api/inbox/escalations/{id}/resolve` (cron_secret-gated for v1).
- [x] Slack delivery is best-effort: a Slack outage does NOT lose an escalation (DB insert + decision_log fire first; Slack failure is logged + swallowed).
- [x] When `settings.slack_webhook_url` is unset, EscalationRuntime is initialised with `slack_notifier=None` and the Slack path is a silent no-op.
- [x] Also exposes `POST /api/inbox/escalations/{id}/dismiss` + `GET /api/inbox/escalations?client_id=<id>` for the operator triage UX.
- [ ] Operator applies migration 018 to dev Supabase.
- [ ] Operator-side: set `SLACK_WEBHOOK_URL` env var to enable Slack notifications (optional).
- [ ] Wire EscalationRuntime call sites: WebhookHandler (low_confidence_reply / cannot_classify_reply / spam_marked_reply / out_of_office_reply) + AutoRespondRuntime (auto_respond_failed). Deferred follow-up.

### Task 2.3.4: 90-day cool-off + round-based re-entry

**File**: `systems/beacon/reply/cool_off.py`.

Per `feedback_surround_sound_architecture`: contacts who don't reply within a sequence go into 90-day cool-off, then re-enter as round 2 (different opening, optionally different channel).

Round-tracking via `contacts.sequence_round` (already exists; just used).

**Acceptance**:
- [x] After 90 days of no-reply, contact's `sequence_round` increments + status reset to `'ready'` to enable a new send cycle. Two-phase runtime (`enter_cool_off_for_idle` + `re_enter_after_cool_off`) plus combined `run_cycle`. Max-rounds cap (default 4) → marks contact `dead` with `reason='max_rounds_reached'` instead of advancing.
- [ ] Round 2+ sequences select a different subject/icebreaker variant pool than round 1. **Deferred to Phase 5 follow-up** — composer-side change touching the bandit-pull + variant-selection logic; runtime-only Task 2.3.4 doesn't couple to it.
- [x] 16 tests cover both phases (CoolOffRuntime unit + SupabaseCoolOffBackend with FakeSupabaseClient): cool-off entry filters, re-entry transitions, max-rounds dead path, blocked-status exclusions.
- [ ] Operator applies migration 019 (`scripts/sql/019_contacts_cool_off.sql`) to dev Supabase.
- [ ] Operator-side: schedule periodic `run_cycle` invocation (cron daily for v1).

## Phase 4: Cost optimiser foundation

Closes the gap from today's $0.01-0.03/contact toward the $0.002 target.

### Task 2.4.1: Signal-gated Deep Research

**File**: `systems/scout/enrich/orchestrator.py` (modification).

Currently `claude_deep_research` runs for every tier-A/B/C contact. Per `feedback_plan15_cost_optimizations`: only fire when Trigify + structural signals are absent. Tier 1-3 icebreaker contacts skip Deep Research entirely; only Tier 4 fallback contacts need the website extract.

**Acceptance**:
- [ ] `_should_run_deep_research(contact, merged_research_data) -> bool` predicate at orchestrator level.
- [ ] Per-contact cost drops to ~$0.005 when signal-gating active (verified via decision_log spend rollup).
- [ ] Tests: contact with trigger_event signals → DR skipped; contact with no signals → DR runs.
- [ ] Quality regression: a 20-contact cohort produces equivalent or better icebreaker quality vs always-on DR (manual operator review against the 4-tier ladder).

### Task 2.4.2: Per-contact cost rollup view

**File**: `scripts/sql/018_per_contact_cost_rollup.sql` (new).

`contact_cost_rollup` SQL view aggregating `decision_log.context.cost_cents` per `contact_id`. Plus an RPC `get_contact_cost(contact_id) -> int_cents` for Python callers.

**Acceptance**:
- [ ] View returns total spend per contact, broken down by stage.
- [ ] RPC callable from Python; tests use a fixture contact.
- [ ] Existing tier-level budget queries still work.

### Task 2.4.3: Per-contact 5c hard ceiling

**File**: `systems/scout/budget/per_contact_ceiling.py` (new), wired into orchestrator + composer.

Before each LLM-spending step, check `get_contact_cost(contact_id)`. If approaching 5c, halt further enrichment + flag the contact for operator review (`status='cost_ceiling_hit'`).

**Acceptance**:
- [ ] Contact halted at 5c spend; doesn't continue to compose.
- [ ] Operator review queue gets the flagged contact.
- [ ] Configurable per-tier (`client_config.per_contact_cost_ceiling_cents` JSONB; default 5 for all tiers).
- [ ] 6+ tests covering halt-before-DR, halt-before-icebreaker, halt-before-compose, edge cases.

### Task 2.4.4: Operator cost dashboard (CLI)

**File**: `scripts/cost_dashboard.py` (new).

CLI tool: `uv run python scripts/cost_dashboard.py --client-id=kirsten-client-zero --days=7`.

Outputs:
- Cost-per-lead (this period) vs $0.002 target.
- Cost-per-tier breakdown.
- Top 10 most-expensive contacts.
- Adapter-level spend rollup.
- Tier budget remaining.

Web app version is backlog; CLI ships now.

**Acceptance**:
- [ ] Tool runs, produces a readable summary.
- [ ] Numbers reconcile against `client_config.tier_spent_cents` and `decision_log` rollups.

### Task 2.4.5: Per-field enrichment coverage rollup view

**Source**: 2026-04-27 scope expansion (operator's "90%+ enrichment" target).
**File**: `scripts/sql/019_enrichment_coverage_rollup.sql` (new).

SQL view + RPC that aggregates per-contact enrichment-field presence by `(client_id, niche, icp_tier)`:
- `email_present + email_verified` (ZeroBounce status)
- `linkedin_url` non-null
- `phone` non-null
- `domain_resolved` (identity stage)
- `research_data.trigger_events` non-empty (Trigify hit rate)

Targets per `feedback_cost_optimiser_continuous_concern` (operator decision 2026-04-27): email + LinkedIn ≥90% across Tier A/B/C; phone ≥90% on Tier A only (gated per `feedback_enrichment_tiers`).

**Acceptance**:
- [ ] View returns one row per `(client_id, niche, icp_tier)` with each field's presence count + percentage.
- [ ] RPC `get_enrichment_coverage(client_id)` callable from Python.
- [ ] Tests against the existing dev cohort (kirsten-client-zero, 31 contacts) produce sane numbers.

### Task 2.4.6: Coverage dashboard CLI extension

**File**: `scripts/cost_dashboard.py` (extend existing — Task 2.4.4 ships first).

New `--coverage` flag adds a coverage report alongside the cost report:
- Per-tier per-field presence vs the 90% target.
- Adapter-level coverage breakdown (which adapter found the email / LinkedIn / phone — informs which is the weak link).
- Highlights tiers/fields under the target.

**Acceptance**:
- [ ] `uv run python scripts/cost_dashboard.py --client-id=kirsten-client-zero --coverage` produces a readable table.
- [ ] Numbers reconcile with the SQL view from Task 2.4.5.
- [ ] Gap-source identification works (e.g. "Tier B email coverage is 78% — Apollo found 62%, Hunter found 14%, Claude scraper found 2%, missing 22%").

## Phase 5: Optimizer agent v1 (read-only recommendations)

Closes the learning loop. v1 is **recommendations-only** — operator approves before changes ship. Auto-apply (v2) deferred to a future plan once v1 has usage history showing the recommendations are reliable.

### Task 2.5.1: Weekly review job

**File**: `agents/optimizer.md` (new agent persona), `systems/optimizer/__init__.py`, `systems/optimizer/weekly_review.py`, `scripts/run_optimizer_weekly.py`.

Cron-scheduled (e.g. Monday 6am operator-local) job that produces a per-client weekly report covering:

1. **Cost analysis** (from Phase 4 rollup): cost-per-lead, cost-per-reply, cost-per-meeting, week-over-week trend, vs target.
2. **Variant performance**: which subject_line / icebreaker / bridge / pain_hook / cta variants are winning. Bandit selection win-rate breakdown. Recommendations: raise allocation on top performers, retire chronically-bottom variants.
3. **Adapter ROI**: which enrichment adapters' signals correlate with positive replies. E.g. if Trigify-sourced contacts reply 3× more than Apollo-only contacts, recommendation: weight Trigify higher in scoring.
4. **Send-time analysis** (basic): which days/hours produce the highest reply rates. Recommendation: shift cadence if signal is strong.
5. **Cool-off / re-entry queue**: contacts ready for round 2 next week.

Each recommendation has a confidence score + the underlying numbers. Operator reviews + approves before changes apply.

**Acceptance**:
- [ ] Optimizer can be invoked manually via `uv run python scripts/run_optimizer_weekly.py --client-id=kirsten-client-zero`.
- [ ] Report renders to markdown (committed to `data/captures/optimizer/<date>.md` for record).
- [ ] Slack notification with summary + link to full report.
- [ ] 8+ tests covering each analysis section against fixture data.

### Task 2.5.2: Recommendation persistence + approval flow

**File**: `scripts/sql/019_optimizer_recommendations.sql` (new), `api/routers/optimizer.py` (new).

Schema:
- `optimizer_recommendation` — one row per recommendation (`client_id`, `category`, `payload` JSONB, `confidence`, `created_at`, `status` ∈ {pending, approved, rejected, expired}, `applied_at`).

API endpoints:
- `POST /api/optimizer/recommendations/<id>/approve` — operator approves; system applies the recommendation (e.g. updates variant win_rate prior).
- `POST /api/optimizer/recommendations/<id>/reject` — dismissed.
- Auto-expire after 7 days if not approved.

**Acceptance**:
- [ ] Recommendations persist across runs.
- [ ] Approve/reject endpoints work + trigger the underlying change.
- [ ] Expiry job retires stale recommendations.
- [ ] Tests cover the full lifecycle.

### Task 2.5.3: Bandit weight adjustments + autonomy promotions

**File**: `systems/optimizer/applicators.py`.

When a recommendation is approved, system applies it. Categories:
- `bandit_weight_adjustment` — raises/lowers a variant's prior win_rate.
- `variant_retirement` — flips status from approved to retired (composer skips).
- `adapter_score_weight` — adjusts client_config scoring weights for an adapter signal.
- `autonomy_promotion` — recommends raising autonomy level on a stage (suggest → draft → act_notify → autonomous) when criteria met (50+ decisions, 80%+ success, 30+ days at level).

Autonomy promotions are gated by the existing autonomy_rules CHECK constraints; the Optimizer just surfaces "ready for promotion" — operator still approves explicitly per CLAUDE.md guardrails.

**Acceptance**:
- [ ] Each applicator has a tested success path + a tested rollback path.
- [ ] Autonomy promotion never auto-applies without operator approval.

### Task 2.5.4: Cold email copy grader skill (operator-interactive)

**Source**: 2026-04-27 scope expansion. Operator-interactive per `feedback_max_credits_vs_api_boundary`.
**File**: `skills/operations/grade-cold-email-copy.md` (new).

Skill that runs inside Claude Code (Sonnet via Max-plan credits). Inputs: a draft (variant text or rendered email body) + optional prior reply-rate context. Outputs: predicted reply rate (0.0-1.0), tier (A/B/C/D), 3-line critique (what works, what doesn't, what to change).

The skill calls `Agent` with `subagent_type` to run the grading sub-agent. No Anthropic SDK code in the daemon. No per-call cost beyond the operator's Max subscription.

When run on a persisted draft: write grade to a new `outreach_drafts.predicted_grade` jsonb column (schema migration alongside this task). When run on a variant before approval: write to a stand-alone YAML file the operator commits to `data/captures/copy_grades/`.

**Acceptance**:
- [ ] Skill loads + runs successfully against a sample variant.
- [ ] Grade JSON shape: `{predicted_reply_rate: float, tier: "A"|"B"|"C"|"D", critique: [str, str, str]}`.
- [ ] Persisted-draft path writes to `outreach_drafts.predicted_grade`.
- [ ] Variant-only path writes to `data/captures/copy_grades/<variant_key>-<timestamp>.yaml`.
- [ ] No Anthropic API call; runs purely via the Claude Code Agent tool.

### Task 2.5.5: Copy grader learning loop (daemon weekly job)

**Source**: 2026-04-27 scope expansion.
**File**: `systems/optimizer/grader_calibration.py` (new), extends `weekly_review.py` from Task 2.5.1.

Weekly job that:
1. Pulls all `outreach_drafts` with `predicted_grade` set + an associated `outreach_reply` outcome from the past 30 days.
2. Computes calibration: did high-tier predictions correlate with replies? What was the AUC / Brier score?
3. Surfaces drift in the Optimizer weekly report: "Grader predicted Tier A drafts at 12% reply rate; actual was 4%. Recommend recalibrating tier-A threshold downward."
4. Operator approves the recalibration before grader weights update (operator-approval flow shared with Task 2.5.2).

**Acceptance**:
- [ ] Calibration metrics land in the weekly report.
- [ ] Recommendation persistence works (uses the same approval flow as Task 2.5.2).
- [ ] Tests with fixture predicted/actual pairs cover the Brier-score branch + the no-data branch.

### Task 2.5.6: ICP filter sub-agent skill (operator-interactive)

**Source**: 2026-04-27 scope expansion. Operator-interactive per `feedback_max_credits_vs_api_boundary`.
**File**: `skills/operations/filter-icp-list.md` (new).

Skill that runs inside Claude Code (Sonnet via Max-plan credits). Input: a CSV path with company name + description + website + size signals. For each row, output: `fit ∈ {yes, maybe, no}` + 1-line reasoning.

Uses `Agent` with `subagent_type=general-purpose` to run a sub-agent that loads `client_config.icp` + the row data, returns the verdict.

Output format: annotated CSV with two new columns (`icp_fit`, `icp_reasoning`). Operator imports surviving rows (`fit=yes`) into the daemon via `scripts/ingest_preresolved_contacts.py`.

**Acceptance**:
- [ ] Skill runs against a 10-row sample CSV.
- [ ] Each row has `icp_fit` + `icp_reasoning` populated.
- [ ] No Anthropic API call.
- [ ] Operator can re-import the annotated CSV cleanly.

### Task 2.5.7: Screen-stage uncertain-zone LLM augment (daemon, API)

**Source**: 2026-04-27 scope expansion. Daemon-autonomous per `feedback_max_credits_vs_api_boundary` (per-contact runtime).
**File**: `systems/scout/pipeline/screen.py` (modify).

When the rule-based `icp_score` lands in the uncertain zone (default 40-60, configurable per `client_config.icp.uncertain_zone`), invoke a Haiku-tier LLM judge that:
1. Reads the contact's company description + size + industry from `raw_data` + `research_data`.
2. Reads `client_config.icp` (titles, geographies, size band, positive + negative examples).
3. Returns `nudge ∈ {-15, -5, 0, +5, +15}` to apply to the rule-based score.
4. Logs the judgment to `decision_log` with `decision_type='icp_threshold'` + reasoning.

Cost-bounded: only ~10-20% of contacts hit the uncertain zone, so per-cohort cost stays low (~0.1c each via Haiku). Maintains tier_budget tracking like other adapters.

**Acceptance**:
- [ ] Contact with rule-score=50 fires the LLM judge; judgment lands in `decision_log`.
- [ ] Final score = rule_score + nudge.
- [ ] Contact with rule-score=20 (clearly archive) skips the judge — no LLM call.
- [ ] Contact with rule-score=85 (clearly Tier A) skips the judge.
- [ ] Tests: 4 contacts at scores {20, 45, 55, 90}; LLM fires for 2 of them.
- [ ] Per-tier cost increase measured against the cost dashboard from Task 2.4.4.

## Phase 6: Productisation deployment script

### Task 2.6.1: New-client bootstrap script

**File**: `scripts/provision_new_client.py` (new).

Single command spins up a new client AIOS:
```
uv run python scripts/provision_new_client.py \
  --client-id=acme-co-zero \
  --client-name="Acme Co" \
  --niche=creative_branding \
  --offer-label=aios_scout_deployment \
  --tier-budgets-cents='{"A":200,"B":100,"C":50,"D":25}'
```

Steps:
1. Validate args (no whitespace/special chars in client_id, niche must exist in `data/reference/sequences/`, etc.).
2. Run all migrations against the target Supabase project.
3. Insert `clients` + `client_config` + `autonomy_rules` rows.
4. Bootstrap empty `context/<client_id>/` + `data/knowledge/personal/<client_id>/` + `data/knowledge/company/<client_id>/`.
5. Copy `data/knowledge/experts/` baseline if not already present.
6. Print a checklist of human-only steps (write personal context, write company facts, approve component variants, etc.).

Per `feedback_per_company_aios_silo`: foundation (skills/rules/departments/agents/systems) is shared template; context/ + data/ content is per-client. The script bootstraps the per-client silo.

**Acceptance**:
- [ ] Script provisions a fresh client end-to-end.
- [ ] All 7 acceptance preflight checks pass against the new client.
- [ ] Human-only checklist surfaces clearly at the end.
- [ ] Idempotent: re-running for the same client reports "already provisioned" cleanly.
- [ ] Tests exercise the validation logic + the migration runner.

### Task 2.6.2: Client config validator

**Source**: follow-up item 26.
**File**: `systems/scout/pipeline/validate_config.py` (new), called by `provision_new_client.py` + on every `client_config` write.

Validates:
- `client_config.icp.titles` entries ≥4 chars (no "CEO" substring footgun).
- `client_config.icp.geographies` not in known-ambiguous-substring set ({"US", "UK", "AU"}).
- `client_config.tier_thresholds`: A > B > C > D > archive monotonicity.

**Acceptance**:
- [ ] Validator catches all 3 footgun classes.
- [ ] Tests cover each footgun + happy path.
- [ ] Wired into provisioning + client_config update endpoint.

## Phase 7: Acceptance + merge + tag

### Task 2.7.1: End-to-end acceptance run

Single client (kirsten-client-zero), single contact, full path: pull → score → screen → identity → enrich → compose → send → reply received → reply classified → auto-respond. Verify each stage wrote the right `decision_log` entries; verify outreach_send_log + outreach_reply rows.

Cost benchmark: 100-contact dry-run cohort produces a per-contact cost ≤ $0.005 (signal-gated DR active, 5c ceiling enforced).

**Acceptance**:
- [ ] Full end-to-end pipeline run captured in `data/captures/plan2-acceptance/`.
- [ ] Cost benchmark report in same dir.
- [ ] Test suite green: target 1100+ tests passing (936 baseline + ~150 new in Plan 2 phases).

### Task 2.7.2: Merge `feat/plan-2-beacon` into main + tag `plan-2`

PR for the entire branch against main; review; merge `--no-ff`; tag `plan-2` at the merge SHA; update `memory/INDEX.md` to mark Plan 2 closed; final session log entry.

**Acceptance**:
- [ ] `git tag plan-2` exists at the merge commit.
- [ ] `memory/INDEX.md` shows Plan 2 as `Done` and Plan 3 ready to start.

## Critical files to create/modify (summary)

| Phase | Files |
|---|---|
| 0 | `api/middleware/verify_signatures.py`, `tests/test_api/test_webhook_auth.py` (new), `scripts/sql/015_decision_log_check_constraint_extensions.sql` (new), `api/asgi.py` (new), `api/main.py` (refactor), `Procfile`/`railway.toml` (paths), `systems/scout/sources/clutch.py`, `systems/scout/identity/claude_identity_scraper.py` |
| 1 | `docs/superpowers/decisions/2026-04-XX-esp-comparison.md` (new — 3-way Instantly/Smartlead/PlusVibe.ai) |
| 2 | `scripts/sql/016_outreach_send_and_reply_schema.sql` (new), `systems/beacon/` (new package), `api/routers/beacon_webhooks.py` (new), `api/main.py` (register router) |
| 3 | `systems/beacon/reply/` (new), `data/reference/sequences/<niche>/components/reply_responses/` (operator-authored), `api/routers/inbox.py` (new) |
| 4 | `systems/scout/enrich/orchestrator.py` (modification), `scripts/sql/017_per_contact_cost_rollup.sql` (new), `systems/scout/budget/per_contact_ceiling.py` (new), `scripts/cost_dashboard.py` (new) |
| 5 | `agents/optimizer.md` (new persona), `systems/optimizer/` (new package), `scripts/run_optimizer_weekly.py` (new), `scripts/sql/018_optimizer_recommendations.sql` (new), `api/routers/optimizer.py` (new) |
| 6 | `scripts/provision_new_client.py` (new), `systems/scout/pipeline/validate_config.py` (new) |
| 7 | `data/captures/plan2-acceptance/` (gitignored evidence), `memory/INDEX.md` |

## Reuse from existing code

- **Composer + research_selector** stays unchanged — the rendered draft is the input to Phase 2's send orchestrator.
- **Decision log + autonomy gate + budget tracker** are reused across Beacon stages identically to Scout stages.
- **Component variants schema** (subject/icebreaker/bridge/...) extends to `reply_response` component type for operator-authored objection templates.
- **Plan 1 acceptance harness** (`scripts/plan1_acceptance.sh` + `_preflight.py` + `_verify.py`) is the model for `plan2_acceptance.sh`.
- **`feedback_value_first_efficiency`** governs all vendor swap decisions in Phase 5.

## Verification

End-to-end after all phases:

1. **Test suite green**: `pytest -q tests/` reports 0 failures (~1100+ tests).
2. **Beacon email end-to-end**: 1 contact sends, replies, gets classified, gets auto-responded.
3. **Cost benchmark**: 100-contact dry-run cohort at ≤ $0.005/contact.
4. **Optimizer weekly review**: report generates against the test data; recommendations land in `optimizer_recommendation` table; one approval applies cleanly.
5. **Productisation**: provision a fresh test client end-to-end, run preflight clean.
6. **No em dashes anywhere new**: `grep -l '—' $(git ls-files data/reference/sequences/) systems/beacon/reply/templates/` returns nothing.

## What this plan explicitly does NOT do

- Does not build LinkedIn outbound — Plan 3 (operator decision 2026-04-26: prioritise email full-loop first).
- Does not build SMS / WhatsApp / voicemail / letters channels — Plan 3.
- Does not auto-apply Optimizer recommendations — Phase 5 ships read-only recommendations only; auto-apply is v2 (future plan).
- Does not build the client web app — backlog.
- Does not implement the AI voice booking agent — backlog per `feedback_voice_agent_backlog_not_rejected`.
- Does not enable autonomous send by default — clients start at `suggest` autonomy and earn `act_notify` / `autonomous` over time per the autonomy progression rules.

## Order of execution

1. Phase 0 (hardening) — can run in parallel chunks; one PR or split into 2-3.
2. Phase 1 (ESP eval) — sequential; operator picks before Phase 2 starts.
3. Phase 2 (Beacon email foundation) — sequential within phase; depends on Phase 1.
4. Phase 3 (Reply runtime) — sequential; depends on Phase 2.
5. Phase 4 (Cost optimiser foundation) — depends on Phase 2 schema (per-contact rollup needs send_log + reply tables).
6. Phase 5 (Optimizer agent v1) — depends on Phase 4 (uses cost rollup) + Phase 3 (uses reply data).
7. Phase 6 (Productisation) — can run early (after Phase 0) since it's mostly orthogonal; but operator may prefer to defer until Phase 5 done so the new-client bootstrap reflects the latest cost defaults.
8. Phase 7 (acceptance + merge) — final.

Estimated calendar: 3-4 weeks at the operator's typical execution cadence (down from 4-5 in the prior LinkedIn-included version).
