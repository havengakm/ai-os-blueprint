-- 014_body_template_component_type.sql
--
-- Plan 1.5 Task 1.5.6: add the `body_template` component type to the
-- component_variants CHECK constraint.
--
-- The body_template variant is the OUTER frame of the email body. It
-- contains placeholders ({{icebreaker_content}}, {{bridge_content}},
-- {{pain_hook_content}}, {{credibility_content}}, {{cta_content}}) that
-- the composer substitutes after resolving each inner component variant.
-- This enables template-level bandit A/B between modular (current default)
-- and storytelling (v2) body shapes without rewriting the inner components.
--
-- v1 types: subject_line, icebreaker, pain_hook, offer_frame, cta, signature
-- v2 added: who_i_am, credibility
-- v3 added: bridge
-- v4 adds:  body_template

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
        'credibility',
        'bridge',
        'body_template'
    ));
