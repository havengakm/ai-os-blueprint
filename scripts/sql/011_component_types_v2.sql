-- Expand component_variants.component_type CHECK constraint to include
-- the v2 AIDA-structured component types introduced on the
-- fix/enrich-compose-pipeline-bugs branch.
--
-- v1 types: subject_line, icebreaker, pain_hook, offer_frame, cta, signature
-- v2 adds:  who_i_am, credibility
--
-- pain_hook is kept in the allowed set (still a valid optional type per the
-- composer refactor; creative_branding just doesn't use it). New niches can
-- still author pain_hook variants without a schema change.

ALTER TABLE component_variants
    DROP CONSTRAINT IF EXISTS component_variants_component_type_check;

ALTER TABLE component_variants
    ADD CONSTRAINT component_variants_component_type_check
    CHECK (component_type IN (
        'subject_line',
        'icebreaker',
        'pain_hook',
        'offer_frame',
        'cta',
        'signature',
        'who_i_am',
        'credibility'
    ));
