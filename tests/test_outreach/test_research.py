"""Tests for ResearchSelector — enrich-output selection for composer placeholders.

Style mirrors tests/test_identity/test_orchestrator.py: FakeLogger records
every log_decision call; ExplodingLogger proves the selector swallows logger
failures. Contact and ComponentVariant factories keep each test body
focused on the one rule it exercises.
"""
from __future__ import annotations

from typing import Any

from systems.scout.outreach import ComponentVariant, ResearchFills, ResearchSelector


# --------------------------------------------------------------------------- #
# Fakes                                                                         #
# --------------------------------------------------------------------------- #

class FakeLogger:
    """Records every log_decision call; always returns a fake id."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def log_decision(self, client_id: str, **kwargs: Any) -> str:
        self.entries.append({"client_id": client_id, **kwargs})
        return "fake-decision-id"


class ExplodingLogger:
    """log_decision always raises — proves selector never crashes on log failure."""

    async def log_decision(self, client_id: str, **kwargs: Any) -> str:
        raise RuntimeError("logger exploded")


# --------------------------------------------------------------------------- #
# Factories                                                                     #
# --------------------------------------------------------------------------- #

def mk_contact(
    *,
    contact_id: str = "contact-1",
    first_name: str = "Jane",
    company: str = "Acme",
    niche: str = "cro_growth_ugc_agency",
    citable_details: list[dict[str, Any]] | None = None,
    buying_signals: list[dict[str, Any]] | None = None,
    trigger_events: list[dict[str, Any]] | None = None,
    research_data_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a contact dict. research_data_override wins over the piecewise args."""
    if research_data_override is not None:
        research_data = research_data_override
    else:
        research_data = {
            "citable_details": citable_details or [],
            "buying_signals": buying_signals or [],
            "trigger_events": trigger_events or [],
            "pain_match": "",
            "pain_category": "other",
            "has_active_buying_signal": False,
            "confidence": 0.0,
        }
    return {
        "contact_id": contact_id,
        "first_name": first_name,
        "company": company,
        "niche": niche,
        "research_data": research_data,
    }


def mk_variant(
    *,
    component_type: str,
    variant_key: str | None = None,
    variant_content: str = "default content",
    metadata: dict[str, Any] | None = None,
    niche: str = "cro_growth_ugc_agency",
    offer_label: str = "pipeline_audit",
) -> ComponentVariant:
    return ComponentVariant(
        variant_key=variant_key or f"{component_type}_v1",
        component_type=component_type,
        niche=niche,
        offer_label=offer_label,
        variant_content=variant_content,
        status="approved",
        metadata=metadata or {},
        ab_epsilon=0.1,
    )


def mk_default_components(
    *,
    pain_hook_metadata: dict[str, Any] | None = None,
    cta_content: str = "Worth a 20-minute call?",
    include_cta: bool = True,
) -> dict[str, ComponentVariant]:
    components = {
        "subject_line": mk_variant(
            component_type="subject_line",
            variant_content="Subject: {{trigger_hook}}",
        ),
        "icebreaker": mk_variant(
            component_type="icebreaker",
            variant_content="Hi {{first_name}}, noticed {{icebreaker_content}}.",
        ),
        "pain_hook": mk_variant(
            component_type="pain_hook",
            variant_content="Many agencies hit {{pain_evidence}}.",
            metadata=pain_hook_metadata or {},
        ),
        "offer_frame": mk_variant(
            component_type="offer_frame",
            variant_content="We help with X.",
        ),
        "signature": mk_variant(
            component_type="signature",
            variant_content="—Kirsten",
        ),
    }
    if include_cta:
        components["cta"] = mk_variant(
            component_type="cta",
            variant_content=cta_content,
        )
    return components


# --------------------------------------------------------------------------- #
# 1. Happy path — all 4 placeholders filled                                     #
# --------------------------------------------------------------------------- #

