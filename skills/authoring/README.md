# Authoring skills

Skills that create or update content — templates, variants, offers, sequences, knowledge entries.

## Planned skills (Plan 1 Scout-relevant)

- `compose-draft.md` — given a contact + niche + offer + round, bandit-select one variant per component type, fill placeholders, write `outreach_drafts` row with `component_selections` JSONB. (Plan 1 Task 15)
- `write-component-variant.md` — operator-facing: add a new subject line / icebreaker / pain_hook / offer_frame / CTA / signature variant to the component registry. Walks operator through offer-score-27-constraints validation. (Plan 1 Task 13)
- `copywriting.md` — invoked by composer when generating placeholder content. Loads Saraev + Sapp + Hormozi frameworks from knowledge_base via `retrieve_knowledge()`. Tells the generator WHICH framework to apply for the current (niche, offer, pain-angle) combination. (Plan 1 Task 14)
- `copy-editing.md` — QA sub-agent skill invoked on every composed draft before `outreach_drafts.status` flips to `rendered`. Flags: factual claims without `raw_data` / `research_data` support, tone mismatch vs brand guidelines, length violations, banned-words usage. (Plan 1 Task 15)
- `brand-guidelines.md` — per-client brand voice + tone + banned-words + punctuation conventions. Loaded from `context/{client}/brand.md` at onboarding. Referenced by `copy-editing.md` + `copywriting.md`. (Plan 1 Task 16)
- `email-sequence.md` — sequence-level authoring guide. Teaches how to write a YAML sequence DAG for a niche-round-angle combo. References Sapp's 6-step close arc for structural pacing + Saraev's touch-count heuristics. (Plan 2)
- `write-yaml-sequence.md` — mechanical sequence-YAML author + validator. Validates DAG integrity, channel availability, event triggers. (Plan 2)
- `score-offer-27-constraints.md` — run a proposed offer through the 27-constraint offer-score rubric. Reference `feedback_offer_score_framework`. (Plan 2)
- `refine-knowledge-entry.md` — operator-facing: add or update an expert-framework entry in the knowledge base. Re-embeds on save. (Plan 7)
- `propose-new-niche-config.md` — when performance signals a new niche is worth carving, propose ICP + weights + tier_thresholds delta. Operator approves. (Plan 7)

## Future-system skills (Content OS, Ads, Landing Page OS — see top-level skills/README.md)

Authored when those systems ship. Reference library:
- **Content OS:** `blog-research.md`, `blog-outline.md`, `blog-write.md`, `blog-status.md`, `schema-markup.md`, `programmatic-seo.md`, `marketing-ideas.md`, `marketing-psychology.md`
- **Ads:** `paid-ads.md`, `launch-strategy.md`, `audience-research.md`, `creative-iteration.md`
- **Landing Page OS:** `page-cro.md`, `popup-cro.md`, `paywall-upgrade-cro.md`, `form-cro.md`, `free-tool-strategy.md`, `frontend-design.md`
- **Cross-cutting:** `pricing-strategy.md` (informs every offer discussion across systems)
