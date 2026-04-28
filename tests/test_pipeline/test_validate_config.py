"""Plan 2 Phase 6 Task 2.6.2: client config validator tests.

Three footgun classes the validator catches:
1. Title entries < 4 chars (the 'CEO' substring footgun — short titles
   match too aggressively in pull-stage rule-based fit checks).
2. Geography entries in the known-ambiguous set ({'US', 'UK', 'AU'}).
   These are 2-letter ISO codes that match too broadly in text.
3. tier_thresholds monotonicity violations: A > B > C > D > archive_floor.
"""
from __future__ import annotations

import pytest

from systems.scout.pipeline.validate_config import (
    AMBIGUOUS_GEOGRAPHIES,
    MIN_TITLE_CHARS,
    ConfigValidationError,
    assert_valid_client_config,
    validate_client_config,
)


# --------------------------------------------------------------------------- #
# Constants sanity                                                            #
# --------------------------------------------------------------------------- #


def test_min_title_chars_is_4():
    assert MIN_TITLE_CHARS == 4


def test_ambiguous_geographies_contains_us_uk_au():
    assert "US" in AMBIGUOUS_GEOGRAPHIES
    assert "UK" in AMBIGUOUS_GEOGRAPHIES
    assert "AU" in AMBIGUOUS_GEOGRAPHIES


# --------------------------------------------------------------------------- #
# Happy path                                                                  #
# --------------------------------------------------------------------------- #


def test_valid_config_passes_with_no_errors():
    config = {
        "icp": {
            "titles": ["VP Marketing", "Head of Growth", "CMO Director"],
            "geographies": ["United States", "United Kingdom"],
        },
        "tier_thresholds": {
            "A": 80, "B": 60, "C": 40, "D": 25, "archive_floor": 10,
        },
    }
    assert validate_client_config(config) == []
    assert_valid_client_config(config)  # no raise


def test_partial_config_no_errors_when_fields_missing():
    """Missing icp / tier_thresholds is permitted (handled at use-site).
    The validator catches *invalid* values, not absent fields."""
    assert validate_client_config({}) == []
    assert validate_client_config({"icp": {}}) == []
    assert validate_client_config({"tier_thresholds": {}}) == []


# --------------------------------------------------------------------------- #
# Footgun 1: title length                                                     #
# --------------------------------------------------------------------------- #


def test_short_title_caught():
    config = {"icp": {"titles": ["VP", "Head of Growth"]}}
    errors = validate_client_config(config)
    assert len(errors) == 1
    assert "VP" in errors[0]
    assert "4 chars" in errors[0]


def test_ceo_substring_footgun_caught():
    """'CEO' is exactly the spec's documented footgun (matches 'video CEO',
    'CEO assistant', etc). The validator must catch it."""
    config = {"icp": {"titles": ["CEO"]}}
    errors = validate_client_config(config)
    assert len(errors) == 1
    assert "CEO" in errors[0]


def test_three_char_title_caught_consistently():
    for short in ("CFO", "COO", "CTO", "CXO"):
        errors = validate_client_config({"icp": {"titles": [short]}})
        assert len(errors) == 1, f"{short!r} not caught"


def test_four_char_title_passes():
    """4 chars is the minimum — strictly inclusive boundary."""
    config = {"icp": {"titles": ["VP HR"]}}  # 5 chars; safely passes
    assert validate_client_config(config) == []
    config = {"icp": {"titles": ["CMOs"]}}  # 4 chars; passes boundary
    assert validate_client_config(config) == []


def test_whitespace_only_title_caught():
    config = {"icp": {"titles": ["    "]}}  # 4 spaces — strip == 0
    errors = validate_client_config(config)
    assert len(errors) == 1


def test_non_string_title_caught():
    config = {"icp": {"titles": [42]}}
    errors = validate_client_config(config)
    assert len(errors) == 1


# --------------------------------------------------------------------------- #
# Footgun 2: ambiguous geography                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("ambiguous", ["US", "UK", "AU"])
def test_ambiguous_geography_caught(ambiguous):
    config = {"icp": {"geographies": [ambiguous]}}
    errors = validate_client_config(config)
    assert len(errors) == 1
    assert ambiguous in errors[0]
    assert "ambiguous" in errors[0].lower()


def test_full_country_name_passes():
    config = {
        "icp": {
            "geographies": ["United States", "United Kingdom", "Australia"]
        }
    }
    assert validate_client_config(config) == []


def test_multiple_ambiguous_geographies_all_reported():
    config = {"icp": {"geographies": ["US", "UK"]}}
    errors = validate_client_config(config)
    assert len(errors) == 2


# --------------------------------------------------------------------------- #
# Footgun 3: tier monotonicity                                                #
# --------------------------------------------------------------------------- #


def test_a_must_be_greater_than_b():
    config = {"tier_thresholds": {"A": 60, "B": 60, "C": 40, "D": 25, "archive_floor": 10}}
    errors = validate_client_config(config)
    assert any("A" in e and "B" in e for e in errors)


def test_b_must_be_greater_than_c():
    config = {"tier_thresholds": {"A": 80, "B": 40, "C": 40, "D": 25, "archive_floor": 10}}
    errors = validate_client_config(config)
    assert any("B" in e and "C" in e for e in errors)


def test_c_must_be_greater_than_d():
    config = {"tier_thresholds": {"A": 80, "B": 60, "C": 25, "D": 25, "archive_floor": 10}}
    errors = validate_client_config(config)
    assert any("C" in e and "D" in e for e in errors)


def test_d_must_be_greater_than_archive_floor():
    config = {
        "tier_thresholds": {"A": 80, "B": 60, "C": 40, "D": 10, "archive_floor": 10}
    }
    errors = validate_client_config(config)
    assert any("D" in e and "archive_floor" in e for e in errors)


def test_inverted_thresholds_report_all_violations():
    """A=10 < B=20 < C=30 < D=40 < archive=50 — every pair fails."""
    config = {
        "tier_thresholds": {"A": 10, "B": 20, "C": 30, "D": 40, "archive_floor": 50}
    }
    errors = validate_client_config(config)
    assert len(errors) == 4  # A<=B, B<=C, C<=D, D<=archive


def test_partial_thresholds_only_validate_present_pairs():
    """If only A + B are set, only that pair is checked. Missing tiers
    don't synthesise default values."""
    config = {"tier_thresholds": {"A": 80, "B": 60}}
    assert validate_client_config(config) == []


# --------------------------------------------------------------------------- #
# assert_valid_client_config raise behaviour                                  #
# --------------------------------------------------------------------------- #


def test_assert_valid_raises_with_all_errors_in_message():
    config = {
        "icp": {
            "titles": ["CEO"],
            "geographies": ["US"],
        },
        "tier_thresholds": {"A": 60, "B": 60, "C": 40, "D": 25, "archive_floor": 10},
    }
    with pytest.raises(ConfigValidationError) as exc:
        assert_valid_client_config(config)
    msg = str(exc.value)
    assert "CEO" in msg
    assert "US" in msg
    assert "A" in msg and "B" in msg


def test_assert_valid_does_not_raise_on_clean_config():
    config = {
        "icp": {"titles": ["VP Marketing"], "geographies": ["United States"]},
        "tier_thresholds": {"A": 80, "B": 60, "C": 40, "D": 25, "archive_floor": 10},
    }
    assert_valid_client_config(config)  # no raise
