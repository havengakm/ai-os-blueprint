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
    """Updated 2026-04-30 (Slice 35): the previous fixture 'is a nice
    call' is now banned as a compliment shape. New fixture demonstrates
    a situation-connect: names a constraint without praising the work."""
    text = (
        "Saw the Iroko work. Translating an infrastructure-grade brief "
        "into something visually distinct is a real constraint."
    )
    result = validate_writing(text)
    assert result.passed is True, [v.rule for v in result.violations]
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


# --- compliment shapes (Slice 35, 2026-04-30) -------------------------------


def test_chatterkick_slice_35_compliment_shape_fails():
    """Operator-flagged 2026-04-30: 'is a clean way to stack the actual
    outcomes people care about' passed every other validator class but
    read as disingenuous flattery. The icebreaker's payload sentence
    must show situation-connection, not praise."""
    text = (
        "Noticed the mission on your LinkedIn. 'Turn followers into "
        "superfans, likes into leads, clicks into conversations' is a "
        "clean way to stack the actual outcomes people care about."
    )
    result = validate_writing(text)
    assert result.passed is False
    rules = {v.rule for v in result.violations}
    assert any("compliment" in r for r in rules)
    assert any("clean way" in v.offending_text for v in result.violations)


def test_is_a_nice_call_is_banned():
    """'The X is a nice call' — generic praise shape."""
    text = "Saw the Iroko work. The modular icon for organised structure is a nice call."
    result = validate_writing(text)
    assert result.passed is False
    assert any(v.rule.startswith("compliment:") for v in result.violations)


def test_is_a_clean_way_to_X_is_banned():
    """'is a clean way to [verb]' — operator's exact flagged shape."""
    text = "Noticed your mission. That's a clean way to highlight the key points people care about."
    result = validate_writing(text)
    assert result.passed is False
    rules = " ".join(v.rule for v in result.violations)
    assert "compliment" in rules


def test_does_a_lot_of_work_is_banned():
    text = "Read the bit about infrastructure-grade nature restoration. That phrase does a lot of work."
    result = validate_writing(text)
    assert result.passed is False


def test_actually_sells_itself_is_banned():
    text = "The 3x pipeline framing with the client quote underneath actually sells itself."
    result = validate_writing(text)
    assert result.passed is False


def test_hits_different_is_banned():
    text = "Read the post about pricing. The framing hits different."
    result = validate_writing(text)
    assert result.passed is False


def test_nailed_it_is_banned():
    text = "Saw the rebrand. You nailed it."
    result = validate_writing(text)
    assert result.passed is False


def test_spot_on_is_banned():
    text = "Saw the framework. Spot on."
    result = validate_writing(text)
    assert result.passed is False


def test_real_talent_is_banned():
    text = "Saw the design. Real talent on the team."
    result = validate_writing(text)
    assert result.passed is False


def test_genuinely_impressive_is_banned():
    text = "Saw the rebrand. Genuinely impressive work."
    result = validate_writing(text)
    assert result.passed is False


def test_slice_35_situation_connect_now_fails_via_diagnostic_class():
    """Slice 36 (2026-04-30) — the 'situation-connect' example I drafted
    in Slice 35 was operator-rejected as 'critique disguised as
    research'. The new ``diagnostic`` validator class correctly catches
    it via 'the hard part is' + 'is usually [verbing]' patterns.
    Originally this test asserted it PASSED; the operator's pointer to
    icebreaker-framework.md surfaced this as the exact failure mode the
    framework explicitly bans ('Diagnosis disguised as research')."""
    text = (
        "Noticed the followers-to-leads framing on your page. The hard "
        "part is usually proving which post drove which call, most "
        "attribution stops at the platform boundary."
    )
    result = validate_writing(text)
    assert result.passed is False
    rules = {v.rule for v in result.violations}
    assert any("the hard part" in r for r in rules)
    assert any("is usually" in r for r in rules)


def test_situation_connect_iroko_passes():
    """The 'specific + grounded' shape from the operator's framework —
    naming a constraint without diagnostic-pundit framing. Should pass."""
    text = (
        "Saw the Iroko work. Translating an infrastructure-grade-nature "
        "brief into something that doesn't look like every other "
        "sustainability brand is a real constraint."
    )
    result = validate_writing(text)
    assert result.passed is True, [v.rule for v in result.violations]


# --- Slice 36 rollback regressions ----------------------------------------
# These phrasings appear in icebreaker-framework.md "Words that sound human"
# list and were over-banned by Slice 35. They should now PASS the validator.


def test_stuck_with_me_passes():
    """Framework example: 'the line about [phrase] stuck with me'."""
    text = "Read your post on agency burnout. The line about boundary-saying stuck with me."
    result = validate_writing(text)
    assert result.passed is True, [v.rule for v in result.violations]


def test_stuck_in_my_head_passes():
    """Framework example: 'Your post has been stuck in my head since Tuesday'."""
    text = "Your post about pricing has been stuck in my head this week."
    result = validate_writing(text)
    assert result.passed is True, [v.rule for v in result.violations]


def test_smart_move_passes():
    """Framework's 'Words that sound human' includes 'smart move'."""
    text = "Saw the rebrand for the wellness brand. Pulling away from the typical sustainability palette was a smart move for that category."
    result = validate_writing(text)
    assert result.passed is True, [v.rule for v in result.violations]


def test_stood_out_passes():
    """Framework example: 'The [project] for [client] stood out'."""
    text = "Looked at your portfolio. The work for Iroko stood out, especially the typography choices."
    result = validate_writing(text)
    assert result.passed is True, [v.rule for v in result.violations]


# --- Slice 36 diagnostic class regressions --------------------------------


def test_the_hard_part_is_banned():
    """Operator-flagged 2026-04-30: 'the hard part is' is critique
    disguised as research. Tells the prospect what is hard about their
    job. Presumptuous."""
    text = "Saw the work. The hard part is usually proving attribution."
    result = validate_writing(text)
    assert result.passed is False
    assert any(v.rule.startswith("diagnostic:") for v in result.violations)


def test_most_agencies_cant_is_banned():
    """Broad-strokes generalization that lectures."""
    text = "Saw the work. Most agencies can't pull this off."
    result = validate_writing(text)
    assert result.passed is False
    assert any("most" in v.rule for v in result.violations)


def test_have_you_tried_is_banned():
    """Socratic-gotcha advice shape from a stranger."""
    text = "Have you tried looking at it from the attribution angle?"
    result = validate_writing(text)
    assert result.passed is False


def test_your_agency_doesnt_seem_to_have_is_banned():
    """Framework-flagged exact shape: 'I noticed your agency doesn't
    seem to have an outbound system' — diagnosis disguised as research."""
    text = "Looked at the site, your agency doesn't seem to have a programmatic outbound layer."
    result = validate_writing(text)
    assert result.passed is False


def test_you_might_want_to_consider_is_banned():
    """Unsolicited advice."""
    text = "Saw the work. You might want to consider rethinking the social-attribution piece."
    result = validate_writing(text)
    assert result.passed is False


def test_the_real_question_is_banned():
    """Socratic-gotcha shape."""
    text = "Saw the case study. The real question is whether attribution survives a longer sales cycle."
    result = validate_writing(text)
    assert result.passed is False


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
