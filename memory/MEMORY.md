# Project Memory

Long-term knowledge about this project. Rarely changes. Read first at session start.

Source of truth for operating principles: `CLAUDE.md` (repo root, always loaded). This file holds the project context layer that builds on those principles.

## Business Context

- **Project name:** AIOS (AI Operating System) blueprint.
- **Company this deployment runs for:** Clymb (Kirsten's own company). AIOS is productised; other companies get their own siloed deployments.
- **Goal:** Unattended autonomous operation of a business: outbound, inbound, operations, content, finance, legal, admin. Daemon-first, not endpoint-first.
- **Product positioning:** An autonomous SDR system (Plan 1) expanding to a full virtual company (Plans 2 onward). Differentiated vs GHL, HeyReach, Clay, Outreach via expert-framework-led strategy + continuous learning + niche specialisation.
- **Target user:** Founder-led and small-team B2B companies, 1 to 50 employees, where founders or senior leaders sell. See `data/knowledge/company/icp.md`.

## Technical Stack

- **Language:** Python 3 for systems + scripts. Markdown for skills, rules, manifests, knowledge.
- **LLM runtime:** Anthropic SDK. Haiku for batch/pipeline, Sonnet for agent runtime and complex reasoning. Never Opus.
- **Database:** Supabase (Postgres). Schemas in `scripts/001_foundation.sql`.
- **Scrapers + research:** Python + Anthropic SDK in `systems/scout/sources/`. Prompts in `data/reference/research_prompts/`.
- **Vendor stack (current, lean):** Manus Pro + Apollo + Lusha + ZeroBounce (~$135 to 165 per month for first 1 to 3 clients). Clay rejected. Cognism / Hunter only on escalation triggers.
- **Cold email:** Instantly (evaluated as vendor before building a send engine).
- **Signal detection:** Trigify (CLI over MCP for token efficiency).
- **Voice agents:** REJECTED. High-ticket calls are human-only.

## Architecture Summary

**Three layers, bottom up:**

1. **Context** = WHAT THE DEPLOYMENT IS. Brand, integrations, active projects. Loaded from `context/`. Per-company silo, never shared.
2. **Data** = WHAT THE DEPLOYMENT KNOWS. Knowledge (personal/company/experts), captures, plans, outputs, reference. In `data/` and Supabase.
3. **Systems** = THE LIMBS. Outbound prospecting, inbound response, content, ad management, reporting. Each system reads from context + data, logs decisions, writes outcomes back. Lives in `systems/`.

No system works in isolation. Every system makes the foundation smarter.

**Each system contract:**

1. Extends `BaseSystem` with a single entry point via `skill.py`
2. Reads from foundation (context + knowledge + past decisions). Mandatory.
3. Logs every significant action to `decision_log`. Mandatory.
4. Checks autonomy level before acting. Mandatory.
5. Writes outcomes back so other systems can learn from them
6. Has a README explaining what it does, what data it uses, how to enable

**Skill library is three-tier:**
- **Capabilities** (atomic, one input to one output) in `skills/<category>/`
- **Composites** (3 to 8 chained capabilities) in `skills/composites/`
- **Playbooks** (end-to-end with human gates) in `skills/playbooks/`

15 capability categories: meta, market-intelligence, offer-positioning, gtm, outbound, inbound, copywriting, sales, customer-success, data-analytics, revops-automation, finance, legal, operations, admin, brand.

Operational specialisation lives in the deployment repo's `client_config.yaml` (per Phase 3 of the productised AIOS plan), not in monorepo-level `departments/` manifests. Vertical-specific seed content lives in `<client>-brain` Obsidian vault.

## File Layout

```
context/          : per-company silo identity (brand, integrations, active projects). Never shared across deployments.
data/             : knowledge (personal/company/experts/verticals), captures, plans, outputs, reference (sops, sequences, frameworks).
memory/           : MEMORY.md (this file, stable context), INDEX.md (recent decisions + open loops), sessions/ (daily logs).
rules/            : global guardrails (writing standards) every content-producing skill enforces.
skills/           : three-tier library (capabilities/, composites/, playbooks/). Universal across deployments.
aios/             : monorepo-side dependency wiring (`dependency_container.py`) + daemon code (`daemon/`). Foundation modules now installed from `aios-foundation` pip package (see Phase 1 PR #4).
systems/          : the limbs. scout, beacon, optimizer, future linkedin/meta_ads/auditor.
scripts/          : utilities: migrations (sql/), provisioning, dashboards.
api/              : webhooks + pipeline triggers.
config/           : environment + API key loading.
.claude/commands/ : the five operational commands (build-context, create-plan, decide, implement, prime).
```

**Library tier (universal, productised):** `skills/`, `rules/`, `aios/foundation/`, `scripts/sql/` migrations, `data/knowledge/verticals/<vertical>/` templates. Same across every client.

**Activation tier (per-deployment):** `<client>-deployment/client_config.yaml` + Supabase rows seeded at provisioning. Picks which `aios-*` system repos run + which skills activate for this deployment.

**Content tier (per-deployment, never shared):** `context/<client_id>/`, `data/knowledge/personal/<client_id>/`, `data/knowledge/company/<client_id>/`, plus per-client Supabase rows. The deployment's identity + facts.

## Development Preferences

- **Writing:** `rules/global-writing-guardrails.md` enforced by `skills/meta/validate-writing.md`. No em dashes, no superfluous adjectives, no filler, no buzzwords, no clichés, no metaphors. Short sentences, active voice, plain English. Cold emails under 75 words, one idea, one ask.
- **Code style:** Simplest robust solution wins. Avoid unused abstractions, defensive branches without a live threat, excessive logging, hypothetical extension points. See `feedback_simplicity_over_complexity` in harness memory.
- **Communication with operator:** Lead with the answer, not the reasoning. No preamble. One sentence if one sentence will do.
- **Cost:** Haiku for batch (~$0.0003 per contact). Sonnet for conversations. Never Opus. `--limit 2` + `--dry-run` before any write operation.
- **Tools:** Prefer CLI / REST over MCP for token efficiency. MCP only when the CLI cannot cover.

## Autonomy distribution target: 60 / 30 / 10

For a mature AIOS, work across all action types should land roughly:

- **~60% autonomous.** System acts and logs. Operator reviews in weekly recap, not in real time.
- **~30% AI-assisted with human review.** System drafts. Operator approves before commit.
- **~10% manual.** Strategic decisions, novel client situations, escalations.

This is a target, not a quota. Brand-new deployments start near 0/10/90 (everything `suggest`-level) and progress through the autonomy ladder over 30+ days per action type. The 60/30/10 ratio is the steady state for a Compounding-stage deployment (per Four-Cs audit).

A weekly drift check belongs in the Friday operator review: if too much work is stuck at manual, automation is not progressing. If too much is autonomous and quality is dropping, a downgrade is overdue. Reference: `feedback_autonomous_agent_goal` + Nate Herk AI's `/audit` framework (adopted 2026-05-04).

## Hard Rules

From `CLAUDE.md`:
- Never commit credentials.
- Never send outreach without a verified buying signal.
- Never send outreach before human review on a new deployment.
- Never contact opted-out contacts.
- Every outreach fact must exist in verified data (no hallucination).
- Three QA failures = flag for human review.

From memory:
- Productised service, no custom code per client. Customisation lives in the per-deployment repo (`<client>-deployment`) + the per-client Obsidian vault (`<client>-brain`). Never in shared-core code.
- Per-company silo. `context/` + `data/` content NEVER copies across deployments.
- Human-written templates with AI-filled placeholders, never AI-generated copy.
- Web app (Next.js + Supabase) as client-facing UX. Slack alternative. Telegram operator-only.
- AI voice agent rejected permanently.

## Lessons Learned

- **$900 SMS overage (past incident):** Tier-based cost defaults with soft alert 70%, hard alert 90%, auto-pause 100%. See `feedback_cost_management`.
- **Mocked-test migration failure (past incident):** Integration tests hit real database, not mocks.
- **Atomic vs hybrid skills (2026-04-22):** Initial "hybrid broad + narrow" skill proposal was rejected in favour of atomic single-purpose. Composites tier added for chained orchestrations. Three-tier model adapted from Gooseworks public catalog.
- **Context vs knowledge muddle (2026-04-22):** Loose "personal" files living under `context/` root created ambiguity. Tightened rule: `context/` = identity, `data/knowledge/` = facts. Migrated `personal*.md`, `voice.md`, `business-frameworks.md`, and `context/projects/clymb/*` accordingly.

## References

- `CLAUDE.md`: operating principles, autonomy framework, hard rules.
- `~/.claude/projects/.../memory/MEMORY.md`: harness-level persistent memory (feedback, preferences, references).
- `docs/superpowers/decisions/`: formal decision docs.
- `data/knowledge/personal/`: Kirsten's operator principles, voice, bio.
- `data/knowledge/company/`: Clymb's facts (services, pricing, ICP, strategy, metrics, research).
- `skills/README.md`: three-tier skill model + frontmatter convention + tag vocabulary.
