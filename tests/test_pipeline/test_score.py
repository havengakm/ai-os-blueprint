"""Tests for ICP scoring functions: score_v1, score_v2, assign_tier.

All tests are pure-function. No async, no mocks, no database.
Contacts and client_config are plain dicts.
"""
from __future__ import annotations

import pytest

from systems.scout.pipeline.score import (
    _has_measurable_case_study,
    _has_named_client,
    _has_recent_structural_signal,
    assign_tier,
    score_v1,
    score_v2,
)

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
    """Only industry + title set (employees, geography are None).
    _score_fit scales over PROVIDED fields (industry+title raw_max=30), so
    a perfect-match partial contact scales to the full fit cap.
    """
    contact = _contact(industry="SaaS", title="Founder")
    score = score_v1(contact, _BASE_CONFIG)
    # fit raw = 30 (industry + title), available raw_max = 30 → scaled to cap = 40.
    # reach: 0; recency: 0 → total 40
    assert score == 40


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
    # industry raw=15, available raw_max=15 (only industry provided) → scaled
    # to full fit cap (40). Case-insensitive match is what's under test —
    # the score value just confirms the match fired.
    assert score == 40


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
    # industry raw=15, available raw_max=15 → scaled to full fit cap (40).
    # Substring behaviour is what's under test, not the exact score.
    assert score == 40


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
    """v2 = v1 + intent when research_data is populated.

    Slice 27 (2026-04-29): intent expanded from 2 binary signals to 5
    research-derived sub-signals + 2 LinkedIn-reserved (Slice C). Full
    intent of 30 now requires the LinkedIn signals to also fire; pre-
    Slice-C max raw = 22 (6+5+4+4+3) which scales to 22/30 of cap.
    """
    contact = _contact(
        industry="SaaS",
        title="CEO",
        employees=100,
        geography="United Kingdom",
        email="a@b.com",
        email_verified=True,
        research_data={
            "pain_match": "pipeline",
            "activity_positive": True,
            "citable_details": [
                {"type": "named_client", "detail": "Stripe"},
                {"type": "case_study", "detail": "Lifted conversion 35%"},
            ],
            "structural_signals": [
                {"type": "exec_change", "recency_days": 14},
            ],
        },
    )
    v1 = score_v1(contact, _BASE_CONFIG)
    v2 = score_v2(contact, _BASE_CONFIG)
    # v1 = 40 + 10 = 50 (fit + verified email); intent raw 6+5+4+4+3 = 22
    # → scaled 22/30*30 = 22; v2 = 72.
    assert v1 == 50
    assert v2 == 72


def test_score_v2_full_intent_with_linkedin_signals_reserved():
    """Slice 27: when both Slice C reserved LinkedIn flags are also set,
    intent raw hits 30 → full cap. Verifies the reserved slots are
    wired and ready for Slice C without further code changes."""
    contact = _contact(
        industry="SaaS",
        title="CEO",
        employees=100,
        geography="United Kingdom",
        email="a@b.com",
        email_verified=True,
        research_data={
            "pain_match": "pipeline",
            "activity_positive": True,
            "citable_details": [
                {"type": "named_client", "detail": "Stripe"},
                {"type": "case_study", "detail": "Lifted conversion 35%"},
            ],
            "structural_signals": [{"type": "exec_change", "recency_days": 14}],
            "linkedin_dm_recent_post_match": True,
            "linkedin_company_recent_post": True,
        },
    )
    v1 = score_v1(contact, _BASE_CONFIG)
    v2 = score_v2(contact, _BASE_CONFIG)
    # Intent raw = 30 → cap 30 → v2 = v1 + 30 = 80
    assert v1 == 50
    assert v2 == 80


def test_score_v2_intent_capped():
    """Custom intent cap of 10 limits intent contribution regardless of signals.

    Slice 27 update: signal set expanded; with full firing including
    LinkedIn-reserved flags raw = 30, scaled to cap (10). Otherwise
    raw/raw_max ratio applies."""
    config = {
        "weights": {"fit": 40, "intent": 10, "reach": 20, "recency": 10},
        "tier_thresholds": _DEFAULT_THRESHOLDS,
        "icp": _ICP,
    }
    contact = _contact(
        research_data={
            "pain_match": "churn",
            "activity_positive": True,
            "citable_details": [
                {"type": "named_client", "detail": "Acme"},
                {"type": "case_study", "detail": "Cut churn 12%"},
            ],
            "structural_signals": [{"type": "funding", "recency_days": 30}],
            "linkedin_dm_recent_post_match": True,
            "linkedin_company_recent_post": True,
        }
    )
    v1 = score_v1(contact, config)
    v2 = score_v2(contact, config)
    # intent raw = 30, scale to cap 10 → +10
    assert v2 == v1 + 10


def test_score_v2_no_research_data():
    """Missing research_data → intent = 0 → v2 == v1."""
    contact = _contact(industry="SaaS", title="CEO")
    v1 = score_v1(contact, _BASE_CONFIG)
    v2 = score_v2(contact, _BASE_CONFIG)
    assert v2 == v1


def test_v2_does_not_drop_below_v1_when_title_added_with_no_match():
    """Regression for Slice 18 bug: identity stage populates ``title``
    BETWEEN v1 and v2 runs. If the resolved title doesn't substring-match
    any ICP title, fit's denominator MUST NOT grow without numerator
    growing — that would cause score_v2 < score_v1, archiving contacts
    that had clean v1 scores.

    Setup: v1 has industry but no title; v2 sees the same data + a
    non-matching title. v2 should equal v1 (intent=0; title contributes
    nothing in either direction).
    """
    base_v1 = _contact(industry="SaaS")  # title omitted
    v1 = score_v1(base_v1, _BASE_CONFIG)

    base_v2 = _contact(industry="SaaS", title="Director")  # not in ICP titles
    v2 = score_v2(base_v2, _BASE_CONFIG)

    assert v2 >= v1, (
        f"v2={v2} dropped below v1={v1} after non-matching title added; "
        "fit denominator grew without numerator. Title fields with no ICP "
        "match must be NEUTRAL (skipped from raw_max), not negative."
    )


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