async def test_select_fills_happy_path_fills_all_four() -> None:
    contact = mk_contact(
        citable_details=[
            {"type": "case_study", "detail": "Grew client pipeline 3x in 90d", "source": "case_studies"},
        ],
        trigger_events=[
            {
                "type": "funding_round", "detail": "Raised Series B last month",
                "source": "claude_web_triggers", "recency_days": 15,
            },
        ],
    )
    # IcebreakerAdapter writes the icebreaker sentence directly; trigger_events
    # no longer fall back into the icebreaker slot.
    contact["research_data"]["icebreaker_content"] = "Saw their Iroko work this morning. Really sharp."
    components = mk_default_components()
    logger = FakeLogger()
    selector = ResearchSelector(decision_logger=logger)

    fills = await selector.select_fills("client-1", contact, components)

    assert isinstance(fills, ResearchFills)
    assert fills.icebreaker_content == "Saw their Iroko work this morning. Really sharp."
    assert fills.trigger_hook == "Raised Series B last month"
    assert fills.pain_evidence == "Grew client pipeline 3x in 90d"
    assert fills.cta_content == "Worth a 20-minute call?"
    # 4 enrich sources + 1 first_name audit entry; productised client_facts
    # weren't passed so those placeholders don't add audit entries.
    assert len(fills.sources_used) == 5


# --------------------------------------------------------------------------- #
# 2. Empty research_data → all enrich-backed fills None                         #
# --------------------------------------------------------------------------- #

async def test_select_fills_empty_research_returns_none() -> None:
    contact = mk_contact(research_data_override={})  # totally empty
    # No cta either → cta_content also None
    components = mk_default_components(include_cta=False)
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.icebreaker_content is None
    assert fills.trigger_hook is None
    assert fills.pain_evidence is None
    assert fills.cta_content is None
    # The only source that always fires is first_name (falls back to "there"
    # when the contact column is blank but here contact.first_name is set).
    assert len(fills.sources_used) == 1
    assert fills.sources_used[0]["placeholder"] == "first_name"


# --------------------------------------------------------------------------- #
# 3. Missing trigger_events → icebreaker + trigger None; pain + cta fill        #
# --------------------------------------------------------------------------- #

async def test_missing_trigger_events_only_pain_and_cta_fill() -> None:
    contact = mk_contact(
        citable_details=[
            {"type": "case_study", "detail": "Booked 40 meetings last quarter", "source": "case_studies"},
        ],
        trigger_events=[],  # none
    )
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.icebreaker_content is None
    assert fills.trigger_hook is None
    assert fills.pain_evidence == "Booked 40 meetings last quarter"
    assert fills.cta_content == "Worth a 20-minute call?"


# --------------------------------------------------------------------------- #
# 4. profile-match trigger preferred over domain-match                          #
# --------------------------------------------------------------------------- #

def test_profile_match_preferred_over_domain_match() -> None:
    # The legacy _select_icebreaker trigger-event ranking is retained as a
    # module-level helper but is no longer invoked from the select_fills path
    # (the fallback was bypassing voice validation — see research.py docstring).
    # Test the ranking directly so we keep coverage of the logic.
    from systems.scout.outreach.research import _select_icebreaker

    events = [
        {
            "type": "behavioral_signal", "detail": "Domain match event",
            "source": "trigify_linkedin", "match_key": "domain", "recency_days": 5,
            "engagement": {"likes": 0, "comments": 0, "shares": 0},
        },
        {
            "type": "behavioral_signal", "detail": "Profile match event",
            "source": "trigify_linkedin", "match_key": "profile", "recency_days": 5,
            "engagement": {"likes": 0, "comments": 0, "shares": 0},
        },
    ]
    detail, _ = _select_icebreaker(events)
    assert detail == "Profile match event"


# --------------------------------------------------------------------------- #
# 5. Recency weighting — recent (7d) preferred over older (80d) same match_key  #
# --------------------------------------------------------------------------- #

def test_recency_weighting_prefers_fresher_event() -> None:
    # Legacy ranking helper — still tested directly (see note above).
    from systems.scout.outreach.research import _select_icebreaker

    events = [
        {
            "type": "behavioral_signal", "detail": "Older post",
            "source": "trigify_linkedin", "match_key": "profile", "recency_days": 80,
        },
        {
            "type": "behavioral_signal", "detail": "Newer post",
            "source": "trigify_linkedin", "match_key": "profile", "recency_days": 7,
        },
    ]
    detail, _ = _select_icebreaker(events)
    assert detail == "Newer post"


