"""Regression tests for creative_branding component YAML set.

Loads the real YAML files under ``data/reference/sequences/creative_branding/``
through ``ComponentStore._discover_and_parse`` and asserts the resulting
``ComponentVariant`` set matches the expected operator-authored inventory.

Catches accidental deletions, renames, or validation regressions on the
seed files the creative_branding deployment depends on.
"""
from __future__ import annotations

from pathlib import Path

from systems.scout.outreach.component_store import (
    ComponentStore,
    ComponentStoreBackend,
    ComponentVariant,
    SyncSummary,
    VariantKeyTuple,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SEQUENCES_ROOT = _REPO_ROOT / "data" / "reference" / "sequences"


class _NullBackend:
    """ComponentStoreBackend stub — sync() never called, only discovery is."""

    async def fetch_existing(
        self, client_id: str, keys: list[VariantKeyTuple],
    ) -> dict[VariantKeyTuple, dict]:
        return {}

    async def insert_variants(
        self, client_id: str, variants: list[ComponentVariant],
    ) -> None:
        pass

    async def update_variants(
        self, client_id: str, updates: list[tuple[str, ComponentVariant]],
    ) -> None:
        pass


def _discover() -> list[ComponentVariant]:
    backend: ComponentStoreBackend = _NullBackend()  # type: ignore[assignment]
    store = ComponentStore(backend=backend, sequences_root=_SEQUENCES_ROOT)
    summary = SyncSummary()
    return store._discover_and_parse(summary)


def _by_type(
    variants: list[ComponentVariant], niche: str,
) -> dict[str, list[ComponentVariant]]:
    out: dict[str, list[ComponentVariant]] = {}
    for v in variants:
        if v.niche != niche:
            continue
        out.setdefault(v.component_type, []).append(v)
    return out


def test_creative_branding_yaml_set_loads_without_errors() -> None:
    """All operator-authored creative_branding YAMLs parse and validate."""
    backend: ComponentStoreBackend = _NullBackend()  # type: ignore[assignment]
    store = ComponentStore(backend=backend, sequences_root=_SEQUENCES_ROOT)
    summary = SyncSummary()
    variants = store._discover_and_parse(summary)

    cb = [v for v in variants if v.niche == "creative_branding"]
    assert cb, "creative_branding sequences directory must produce at least one variant"
    assert summary.errors == [], f"unexpected YAML errors: {summary.errors}"


def test_subject_line_v8_taking_on_more_clients_present() -> None:
    variants = _discover()
    by_type = _by_type(variants, "creative_branding")
    keys = {v.variant_key for v in by_type.get("subject_line", [])}
    assert "v8_taking_on_more_clients" in keys
    v8 = next(
        v for v in by_type["subject_line"]
        if v.variant_key == "v8_taking_on_more_clients"
    )
    assert "{{first_name}}" in v8.variant_content
    assert "{{short_company_name}}" in v8.variant_content
    # After Plan B's universal-placeholder refactor, the literal "clients"
    # was replaced with {{niche_specific_term}} so the same template serves
    # creative_branding ("clients") and fitness_wellness ("members") without
    # duplicating the variant.
    assert "taking on more {{niche_specific_term}}?" in v8.variant_content
    assert v8.offer_label == "aios_scout_deployment"


def test_cta_v3_90sec_video_present() -> None:
    variants = _discover()
    by_type = _by_type(variants, "creative_branding")
    keys = {v.variant_key for v in by_type.get("cta", [])}
    assert "v3_90sec_video" in keys
    v3 = next(
        v for v in by_type["cta"]
        if v.variant_key == "v3_90sec_video"
    )
    assert "90-sec video" in v3.variant_content


def test_who_i_am_v1_ai_outreach_system_present() -> None:
    """New component type + v1 variant for the revised body."""
    variants = _discover()
    by_type = _by_type(variants, "creative_branding")
    pool = by_type.get("who_i_am", [])
    assert pool, "who_i_am component type must have at least one variant"
    keys = {v.variant_key for v in pool}
    assert "v1_ai_outreach_system" in keys
    v1 = next(v for v in pool if v.variant_key == "v1_ai_outreach_system")
    # The three new niche-level placeholders must all render in this body.
    for placeholder in ("{{niche}}", "{{niche_specific_term}}", "{{meetings_niche_term}}"):
        assert placeholder in v1.variant_content, (
            f"who_i_am v1 must reference {placeholder}"
        )


def test_credibility_v1_100_businesses_present() -> None:
    variants = _discover()
    by_type = _by_type(variants, "creative_branding")
    pool = by_type.get("credibility", [])
    assert pool, "credibility component type must have at least one variant"
    keys = {v.variant_key for v in pool}
    assert "v1_100_businesses" in keys
    v1 = next(v for v in pool if v.variant_key == "v1_100_businesses")
    assert "100+ service businesses" in v1.variant_content


def test_offer_frame_v3_three_spots_is_the_only_offer_frame() -> None:
    """v1 (heres_what_id_do) and v2 (promise_period) were operator-rejected
    and removed. v3_three_spots is the sole creative_branding offer_frame."""
    variants = _discover()
    by_type = _by_type(variants, "creative_branding")
    offer_frames = by_type.get("offer_frame", [])
    keys = {v.variant_key for v in offer_frames}
    assert "v3_three_spots" in keys
    assert "v1_heres_what_id_do" not in keys
    assert "v2_promise_period" not in keys
    v3 = next(v for v in offer_frames if v.variant_key == "v3_three_spots")
    # v3 uses the niche-level placeholders in client_facts.
    assert "3 {{niche}}" in v3.variant_content
    assert "{{meetings_niche_term}}" in v3.variant_content


def test_all_creative_branding_variants_use_expected_offer_label() -> None:
    variants = _discover()
    cb = [v for v in variants if v.niche == "creative_branding"]
    offer_labels = {v.offer_label for v in cb}
    assert offer_labels == {"aios_scout_deployment"}, (
        f"all creative_branding variants must share one offer_label; "
        f"found {offer_labels}"
    )


def test_body_template_v1_modular_present_and_approved() -> None:
    """Plan 1.5 Task 1.5.8: v1_modular makes the legacy modular body shape
    explicit as a body_template variant. Must load, be approved, and
    contain placeholders for every inner body component."""
    variants = _discover()
    by_type = _by_type(variants, "creative_branding")
    body_templates = by_type.get("body_template", [])
    keys = {v.variant_key for v in body_templates}
    assert "v1_modular" in keys

    v1 = next(v for v in body_templates if v.variant_key == "v1_modular")
    assert v1.status == "approved"
    for placeholder in (
        "{{icebreaker_content}}",
        "{{bridge_content}}",
        "{{pain_hook_content}}",
        "{{credibility_content}}",
        "{{offer_frame_content}}",
        "{{cta_content}}",
        "{{signature_content}}",
    ):
        assert placeholder in v1.variant_content, (
            f"v1_modular must reference {placeholder} so the composer's "
            f"body_template substitution covers every inner component."
        )


def test_body_template_v2_storytelling_present_and_draft() -> None:
    """Plan 1.5 Task 1.5.8: v2_storytelling is staged for Kirsten's
    verbatim copy. Bandit must not pick it until status flips to
    'approved' (composer.fetch_approved_variants filters on status)."""
    variants = _discover()
    by_type = _by_type(variants, "creative_branding")
    body_templates = by_type.get("body_template", [])
    keys = {v.variant_key for v in body_templates}
    assert "v2_storytelling" in keys

    v2 = next(v for v in body_templates if v.variant_key == "v2_storytelling")
    # Locked behind status='draft' until operator authors the verbatim copy.
    assert v2.status == "draft"
