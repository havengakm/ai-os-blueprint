-- Add the `bridge` component type to the component_variants CHECK constraint.
--
-- The bridge slot sits between icebreaker and who_i_am in the v3-locked
-- creative_branding body order. It carries the substantive transition from
-- the observation about the prospect's work to the real purpose of the
-- email (see
-- data/reference/sequences/creative_branding/components/bridge/
-- v1_left_field_question.yaml).
--
-- v1 types: subject_line, icebreaker, pain_hook, offer_frame, cta, signature
-- v2 added: who_i_am, credibility
-- v3 adds:  bridge

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
        'bridge'
    ));