# --------------------------------------------------------------------------- #
# 6. Engagement weighting (trigify only)                                        #
# --------------------------------------------------------------------------- #

def test_engagement_weighting_prefers_high_engagement() -> None:
    # Legacy ranking helper — still tested directly (see note above).
    # Both profile-match, both same recency band (<30d); engagement is the tiebreak.
    from systems.scout.outreach.research import _select_icebreaker

    events = [
        {
            "type": "behavioral_signal", "detail": "Low engagement",
            "source": "trigify_linkedin", "match_key": "profile", "recency_days": 10,
            "engagement": {"likes": 1, "comments": 0, "shares": 0},  # sum=1
        },
        {
            "type": "behavioral_signal", "detail": "High engagement",
            "source": "trigify_linkedin", "match_key": "profile", "recency_days": 10,
            "engagement": {"likes": 40, "comments": 10, "shares": 5},  # sum=55
        },
    ]
    detail, _ = _select_icebreaker(events)
    assert detail == "High engagement"


# --------------------------------------------------------------------------- #
# 7. pain_category_preference honoured                                          #
# --------------------------------------------------------------------------- #

async def test_pain_category_preference_selects_matching_type() -> None:
    contact = mk_contact(citable_details=[
        {"type": "cost", "detail": "Paid $50k/mo on ads", "source": "about"},
        {"type": "growth", "detail": "Revenue doubled in 6 months", "source": "case_studies"},
    ])
    components = mk_default_components(
        pain_hook_metadata={"pain_category_preference": "growth"},
    )
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.pain_evidence == "Revenue doubled in 6 months"


async def test_pain_category_preference_falls_back_when_no_match() -> None:
    # Preference is set to a category that isn't present → fall back to first detail.
    contact = mk_contact(citable_details=[
        {"type": "cost", "detail": "Paid $50k/mo on ads", "source": "about"},
    ])
    components = mk_default_components(
        pain_hook_metadata={"pain_category_preference": "growth"},
    )
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.pain_evidence == "Paid $50k/mo on ads"


# --------------------------------------------------------------------------- #
# 8. pain_evidence fallback to buying_signals                                   #
# --------------------------------------------------------------------------- #

async def test_pain_evidence_falls_back_to_buying_signals() -> None:
    contact = mk_contact(
        citable_details=[],  # nothing citable
        buying_signals=[
            {"category": "hiring", "detail": "Hiring 5 SDRs right now", "source": "careers"},
        ],
    )
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.pain_evidence == "Hiring 5 SDRs right now"
    # The buying_signal should be recorded in the audit trail.
    pain_src = next(s for s in fills.sources_used if s["placeholder"] == "pain_evidence")
    assert pain_src["source"] == "careers"
    assert pain_src["type"] == "hiring"  # falls back from category when type missing


# --------------------------------------------------------------------------- #
# 9. cta_content passthrough — not looked up from research_data                 #
# --------------------------------------------------------------------------- #

async def test_cta_content_passthrough_from_component() -> None:
    # Rich research_data, no cta_content-like fields — selector must NOT invent
    # one; it must pull directly from the component.
    contact = mk_contact(
        citable_details=[{"type": "case_study", "detail": "ignored", "source": "x"}],
    )
    components = mk_default_components(cta_content="Book a time: https://cal.me/kirsten")
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.cta_content == "Book a time: https://cal.me/kirsten"
    # Audit entry records the component variant as the source.
    cta_src = next(s for s in fills.sources_used if s["placeholder"] == "cta_content")
    assert cta_src["source"].startswith("component:")
    assert cta_src["type"] == "component_passthrough"


async def test_cta_missing_from_selections_yields_none() -> None:
    contact = mk_contact()
    components = mk_default_components(include_cta=False)
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.cta_content is None
    assert not any(s["placeholder"] == "cta_content" for s in fills.sources_used)


# --------------------------------------------------------------------------- #
# 10. decision_log emission shape                                               #
# --------------------------------------------------------------------------- #

