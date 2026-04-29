"""Tests for systems.scout.outreach.writing_validator.

Locks the hard-rule subset that catches AI-speak, em-dashes, buzzwords,
and filler. Per Slice 21 of 2026-04-29 (operator caught templated +
em-dashed icebreaker that slipped past the prompt's own rules).
"""
from __future__ import annotations

from systems.scout.outreach.writing_validator import (
    Violation,
    validate_writing,
)


# --- empty / passing ---------------------------------------------------------


def test_empty_text_passes():
    assert validate_writing("").passed is True
    assert validate_writing(None).passed is True


def test_clean_text_passes():
    text = "Saw the Iroko work. The modular icon is a nice call."
    result = validate_writing(text)
    assert result.passed is True
    assert result.violations == []


# --- em-dash detection (hardest rule) ---------------------------------------


def test_unicode_em_dash_fails():
    text = "Saw the work — really clean."
    result = validate_writing(text)
    assert result.passed is False
    assert any(v.rule == "em_dash" for v in result.violations)


def test_unicode_en_dash_fails():
    text = "Saw the work – clean."
    result = validate_writing(text)
    assert result.passed is False
    assert any(v.rule == "em_dash" for v in result.violations)


def test_double_hyphen_em_dash_fails():
    text = "Saw the work -- really clean."
    result = validate_writing(text)
    assert result.passed is False
    assert any(v.rule == "em_dash" for v in result.violations)


# --- AI-cliché detection ----------------------------------------------------


def test_ngl_is_banned():
    """Operator flagged 'ngl' as AI-speak on 2026-04-29 even though prior
    prompts allowed it."""
    text = "Saw the work, ngl really clean."
    result = validate_writing(text)
    assert result.passed is False
    assert any(v.rule == "ai_cliche:ngl" for v in result.violations)


def test_two_things_stuck_with_me_is_banned():
    text = "Saw the work. Two things stuck with me about it."
    result = validate_writing(text)
    assert result.passed is False
    assert any("two things stuck" in v.rule for v in result.violations)


def test_came_across_your_is_banned():
    text = "Came across your portfolio this morning."
    result = validate_writing(text)
    assert result.passed is False
    assert any("came across" in v.rule for v in result.violations)


def test_sharp_positioning_is_banned():
    text = "Saw the work. Sharp positioning."
    result = validate_writing(text)
    assert result.passed is False
    assert any("sharp positioning" in v.rule for v in result.violations)


def test_sharp_work_is_banned():
    text = "Saw the work. Really sharp work."
    result = validate_writing(text)
    assert result.passed is False
    assert any("sharp work" in v.rule for v in result.violations)


# --- buzzwords --------------------------------------------------------------


def test_leverage_is_banned():
    text = "We help agencies leverage their existing client base."
    result = validate_writing(text)
    assert result.passed is False
    assert any("buzzword:leverage" in v.rule for v in result.violations)


def test_seamless_is_banned():
    text = "A seamless onboarding process."
    result = validate_writing(text)
    assert result.passed is False


# --- filler -----------------------------------------------------------------


def test_hope_this_finds_you_well_is_banned():
    text = "Hope this finds you well. Wanted to reach out."
    result = validate_writing(text)
    assert result.passed is False


def test_just_checking_in_is_banned():
    text = "Just checking in on this thread."
    result = validate_writing(text)
    assert result.passed is False


# --- founding year / tenure (Slice 23, 2026-04-29) -------------------------


def test_founded_in_yyyy_is_banned():
    """Operator-flagged 2026-04-29: 'DO NOT mention founding year. That is
    very disingenuous and screams of AI!!! No person speaks like this'."""
    text = "Noticed LYFE Marketing was founded in 2011. That hits."
    result = validate_writing(text)
    assert result.passed is False
    assert any("founded in YYYY" in v.rule for v in result.violations)


def test_since_yyyy_is_banned():
    text = "Noticed Social House has been at this since 2011."
    result = validate_writing(text)
    assert result.passed is False
    rules = {v.rule for v in result.violations}
    assert any("since YYYY" in r for r in rules)
    assert any("been at this" in r for r in rules)


def test_decade_plus_run_is_banned():
    text = "Noticed Fresh Content Society. A decade-plus run in this space says something."
    result = validate_writing(text)
    assert result.passed is False
    assert any("decade-plus" in v.rule for v in result.violations)


def test_over_a_decade_to_learn_is_banned():
    text = "That's over a decade to learn what actually works."
    result = validate_writing(text)
    assert result.passed is False
    assert any("a decade" in v.rule for v in result.violations)


def test_been_in_the_room_long_enough_is_banned():
    text = "When you've been in the room long enough you see the pattern."
    result = validate_writing(text)
    assert result.passed is False
    assert any("been in the room" in v.rule for v in result.violations)


def test_lyfe_marketing_slice_23_founding_year_icebreaker_fails():
    """The actual Tier-4 icebreaker the operator caught on 2026-04-29
    Slice 23 — opens with founding year, screams of AI."""
    text = (
        "Noticed LYFE Marketing was founded in 2011. That line about being "
        "tired of unsatisfying results from social media strategy hits "
        "different when you've been in the room long enough to see the "
        "pattern repeat."
    )
    result = validate_writing(text)
    assert result.passed is False
    rules = {v.rule for v in result.violations}
    assert any("founded in YYYY" in r for r in rules)
    assert any("been in the room" in r for r in rules)


def test_social_house_slice_23_tenure_icebreaker_fails():
    text = (
        "Noticed Social House has been at this since 2011. That's over a "
        "decade to learn what actually works."
    )
    result = validate_writing(text)
    assert result.passed is False
    rules = {v.rule for v in result.violations}
    assert any("since YYYY" in r for r in rules)
    assert any("been at this" in r for r in rules)
    assert any("a decade" in r for r in rules)


def test_fresh_content_society_slice_23_decade_icebreaker_fails():
    text = (
        "Noticed Fresh Content Society was founded in 2014. A decade-plus "
        "run in this space says something about what actually sticks."
    )
    result = validate_writing(text)
    assert result.passed is False
    rules = {v.rule for v in result.violations}
    assert any("founded in YYYY" in r for r in rules)
    assert any("decade-plus" in r for r in rules)


# --- composition: real failure case from 2026-04-29 -------------------------


def test_lyfe_marketing_icebreaker_from_slice_20_fails():
    """The actual icebreaker the operator caught: em-dash + ngl +
    Sharp positioning. All three should fire."""
    text = (
        "Came across LYFE Marketing's site this morning. Two things stuck "
        "with me: you've been at this since 2011, and that line about being "
        'tired of "unsatisfying results from your social media strategy" '
        "— ngl, that's the exact frustration everyone's sitting with right "
        "now. Sharp positioning."
    )
    result = validate_writing(text)
    assert result.passed is False
    rules = {v.rule for v in result.violations}
    assert "em_dash" in rules
    assert any("ngl" in r for r in rules)
    assert any("sharp positioning" in r for r in rules)
    assert any("came across" in r for r in rules)
    assert any("two things stuck" in r for r in rules)


# --- summary --------------------------------------------------------------


def test_violation_summary_is_one_line_actionable():
    text = "Came across the work — leverage your synergy."
    result = validate_writing(text)
    assert result.passed is False
    summary = result.violation_summary
    assert "failed" in summary
    assert str(len(result.violations)) in summary