def test_score_v1_sparse_contact_stays_above_archive_floor():
    """Regression: ingest CSV payloads often lack industry/employees/geography
    but have title + email_verified. Before the Option-A fit scaling fix, such
    contacts scored ~25 and got archived by score_v2 despite being viable.
    They must now score at or above the 35 archive floor.
    """
    contact = _contact(
        title="Founder",
        email="founder@acme.com",
        email_verified=True,
        # industry, employees, geography all None
        # no linkedin, no phone
    )
    score = score_v1(contact, _BASE_CONFIG)
    # fit: only title provided → raw=15, raw_max=15 → scaled 15/15*40 = 40
    # reach: verified email only (raw=10), default raw_max=20, cap=20 → 10
    # recency: 0
    # total: 50 — comfortably above archive_floor=35
    assert score >= _DEFAULT_THRESHOLDS["archive_floor"]
    assert score == 50


def test_score_v1_fully_populated_regression():
    """When every fit field is provided, behaviour is unchanged from the
    pre-Option-A implementation — raw_max==default (40), no scaling effect."""
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
    # fit: raw=40, raw_max=40, cap=40 → 40 (identical to pre-fix)
    # reach: 20, recency: 10 → total 70
    assert score == 70


def test_score_v1_mixed_sparse_proportional():
    """Mix: industry missing, employees+geography+title set, one of those
    matches. Scaled against provided fields only (title + employees +
    geography = raw_max 25), not the full 40."""
    # Title matches ("Founder" matches ICP titles), employees in band,
    # geography NOT matching ("Germany" not in UK/Ireland).
    contact = _contact(
        industry=None,
        title="Founder",
        employees=50,
        geography="Germany",
    )
    score = score_v1(contact, _BASE_CONFIG)
    # fit: raw = 15 (title) + 5 (employees) = 20; raw_max = 15 + 5 + 5 = 25
    # scaled: 20/25 * 40 = 32
    # reach: 0, recency: 0
    assert score == 32


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


# --------------------------------------------------------------------------- #
# Slice 27 (2026-04-29): intent signal helpers                                 #
# --------------------------------------------------------------------------- #


def test_has_named_client_recognises_recognised_types():
    """named_client / client_portfolio / case_study / project / named_project
    types with non-empty detail count as a named-client reference."""
    cd = [
        {"type": "named_client", "detail": "Stripe"},
        {"type": "year_founded", "detail": "2014"},  # marketing-copy: ignored
    ]
    assert _has_named_client(cd) is True


def test_has_named_client_rejects_marketing_copy_only():
    """Lists containing only year_founded / company_about / value_proposition
    don't count — those are the entries the operator flagged as 'AI clutch'."""
    cd = [
        {"type": "year_founded", "detail": "2011"},
        {"type": "company_about", "detail": "Are you tired of..."},
        {"type": "value_proposition", "detail": "Top agency"},
    ]
    assert _has_named_client(cd) is False


def test_has_named_client_rejects_empty_detail():
    """Recognised type with empty detail does not count."""
    assert _has_named_client([{"type": "named_client", "detail": ""}]) is False
    assert _has_named_client([{"type": "named_client"}]) is False


def test_has_named_client_handles_non_dict_entries():
    """Robust against malformed entries (str, None, list)."""
    assert _has_named_client(["bad", None, {"type": "named_client", "detail": "Acme"}]) is True
    assert _has_named_client(["bad", None]) is False


def test_has_measurable_case_study_matches_percent():
    cd = [{"type": "case_study", "detail": "Lifted conversion 35% in 90 days."}]
    assert _has_measurable_case_study(cd) is True


def test_has_measurable_case_study_matches_dollar_amount():
    cd = [{"type": "case_study", "detail": "Generated $2M in pipeline value"}]
    assert _has_measurable_case_study(cd) is True


def test_has_measurable_case_study_matches_multiplier():
    cd = [{"type": "case_study", "detail": "3x growth year over year"}]
    assert _has_measurable_case_study(cd) is True


def test_has_measurable_case_study_rejects_no_metric():
    """A case_study with prose but no metric doesn't count."""
    cd = [{"type": "case_study", "detail": "Built a comprehensive brand strategy"}]
    assert _has_measurable_case_study(cd) is False


def test_has_measurable_case_study_rejects_wrong_type():
    """Marketing-copy types don't count even with metrics in detail."""
    cd = [{"type": "company_about", "detail": "We've grown 200%"}]
    assert _has_measurable_case_study(cd) is False


def test_has_recent_structural_signal_within_window():
    sigs = [{"type": "exec_change", "recency_days": 14}]
    assert _has_recent_structural_signal(sigs) is True


def test_has_recent_structural_signal_outside_window():
    sigs = [{"type": "exec_change", "recency_days": 200}]
    assert _has_recent_structural_signal(sigs) is False


def test_has_recent_structural_signal_missing_recency():
    """Missing recency_days defaults to 'old' — only confirmed-recent counts."""
    sigs = [{"type": "exec_change"}]
    assert _has_recent_structural_signal(sigs) is False


def test_has_recent_structural_signal_custom_window():
    sigs = [{"type": "funding", "recency_days": 100}]
    assert _has_recent_structural_signal(sigs, max_days=180) is True
    assert _has_recent_structural_signal(sigs, max_days=60) is False