async def test_decision_log_emitted_with_correct_shape() -> None:
    contact = mk_contact(
        citable_details=[{"type": "case_study", "detail": "3x pipeline", "source": "case_studies"}],
        trigger_events=[
            {
                "type": "funding_round", "detail": "Raised Series B", "source": "claude_web_triggers",
                "recency_days": 10,
            },
        ],
    )
    # IcebreakerAdapter output — no trigger-events fallback in the select path.
    contact["research_data"]["icebreaker_content"] = "Saw their Iroko work this morning. Really sharp."
    components = mk_default_components()
    logger = FakeLogger()
    selector = ResearchSelector(decision_logger=logger)

    await selector.select_fills("client-1", contact, components)

    assert len(logger.entries) == 1
    entry = logger.entries[0]
    assert entry["client_id"] == "client-1"
    assert entry["decision_type"] == "research_contact"
    assert entry["decision"].startswith("research_fills:contact-1:")
    # 5 of 13 filled: the 4 enrich-sourced placeholders + first_name fallback.
    # No client_facts passed and no short_company_name on the contact -> the
    # other 8 productised slots are None (including the 3 new niche-level fills).
    assert entry["decision"].endswith(":5of13")
    assert entry["source"] == "system"
    assert entry["confidence"] is None

    context = entry["context"]
    assert context["contact_id"] == "contact-1"
    assert context["niche"] == "cro_growth_ugc_agency"
    assert context["dry_run"] is False
    assert context["placeholders_filled"] == [
        "icebreaker_content", "trigger_hook", "pain_evidence", "cta_content",
        "first_name",
    ]
    assert context["placeholders_empty"] == [
        "short_company_name", "operator_name",
        "offer_promise", "offer_period", "offer_risk_reversal",
        "niche", "niche_specific_term", "meetings_niche_term",
    ]
    assert isinstance(context["sources_used"], list)
    # 4 enrich sources + 1 first_name audit entry.
    assert len(context["sources_used"]) == 5
    # Component tuple records the variant_keys that were in play.
    assert context["component_tuple"]["cta"] == "cta_v1"
    assert context["component_tuple"]["pain_hook"] == "pain_hook_v1"


# --------------------------------------------------------------------------- #
# 11. dry_run=True still logs; context dry_run=True                             #
# --------------------------------------------------------------------------- #

async def test_dry_run_still_logs_but_marks_context() -> None:
    contact = mk_contact()
    components = mk_default_components()
    logger = FakeLogger()
    selector = ResearchSelector(decision_logger=logger)

    await selector.select_fills("client-1", contact, components, dry_run=True)

    assert len(logger.entries) == 1
    assert logger.entries[0]["context"]["dry_run"] is True


async def test_dry_run_does_not_change_selection_behaviour() -> None:
    contact = mk_contact(
        citable_details=[{"type": "case_study", "detail": "same fact", "source": "x"}],
    )
    components = mk_default_components()
    selector = ResearchSelector()

    dry = await selector.select_fills("client-1", contact, components, dry_run=True)
    live = await selector.select_fills("client-1", contact, components, dry_run=False)

    assert dry.icebreaker_content == live.icebreaker_content
    assert dry.trigger_hook == live.trigger_hook
    assert dry.pain_evidence == live.pain_evidence
    assert dry.cta_content == live.cta_content


# --------------------------------------------------------------------------- #
# 12. Exploding logger — selector returns fills, no crash                       #
# --------------------------------------------------------------------------- #

async def test_exploding_logger_does_not_crash_selector() -> None:
    contact = mk_contact(
        citable_details=[{"type": "case_study", "detail": "fact", "source": "x"}],
    )
    components = mk_default_components()
    selector = ResearchSelector(decision_logger=ExplodingLogger())

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.pain_evidence == "fact"
    assert fills.cta_content == "Worth a 20-minute call?"


# --------------------------------------------------------------------------- #
# 13. No logger injected — silent but functional                                #
# --------------------------------------------------------------------------- #

async def test_no_logger_returns_fills_silently() -> None:
    contact = mk_contact(
        citable_details=[{"type": "case_study", "detail": "fact", "source": "x"}],
    )
    components = mk_default_components()
    selector = ResearchSelector(decision_logger=None)

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.pain_evidence == "fact"


# --------------------------------------------------------------------------- #
# Extra: sources_used dedup when same source would fill multiple placeholders    #
# --------------------------------------------------------------------------- #

