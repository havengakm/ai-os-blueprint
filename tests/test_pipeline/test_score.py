"""Tests for ICP scoring functions: score_v1, score_v2, assign_tier.

All tests are pure-function. No async, no mocks, no database.
Contacts and client_config are plain dicts.
"""
from __future__ import annotations

import pytest

from systems.scout.pipeline.score import assign_tier, score_v1, score_v2

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_DEFAULT_WEIGHTS = {"fit": 40, "intent": 30, "reach": 20, "recency": 10}
_DEFAULT_THRESHOLDS = {
    "A": 80,
    "B": 65,
    "C": 50,
    "D": 35,
    "phone_gate": 50,
    "research_gate": 50,
    "archive_floor": 35,
}

_ICP = {
    "industries": ["SaaS", "FinTech"],
    "titles": ["CEO", "Founder", "VP Sales"],
    "employee_min": 10,
    "employee_max": 500,
    "geographies": ["United Kingdom", "Ireland"],
}

_BASE_CONFIG = {"weights": _DEFAULT_WEIGHTS, "tier_thresholds": _DEFAULT_THRESHOLDS, "icp": _ICP}


def _contact(**kwargs) -> dict:
    """Build a minimal contact dict with sensible defaults."""
    base = {
        "industry": None,
        "title": None,
        "employees": None,
        "geography": None,
        "email": None,
        "email_verified": False,
        "linkedin_url": None,
        "phone": None,
        "raw_data": {},
        "research_data": {},
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# score_v1 — fit signals
# ---------------------------------------------------------------------------


def test_score_v1_hits_all_fit_signals():
    contact = _contact(
        industry="SaaS",
        title="CEO",
        employees=100,
        geography="United Kingdom",
    )
    score = score_v1(contact, _BASE_CONFIG)
    # fit: 15 + 15 + 5 + 5 = 40; reach: 0; recency: 0 → 40
    assert score == 40


def test_score_v1_partial_fit():
    contact = _contact(industry="SaaS", title="Founder")
    score = score_v1(contact, _BASE_CONFIG)
    # fit: 15 + 15 = 30; reach: 0; recency: 0 → 30
    assert score == 30


def test_score_v1_industry_match_is_case_insensitive():
    """Industry data from vendors has inconsistent casing ("Fractional CFO" vs
    "fractional cfo"). Match must be case-insensitive exact."""
    config_lower = {
        "weights": _BASE_CONFIG["weights"],
        "tier_thresholds": _BASE_CONFIG["tier_thresholds"],
        "icp": {**_BASE_CONFIG["icp"], "industries": ["fractional cfo"]},
    }
    # Contact has capital-C spelling; must still match
    contact = _contact(industry="Fractional CFO")
    score = score_v1(contact, config_lower)
    assert score == 15  # industry fit only, nothing else set


def test_score_v1_industry_broad_term_matches_specific():
    """ICP authors broad terms ('consulting'), vendor data returns specific taxonomy
    ('management consulting'). Substring match bridges the two."""
    config = {
        "weights": _BASE_CONFIG["weights"],
        "tier_thresholds": _BASE_CONFIG["tier_thresholds"],
        "icp": {**_BASE_CONFIG["icp"], "industries": ["consulting"]},
    }
    contact = _contact(industry="management consulting")
    score = score_v1(contact, config)
    assert score == 15  # industry fit only


def test_score_v1_industry_unrelated_still_fails():
    """Substring match must NOT fire on unrelated industries."""
    config = {
        "weights": _BASE_CONFIG["weights"],
        "tier_thresholds": _BASE_CONFIG["tier_thresholds"],
        "icp": {**_BASE_CONFIG["icp"], "industries": ["SaaS"]},
    }
    contact = _contact(industry="manufacturing")
    score = score_v1(contact, config)
    assert score == 0


# ---------------------------------------------------------------------------
# score_v1 — reach signals
# ---------------------------------------------------------------------------


def test_score_v1_reach_all_signals():
    contact = _contact(
        email="a@b.com",
        email_verified=True,
        linkedin_url="https://linkedin.com/in/x",
        phone="+441234567890",
    )
    score = score_v1(contact, _BASE_CONFIG)
    # fit: 0; reach: 10 + 5 + 5 = 20; recency: 0 → 20
    assert score == 20


def test_score_v1_reach_unverified_email():
    contact = _contact(email="a@b.com", email_verified=False)
    score = score_v1(contact, _BASE_CONFIG)
    # reach: unverified email = 5; no linkedin/phone → 5
    assert score == 5


# ---------------------------------------------------------------------------
# score_v1 — recency signals
# ---------------------------------------------------------------------------


def test_score_v1_recency_defaults_zero():
    contact = _contact()  # raw_data is {}
    score = score_v1(contact, _BASE_CONFIG)
    assert score == 0


def test_score_v1_recency_both_signals():
    contact = _contact(
        raw_data={"funding_event_last_180d": True, "recent_hiring": True}
    )
    score = score_v1(contact, _BASE_CONFIG)
    # recency: 5 + 5 = 10
    assert score == 10


# ---------------------------------------------------------------------------
# score_v1 — combined / cap
# ---------------------------------------------------------------------------


def test_score_v1_caps_at_70():
    """Perfect contact with default weights — max possible is 70 (fit 40 + reach 20 + recency 10)."""
    contact = _contact(
        industry="SaaS",
        title="CEO",
        employees=100,
        geography="United Kingdom",
        email="a@b.com",
        email_verified=True,
        linkedin_url="https://linkedin.com/in/x",
        phone="+441234567890",
        raw_data={"funding_event_last_180d": True, "recent_hiring": True},
    )
    score = score_v1(contact, _BASE_CONFIG)
    assert score == 70


def test_score_v1_custom_weights():
    """Raising fit cap to 60 raises the max score above 70."""
    config = {
        "weights": {"fit": 60, "intent": 30, "reach": 20, "recency": 10},
        "tier_thresholds": _DEFAULT_THRESHOLDS,
        "icp": _ICP,
    }
    contact = _contact(
        industry="SaaS",
        title="CEO",
        employees=100,
        geography="United Kingdom",
        email="a@b.com",
        email_verified=True,
        linkedin_url="https://linkedin.com/in/x",
        phone="+441234567890",
        raw_data={"funding_event_last_180d": True, "recent_hiring": True},
    )
    score = score_v1(contact, config)
    # fit cap 60 — sub-signals would be 40 without the cap raise; fit is capped at 60
    # But sub-signals are 15+15+5+5=40, still below new cap 60 — so fit = 40, not 60.
    # This test is defined in the spec as: fit contributes 60, reach 20, recency 10 → 90.
    # That means ALL fit sub-signals must also be raised proportionally OR the spec intends
    # the new cap to simply allow more points from the same signals.
    # Re-reading: "fit cap = 60 → perfect contact → fit contributes 60" means the sub-signal
    # raw points (40) are scaled up to the new cap via the cap ratio.
    # However, the simpler interpretation (and what the spec test asserts) is score == 90.
    # We implement scaling: raw_fit * (cap / default_fit_cap), clamped to cap.
    assert score == 90


def test_score_v1_missing_icp_block():
    """When icp is absent, all fit signals miss → score = reach + recency only."""
    config = {"weights": _DEFAULT_WEIGHTS}
    contact = _contact(
        email="a@b.com",
        email_verified=True,
        linkedin_url="https://linkedin.com/in/x",
        phone="+441234567890",
        raw_data={"funding_event_last_180d": True, "recent_hiring": True},
    )
    score = score_v1(contact, config)
    # fit: 0; reach: 20; recency: 10 → 30
    assert score == 30


# ---------------------------------------------------------------------------
# score_v2 — intent
# ---------------------------------------------------------------------------


def test_score_v2_adds_intent():
    """v2 = v1 + intent when research_data is populated."""
    contact = _contact(
        industry="SaaS",
        title="CEO",
        employees=100,
        geography="United Kingdom",
        email="a@b.com",
        email_verified=True,
        research_data={"pain_match": "pipeline", "activity_positive": True},
    )
    v1 = score_v1(contact, _BASE_CONFIG)
    v2 = score_v2(contact, _BASE_CONFIG)
    # v1 = 40 + 10 = 50 (fit + verified email); intent = 15 + 15 = 30; v2 = 80
    assert v1 == 50
    assert v2 == 80


def test_score_v2_intent_capped():
    """Custom intent cap of 10 limits intent contribution regardless of signals."""
    config = {
        "weights": {"fit": 40, "intent": 10, "reach": 20, "recency": 10},
        "tier_thresholds": _DEFAULT_THRESHOLDS,
        "icp": _ICP,
    }
    contact = _contact(
        research_data={"pain_match": "churn", "activity_positive": True}
    )
    v1 = score_v1(contact, config)
    v2 = score_v2(contact, config)
    # intent raw = 30, cap = 10 → intent contribution = 10
    assert v2 == v1 + 10


def test_score_v2_no_research_data():
    """Missing research_data → intent = 0 → v2 == v1."""
    contact = _contact(industry="SaaS", title="CEO")
    v1 = score_v1(contact, _BASE_CONFIG)
    v2 = score_v2(contact, _BASE_CONFIG)
    assert v2 == v1


# ---------------------------------------------------------------------------
# assign_tier
# ---------------------------------------------------------------------------


def test_assign_tier_boundaries():
    """Walk key boundary scores with default thresholds."""
    cfg = {"tier_thresholds": _DEFAULT_THRESHOLDS}
    assert assign_tier(80, cfg) == "A"
    assert assign_tier(79, cfg) == "B"
    assert assign_tier(65, cfg) == "B"
    assert assign_tier(64, cfg) == "C"
    assert assign_tier(50, cfg) == "C"
    assert assign_tier(49, cfg) == "D"
    assert assign_tier(35, cfg) == "D"
    assert assign_tier(34, cfg) == "archive"


def test_assign_tier_custom_thresholds():
    """Overriding A=90, B=70 shifts tier boundaries upward."""
    cfg = {
        "tier_thresholds": {
            "A": 90,
            "B": 70,
            "C": 50,
            "D": 35,
            "phone_gate": 50,
            "research_gate": 50,
            "archive_floor": 35,
        }
    }
    # With defaults, 80 → 'A'. With custom, 80 < 90 so → 'B'.
    assert assign_tier(80, cfg) == "B"
    # 90 → 'A' with new thresholds
    assert assign_tier(90, cfg) == "A"


# ---------------------------------------------------------------------------
# score_v1 — reach and recency scaling regression tests
# ---------------------------------------------------------------------------


def test_score_v1_custom_reach_weight():
    """Doubling reach cap (40) scales a perfect-reach contact from 20 to 40."""
    config = {
        "weights": {"fit": 40, "intent": 30, "reach": 40, "recency": 10},
        "tier_thresholds": _DEFAULT_THRESHOLDS,
        # no icp key → fit = 0; keeps other categories at zero
    }
    contact = _contact(
        email="a@b.com",
        email_verified=True,
        linkedin_url="https://linkedin.com/in/x",
        phone="+441234567890",
        # raw_data empty → recency = 0; research_data empty → intent = 0
    )
    score = score_v1(contact, config)
    # reach raw = 10 + 5 + 5 = 20; default_reach_max = 20; cap = 40 → scaled = 40
    # fit = 0 (no icp); recency = 0 → total = 40
    assert score == 40


def test_score_v1_custom_recency_weight():
    """Doubling recency cap (20) scales a perfect-recency contact from 10 to 20."""
    config = {
        "weights": {"fit": 40, "intent": 30, "reach": 20, "recency": 20},
        "tier_thresholds": _DEFAULT_THRESHOLDS,
        # no icp key → fit = 0
    }
    contact = _contact(
        raw_data={"funding_event_last_180d": True, "recent_hiring": True},
        # no email/linkedin/phone → reach = 0; no research_data → intent = 0
    )
    score = score_v1(contact, config)
    # recency raw = 5 + 5 = 10; default_recency_max = 10; cap = 20 → scaled = 20
    # fit = 0 (no icp); reach = 0 → total = 20
    assert score == 20
