"""Plan 2 Phase 6 Task 2.6.1: provision_new_client tests.

The bootstrap script's responsibilities:
1. Validate args (client_id format, niche existence).
2. Build default client_config from args + run validate_config.
3. Bootstrap per-client folders (context/<id>, data/knowledge/personal/<id>,
   data/knowledge/company/<id>).
4. Insert clients + client_config + autonomy_rules rows in Supabase.
5. Print human-only checklist.

Migrations are NOT run by this script — that's the operator's responsibility
out-of-band. The script assumes migrations are already applied to the
target Supabase project.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.provision_new_client import (
    DEFAULT_TIER_THRESHOLDS,
    ProvisionResult,
    bootstrap_client_folders,
    build_default_client_config,
    human_checklist,
    validate_client_id,
    validate_niche_exists,
)


# --------------------------------------------------------------------------- #
# validate_client_id                                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "valid_id",
    [
        "kirsten-client-zero",
        "acme-co-zero",
        "client_a",
        "abc-123",
        "tenant42",
    ],
)
def test_validate_client_id_accepts_kebab_underscore_alnum(valid_id):
    validate_client_id(valid_id)  # no raise


@pytest.mark.parametrize(
    "invalid_id",
    [
        "",
        " ",
        "with whitespace",
        "with/slash",
        "with.dot",
        "with$special",
        "tab\there",
        "newline\nhere",
        "Capital",  # uppercase forbidden — mirror migration patterns
    ],
)
def test_validate_client_id_rejects_special_chars(invalid_id):
    with pytest.raises(ValueError):
        validate_client_id(invalid_id)


def test_validate_client_id_rejects_too_long():
    """Cap at a sane length so DB FK constraints don't break."""
    with pytest.raises(ValueError):
        validate_client_id("a" * 200)


# --------------------------------------------------------------------------- #
# validate_niche_exists                                                       #
# --------------------------------------------------------------------------- #


def test_validate_niche_exists_accepts_known(tmp_path: Path):
    """Niche dir present under sequences_root → accepted."""
    sequences_root = tmp_path / "sequences"
    (sequences_root / "creative_branding").mkdir(parents=True)
    validate_niche_exists("creative_branding", sequences_root=sequences_root)


def test_validate_niche_exists_rejects_unknown(tmp_path: Path):
    sequences_root = tmp_path / "sequences"
    sequences_root.mkdir()
    (sequences_root / "creative_branding").mkdir()
    with pytest.raises(ValueError) as exc:
        validate_niche_exists("nonexistent", sequences_root=sequences_root)
    assert "nonexistent" in str(exc.value)


def test_validate_niche_exists_against_real_repo():
    """Smoke test against the actual sequences/ dir in this repo."""
    validate_niche_exists("creative_branding")  # known niche; no raise


# --------------------------------------------------------------------------- #
# build_default_client_config                                                 #
# --------------------------------------------------------------------------- #


def test_build_default_client_config_includes_tier_budgets():
    cfg = build_default_client_config(
        client_id="acme",
        client_name="Acme Co",
        niche="creative_branding",
        offer_label="aios_scout_deployment",
        tier_budgets_cents={"A": 200, "B": 100, "C": 50, "D": 25},
    )
    assert cfg["tier_budgets_cents"] == {"A": 200, "B": 100, "C": 50, "D": 25}
    assert cfg["niche"] == "creative_branding"
    assert cfg["offer_label"] == "aios_scout_deployment"


def test_build_default_client_config_uses_default_tier_thresholds():
    cfg = build_default_client_config(
        client_id="acme", client_name="Acme",
        niche="creative_branding", offer_label="x",
        tier_budgets_cents={"A": 100, "B": 50, "C": 25, "D": 10},
    )
    assert cfg["tier_thresholds"] == DEFAULT_TIER_THRESHOLDS
    # Validator will pass against the defaults.
    from aios.scout.pipeline.validate_config import validate_client_config
    assert validate_client_config(cfg) == []


def test_build_default_client_config_starts_with_empty_icp():
    """ICP must be operator-authored; the bootstrap leaves it empty so
    the validator can be re-run after operator fills it in."""
    cfg = build_default_client_config(
        client_id="acme", client_name="Acme",
        niche="creative_branding", offer_label="x",
        tier_budgets_cents={"A": 100, "B": 50, "C": 25, "D": 10},
    )
    assert cfg["icp"] == {}


# --------------------------------------------------------------------------- #
# bootstrap_client_folders                                                    #
# --------------------------------------------------------------------------- #


def test_bootstrap_client_folders_creates_three_dirs(tmp_path: Path):
    result = bootstrap_client_folders("acme", repo_root=tmp_path)
    assert (tmp_path / "context" / "acme").is_dir()
    assert (tmp_path / "data" / "knowledge" / "personal" / "acme").is_dir()
    assert (tmp_path / "data" / "knowledge" / "company" / "acme").is_dir()
    assert len(result.created_paths) == 3


def test_bootstrap_client_folders_idempotent(tmp_path: Path):
    """Re-running for the same client_id doesn't error + reports
    'already_present' for the existing dirs."""
    bootstrap_client_folders("acme", repo_root=tmp_path)
    second = bootstrap_client_folders("acme", repo_root=tmp_path)
    assert second.created_paths == []  # nothing new
    assert len(second.already_present_paths) == 3


def test_bootstrap_client_folders_dry_run(tmp_path: Path):
    """dry_run=True: no dirs created on disk; result reports what would
    have been created."""
    result = bootstrap_client_folders("acme", repo_root=tmp_path, dry_run=True)
    assert len(result.would_create_paths) == 3
    assert not (tmp_path / "context" / "acme").exists()


# --------------------------------------------------------------------------- #
# human_checklist                                                             #
# --------------------------------------------------------------------------- #


def test_human_checklist_includes_required_steps():
    md = human_checklist("acme")
    assert "acme" in md
    # Critical operator-only steps mentioned per spec
    assert "personal context" in md.lower() or "context/" in md
    assert "company facts" in md.lower() or "company/" in md
    assert "approve" in md.lower() and "variant" in md.lower()


# --------------------------------------------------------------------------- #
# ProvisionResult dataclass shape                                              #
# --------------------------------------------------------------------------- #


def test_provision_result_dataclass_shape():
    """Smoke check on the return type."""
    r = ProvisionResult(
        client_id="acme",
        already_provisioned=False,
        db_rows_inserted={"clients": 1, "client_config": 1, "autonomy_rules": 1},
        created_paths=[Path("/tmp/context/acme")],
        already_present_paths=[],
        would_create_paths=[],
    )
    assert r.client_id == "acme"
    assert r.db_rows_inserted["clients"] == 1