async def test_sources_used_deduplicates_across_placeholders() -> None:
    # Icebreaker comes from the adapter; trigger_hook comes from trigger_events.
    # These are now separately sourced (no trigger-events fallback for the
    # icebreaker slot), so the audit trail records one row per placeholder.
    event = {
        "type": "funding_round", "detail": "Raised Series B last month",
        "source": "claude_web_triggers", "recency_days": 10,
    }
    contact = mk_contact(trigger_events=[event])
    contact["research_data"]["icebreaker_content"] = "Saw their Iroko work this morning. Really sharp."
    components = mk_default_components(include_cta=False)
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.icebreaker_content == "Saw their Iroko work this morning. Really sharp."
    assert fills.trigger_hook == "Raised Series B last month"

    # Dedup is WITHIN (placeholder, source): each placeholder appears exactly
    # once in the audit trail.
    placeholders = [s["placeholder"] for s in fills.sources_used]
    assert placeholders.count("icebreaker_content") == 1
    assert placeholders.count("trigger_hook") == 1


async def test_sources_used_deduplicates_within_same_placeholder() -> None:
    # Contrived: cta component selected twice (simulated by passing same key);
    # audit must still record exactly one cta_content entry.
    from systems.scout.outreach.research import _append_passthrough

    sources: list[dict[str, Any]] = []
    variant = mk_variant(component_type="cta", variant_key="cta_x")
    _append_passthrough(sources, variant, "Book a call.")
    _append_passthrough(sources, variant, "Book a call.")

    assert len(sources) == 1
    assert sources[0]["placeholder"] == "cta_content"


# --------------------------------------------------------------------------- #
# Extra: malformed research_data entries don't crash                            #
# --------------------------------------------------------------------------- #

async def test_malformed_research_data_is_tolerated() -> None:
    contact = mk_contact(research_data_override={
        "citable_details": "not a list",          # wrong type
        "buying_signals": [None, 42, {}],          # non-dict + empty dict
        "trigger_events": None,                   # None
    })
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.icebreaker_content is None
    assert fills.trigger_hook is None
    # Empty dicts have no detail string → falls through to None.
    assert fills.pain_evidence is None
    # cta still works because it comes from the component, not research_data.
    assert fills.cta_content == "Worth a 20-minute call?"


# --------------------------------------------------------------------------- #
# Extra: firmographic type preferred over behavioral for trigger_hook           #
# --------------------------------------------------------------------------- #

async def test_trigger_hook_prefers_firmographic_over_behavioral() -> None:
    contact = mk_contact(trigger_events=[
        {
            "type": "behavioral_signal", "detail": "Posted recently",
            "source": "trigify_linkedin", "match_key": "profile", "recency_days": 3,
        },
        {
            "type": "executive_hire", "detail": "Hired new CRO",
            "source": "claude_web_triggers", "recency_days": 20,
        },
    ])
    # Icebreaker now comes from the adapter, not trigger_events.
    contact["research_data"]["icebreaker_content"] = "Saw their Iroko work this morning. Really sharp."
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    # Icebreaker sourced from the adapter output.
    assert fills.icebreaker_content == "Saw their Iroko work this morning. Really sharp."
    # Trigger-hook prefers the firmographic executive_hire.
    assert fills.trigger_hook == "Hired new CRO"


async def test_trigger_hook_drops_events_older_than_max_recency() -> None:
    contact = mk_contact(trigger_events=[
        {
            "type": "funding_round", "detail": "Raised Series B (stale)",
            "source": "claude_web_triggers", "recency_days": 200,
        },
    ])
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.trigger_hook is None


async def test_trigger_hook_falls_back_to_behavioral_when_no_firmographic() -> None:
    contact = mk_contact(trigger_events=[
        {
            "type": "behavioral_signal", "detail": "Fresh post",
            "source": "trigify_linkedin", "match_key": "domain", "recency_days": 5,
        },
    ])
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.trigger_hook == "Fresh post"


# --------------------------------------------------------------------------- #
# Extra: no pain_hook metadata → takes first citable_detail                     #
# --------------------------------------------------------------------------- #

async def test_pain_evidence_without_preference_takes_first_citable() -> None:
    contact = mk_contact(citable_details=[
        {"type": "case_study", "detail": "First detail", "source": "x"},
        {"type": "case_study", "detail": "Second detail", "source": "y"},
    ])
    # No pain_category_preference set.
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.pain_evidence == "First detail"


