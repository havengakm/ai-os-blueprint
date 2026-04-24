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
    assert "taking on more clients?" in v8.variant_content
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


def test_all_creative_branding_variants_use_expected_offer_label() -> None:
    variants = _discover()
    cb = [v for v in variants if v.niche == "creative_branding"]
    offer_labels = {v.offer_label for v in cb}
    assert offer_labels == {"aios_scout_deployment"}, (
        f"all creative_branding variants must share one offer_label; "
        f"found {offer_labels}"
    )
