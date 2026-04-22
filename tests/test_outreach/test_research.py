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
    components = mk_default_components()
    logger = FakeLogger()
    selector = ResearchSelector(decision_logger=logger)

    fills = await selector.select_fills("client-1", contact, components)

    assert isinstance(fills, ResearchFills)
    assert fills.icebreaker_content == "Raised Series B last month"
    assert fills.trigger_hook == "Raised Series B last month"
    assert fills.pain_evidence == "Grew client pipeline 3x in 90d"
    assert fills.cta_content == "Worth a 20-minute call?"
    assert len(fills.sources_used) == 4  # one per placeholder


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
    assert fills.sources_used == []


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

async def test_profile_match_preferred_over_domain_match() -> None:
    contact = mk_contact(trigger_events=[
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
    ])
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.icebreaker_content == "Profile match event"


# --------------------------------------------------------------------------- #
# 5. Recency weighting — recent (7d) preferred over older (80d) same match_key  #
# --------------------------------------------------------------------------- #

async def test_recency_weighting_prefers_fresher_event() -> None:
    contact = mk_contact(trigger_events=[
        {
            "type": "behavioral_signal", "detail": "Older post",
            "source": "trigify_linkedin", "match_key": "profile", "recency_days": 80,
        },
        {
            "type": "behavioral_signal", "detail": "Newer post",
            "source": "trigify_linkedin", "match_key": "profile", "recency_days": 7,
        },
    ])
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.icebreaker_content == "Newer post"


# --------------------------------------------------------------------------- #
# 6. Engagement weighting (trigify only)                                        #
# --------------------------------------------------------------------------- #

async def test_engagement_weighting_prefers_high_engagement() -> None:
    # Both profile-match, both same recency band (<30d); engagement is the tiebreak.
    contact = mk_contact(trigger_events=[
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
    ])
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    assert fills.icebreaker_content == "High engagement"


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
    components = mk_default_components()
    logger = FakeLogger()
    selector = ResearchSelector(decision_logger=logger)

    await selector.select_fills("client-1", contact, components)

    assert len(logger.entries) == 1
    entry = logger.entries[0]
    assert entry["client_id"] == "client-1"
    assert entry["decision_type"] == "research_contact"
    assert entry["decision"].startswith("research_fills:contact-1:")
    assert entry["decision"].endswith(":4of4")
    assert entry["source"] == "system"
    assert entry["confidence"] is None

    context = entry["context"]
    assert context["contact_id"] == "contact-1"
    assert context["niche"] == "cro_growth_ugc_agency"
    assert context["dry_run"] is False
    assert context["placeholders_filled"] == [
        "icebreaker_content", "trigger_hook", "pain_evidence", "cta_content",
    ]
    assert context["placeholders_empty"] == []
    assert isinstance(context["sources_used"], list)
    assert len(context["sources_used"]) == 4
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
    # One funding_round event satisfies BOTH icebreaker and trigger_hook.
    event = {
        "type": "funding_round", "detail": "Raised Series B last month",
        "source": "claude_web_triggers", "recency_days": 10,
    }
    contact = mk_contact(trigger_events=[event])
    components = mk_default_components(include_cta=False)
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    # Both placeholders should be filled from the same event.
    assert fills.icebreaker_content == "Raised Series B last month"
    assert fills.trigger_hook == "Raised Series B last month"

    # Different placeholders with same source are allowed (one each, Plan 7 needs
    # per-placeholder rows). Dedup is WITHIN (placeholder, source) — verified via
    # a second call where we pretend the helper re-ran: source still appears once
    # per placeholder. So for this test we just assert the expected pair shape.
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
    components = mk_default_components()
    selector = ResearchSelector()

    fills = await selector.select_fills("client-1", contact, components)

    # Icebreaker prefers the behavioral profile-match.
    assert fills.icebreaker_content == "Posted recently"
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