# --------------------------------------------------------------------------- #
# Extra: detail truncation cap                                                  #
# --------------------------------------------------------------------------- #

async def test_detail_truncated_to_max_chars() -> None:
    very_long = "x" * 300
    contact = mk_contact(citable_details=[
        {"type": "case_study", "detail": very_long, "source": "x"},
    ])
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.pain_evidence is not None
    assert len(fills.pain_evidence) == 160


# --------------------------------------------------------------------------- #
# Productised placeholder contract — _select_first_name                         #
# --------------------------------------------------------------------------- #

def test_select_first_name_returns_stripped_value_when_present() -> None:
    from systems.scout.outreach.research import _select_first_name

    assert _select_first_name({"first_name": "  Jane  "}) == "Jane"


def test_select_first_name_falls_back_when_empty_or_missing() -> None:
    from systems.scout.outreach.research import _select_first_name

    assert _select_first_name({"first_name": ""}) == "there"
    assert _select_first_name({"first_name": "   "}) == "there"
    assert _select_first_name({}) == "there"
    assert _select_first_name({"first_name": None}) == "there"
    assert _select_first_name({"first_name": 42}) == "there"  # type: ignore[dict-item]


# --------------------------------------------------------------------------- #
# Productised placeholder contract — _select_short_company_name                 #
# --------------------------------------------------------------------------- #

def test_select_short_company_name_reads_from_research_data() -> None:
    from systems.scout.outreach.research import _select_short_company_name

    contact = {"research_data": {"short_company_name": "Acme"}}
    assert _select_short_company_name(contact) == "Acme"


def test_select_short_company_name_strips_whitespace() -> None:
    from systems.scout.outreach.research import _select_short_company_name

    contact = {"research_data": {"short_company_name": "  Acme  "}}
    assert _select_short_company_name(contact) == "Acme"


def test_select_short_company_name_returns_none_on_empty_or_missing() -> None:
    from systems.scout.outreach.research import _select_short_company_name

    assert _select_short_company_name({"research_data": {"short_company_name": ""}}) is None
    assert _select_short_company_name({"research_data": {"short_company_name": "   "}}) is None
    assert _select_short_company_name({"research_data": {}}) is None
    assert _select_short_company_name({}) is None


def test_select_short_company_name_tolerates_non_dict_research_data() -> None:
    from systems.scout.outreach.research import _select_short_company_name

    assert _select_short_company_name({"research_data": "garbage"}) is None
    assert _select_short_company_name({"research_data": None}) is None


# --------------------------------------------------------------------------- #
# Productised placeholder contract — _select_from_client_facts                  #
# --------------------------------------------------------------------------- #

def test_select_from_client_facts_returns_value_when_present() -> None:
    from systems.scout.outreach.research import _select_from_client_facts

    assert _select_from_client_facts({"operator_name": "Kirsten"}, "operator_name") == "Kirsten"


def test_select_from_client_facts_strips_whitespace() -> None:
    from systems.scout.outreach.research import _select_from_client_facts

    assert _select_from_client_facts({"operator_name": "  Kirsten  "}, "operator_name") == "Kirsten"


def test_select_from_client_facts_none_on_missing_or_bad_type() -> None:
    from systems.scout.outreach.research import _select_from_client_facts

    assert _select_from_client_facts({}, "operator_name") is None
    assert _select_from_client_facts({"operator_name": ""}, "operator_name") is None
    assert _select_from_client_facts({"operator_name": "   "}, "operator_name") is None
    assert _select_from_client_facts({"operator_name": None}, "operator_name") is None
    assert _select_from_client_facts({"operator_name": 42}, "operator_name") is None


# --------------------------------------------------------------------------- #
# Productised placeholder contract — select_fills integration                   #
# --------------------------------------------------------------------------- #

async def test_select_fills_with_full_client_facts_populates_all_six() -> None:
    contact = mk_contact()
    # Seed short_company_name in research_data.
    contact["research_data"]["short_company_name"] = "Acme"
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills(
        "client-1", contact, components,
        client_facts={
            "operator_name": "Kirsten",
            "offer_promise": "20 booked calls",
            "offer_period": "30 days",
            "offer_risk_reversal": "or you don't pay",
        },
    )

    assert fills.first_name == "Jane"
    assert fills.short_company_name == "Acme"
    assert fills.operator_name == "Kirsten"
    assert fills.offer_promise == "20 booked calls"
    assert fills.offer_period == "30 days"
    assert fills.offer_risk_reversal == "or you don't pay"

    # Audit trail records every productised source.
    sources_by_pl = {s["placeholder"]: s for s in fills.sources_used}
    assert sources_by_pl["first_name"]["source"] == "contact_column"
    assert sources_by_pl["first_name"]["type"] == "identity"
    assert sources_by_pl["short_company_name"]["source"] == "contact_research_data"
    assert sources_by_pl["short_company_name"]["type"] == "identity"
    for key in ("operator_name", "offer_promise", "offer_period", "offer_risk_reversal"):
        assert sources_by_pl[key]["source"] == "client_facts"
        assert sources_by_pl[key]["type"] == "client_fact"


async def test_select_fills_without_client_facts_defaults_to_none() -> None:
    contact = mk_contact()  # no short_company_name in research_data
    components = mk_default_components()
    selector = ResearchSelector()

    # Default path — no kwarg, no crash.
    fills = await selector.select_fills("client-1", contact, components)

    # first_name still falls back to the contact column.
    assert fills.first_name == "Jane"
    assert fills.short_company_name is None
    assert fills.operator_name is None
    assert fills.offer_promise is None
    assert fills.offer_period is None
    assert fills.offer_risk_reversal is None
    # v2 niche-level fills default to None when client_facts empty.
    assert fills.niche is None
    assert fills.niche_specific_term is None
    assert fills.meetings_niche_term is None


async def test_select_fills_populates_niche_level_fields_from_client_facts() -> None:
    """v2: niche / niche_specific_term / meetings_niche_term source from
    client_facts and surface as separate ResearchFills attrs."""
    contact = mk_contact()
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills(
        "client-1", contact, components,
        client_facts={
            "niche": "creative and branding agencies",
            "niche_specific_term": "clients",
            "meetings_niche_term": "sales calls",
        },
    )

    assert fills.niche == "creative and branding agencies"
    assert fills.niche_specific_term == "clients"
    assert fills.meetings_niche_term == "sales calls"

    # Audit trail records every niche-level source as client_facts.
    sources_by_pl = {s["placeholder"]: s for s in fills.sources_used}
    for key in ("niche", "niche_specific_term", "meetings_niche_term"):
        assert sources_by_pl[key]["source"] == "client_facts"
        assert sources_by_pl[key]["type"] == "client_fact"


async def test_select_fills_partial_niche_level_fields() -> None:
    """Only the keys present in client_facts should fill; others stay None."""
    contact = mk_contact()
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills(
        "client-1", contact, components,
        client_facts={"niche": "creative and branding agencies"},
    )

    assert fills.niche == "creative and branding agencies"
    assert fills.niche_specific_term is None
    assert fills.meetings_niche_term is None


async def test_select_fills_with_blank_first_name_uses_there_fallback() -> None:
    contact = mk_contact(first_name="")
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.first_name == "there"
    # Audit trail still records the fill — placeholder is always filled.
    first_name_src = next(s for s in fills.sources_used if s["placeholder"] == "first_name")
    assert first_name_src["source"] == "contact_column"


async def test_select_fills_partial_client_facts_fills_only_present_keys() -> None:
    contact = mk_contact()
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills(
        "client-1", contact, components,
        client_facts={"operator_name": "Kirsten"},
    )

    assert fills.operator_name == "Kirsten"
    assert fills.offer_promise is None
    assert fills.offer_period is None
    assert fills.offer_risk_reversal is None


async def test_select_fills_decision_log_reports_13_of_13_surface() -> None:
    """Regression guard: after extending PLACEHOLDER_FIELDS the decision-log
    'filled N of total' ratio must reflect the productised surface.

    v2 adds niche, niche_specific_term, meetings_niche_term → total = 13."""
    contact = mk_contact(
        citable_details=[{"type": "case_study", "detail": "fact", "source": "x"}],
        trigger_events=[
            {
                "type": "funding_round", "detail": "Raised Series B",
                "source": "claude_web_triggers", "recency_days": 10,
            },
        ],
    )
    contact["research_data"]["short_company_name"] = "Acme"
    # IcebreakerAdapter output fills the icebreaker slot (no trigger-events fallback).
    contact["research_data"]["icebreaker_content"] = "Saw their Iroko work this morning. Really sharp."
    components = mk_default_components()
    logger = FakeLogger()
    selector = ResearchSelector(decision_logger=logger)

    await selector.select_fills(
        "client-1", contact, components,
        client_facts={
            "operator_name": "Kirsten",
            "offer_promise": "20 calls",
            "offer_period": "30 days",
            "offer_risk_reversal": "or free",
            "niche": "creative and branding agencies",
            "niche_specific_term": "clients",
            "meetings_niche_term": "sales calls",
        },
    )

    entry = logger.entries[0]
    # 13 placeholders, all 13 filled.
    assert entry["decision"].endswith(":13of13")
    assert entry["context"]["placeholders_empty"] == []
    assert set(entry["context"]["placeholders_filled"]) == {
        "icebreaker_content", "trigger_hook", "pain_evidence", "cta_content",
        "first_name", "short_company_name", "operator_name",
        "offer_promise", "offer_period", "offer_risk_reversal",
        "niche", "niche_specific_term", "meetings_niche_term",
    }


# --------------------------------------------------------------------------- #
# _select_icebreaker_content — adapter output takes priority                    #
# --------------------------------------------------------------------------- #

async def test_icebreaker_content_prefers_adapter_output_over_trigger_events() -> None:
    contact = mk_contact(trigger_events=[
        {
            "type": "behavioral_signal", "detail": "Legacy trigger-event icebreaker",
            "source": "trigify_linkedin", "match_key": "profile", "recency_days": 5,
        },
    ])
    # IcebreakerAdapter (Task D) writes this — must win over trigger_events.
    contact["research_data"]["icebreaker_content"] = "Adapter-written line"
    contact["research_data"]["icebreaker_tier"] = "tier_1"
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.icebreaker_content == "Adapter-written line"
    ice_src = next(s for s in fills.sources_used if s["placeholder"] == "icebreaker_content")
    assert ice_src["source"] == "icebreaker_adapter:tier_tier_1"
    assert ice_src["type"] == "icebreaker"


def test_select_icebreaker_content_returns_none_when_adapter_absent() -> None:
    # No trigger-events fallback: when IcebreakerAdapter output is blank/absent,
    # _select_icebreaker_content returns (None, None) even if trigger_events
    # are populated. The old fallback silently bypassed voice validation and
    # banned-word checks, so it was removed — adapter failures are now visible
    # via fills_missing.
    from systems.scout.outreach.research import _select_icebreaker_content

    contact = {
        "research_data": {
            "icebreaker_content": "   ",  # blank adapter output
            "trigger_events": [
                {
                    "type": "funding_round", "detail": "Raised Series B",
                    "source": "claude_web_triggers", "match_key": "profile",
                    "recency_days": 10,
                },
            ],
        },
    }
    detail, src = _select_icebreaker_content(contact)

    assert detail is None
    assert src is None


def test_select_icebreaker_content_returns_none_when_both_empty() -> None:
    from systems.scout.outreach.research import _select_icebreaker_content

    contact: dict[str, Any] = {"research_data": {}}
    detail, src = _select_icebreaker_content(contact)

    assert detail is None
    assert src is None


def test_select_icebreaker_content_no_tier_uses_generic_source() -> None:
    from systems.scout.outreach.research import _select_icebreaker_content

    contact = {"research_data": {"icebreaker_content": "Adapter line"}}  # no tier
    detail, src = _select_icebreaker_content(contact)

    assert detail == "Adapter line"
    assert src is not None
    assert src["source"] == "icebreaker_adapter"


def test_select_icebreaker_content_tolerates_non_dict_research_data() -> None:
    from systems.scout.outreach.research import _select_icebreaker_content

    contact = {"research_data": "garbage"}
    detail, src = _select_icebreaker_content(contact)

    # Non-dict research_data -> (None, None); no trigger-events fallback.
    assert detail is None
    assert src is None
