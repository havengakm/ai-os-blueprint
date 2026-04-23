"""Tests for Composer — bandit component selection + placeholder rendering.

Style mirrors tests/test_outreach/test_research.py: in-memory fakes for the
storage backend, a real ResearchSelector wrapping a FakeLogger, and small
factories (mk_contact, mk_variant, mk_variants_by_type) so each test body
focuses on the one rule it exercises.
"""
from __future__ import annotations

import random
from typing import Any

import pytest

from systems.scout.outreach import (
    AD_ACTIVITY_DIRECTORIES,  # noqa: F401  (surface export smoke)
    Composer,
    ComposedDraft,
    ComposerSkip,
    ComponentVariant,
    ResearchSelector,
)
from systems.scout.outreach.composer import (
    _humanize_platforms,
    _render_ad_activity_observation,
)


# --------------------------------------------------------------------------- #
# Fakes                                                                         #
# --------------------------------------------------------------------------- #

class FakeLogger:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def log_decision(self, client_id: str, **kwargs: Any) -> str:
        self.entries.append({"client_id": client_id, **kwargs})
        return "fake-decision-id"


class ExplodingLogger:
    async def log_decision(self, client_id: str, **kwargs: Any) -> str:
        raise RuntimeError("logger exploded")


class FakeStorage:
    """In-memory composer backend.

    Accepts a pre-built variants_by_type map + active_directories list.
    Records persist_draft calls; optionally raises to simulate failures.
    """

    def __init__(
        self,
        *,
        variants_by_type: dict[str, list[ComponentVariant]] | None = None,
        active_directories: list[str] | None = None,
        persist_raises: Exception | None = None,
        logger: FakeLogger | ExplodingLogger | None = None,
    ) -> None:
        self._variants_by_type = variants_by_type or {}
        self._active_directories = active_directories or []
        self._persist_raises = persist_raises
        self._logger = logger or FakeLogger()
        self.persisted_drafts: list[dict[str, Any]] = []
        self.fetch_variants_calls: list[tuple[str, str, str]] = []

    async def fetch_approved_variants(
        self, client_id: str, niche: str, offer_label: str,
    ) -> dict[str, list[ComponentVariant]]:
        self.fetch_variants_calls.append((client_id, niche, offer_label))
        # Return shallow copies so composer filter doesn't mutate our backing store.
        return {
            ct: list(vs) for ct, vs in self._variants_by_type.items()
        }

    async def fetch_active_directories(self, client_id: str) -> list[str]:
        return list(self._active_directories)

    async def persist_draft(
        self,
        client_id: str,
        contact_id: str,
        *,
        subject: str,
        body: str,
        component_selections: dict[str, str],
        research_sources: list[dict[str, Any]],
    ) -> str:
        if self._persist_raises is not None:
            raise self._persist_raises
        draft = {
            "client_id": client_id,
            "contact_id": contact_id,
            "subject": subject,
            "body": body,
            "component_selections": component_selections,
            "research_sources": research_sources,
        }
        self.persisted_drafts.append(draft)
        return f"draft-{len(self.persisted_drafts)}"

    async def log_decision(self, client_id: str, **kwargs: Any) -> str | None:
        return await self._logger.log_decision(client_id, **kwargs)

    @property
    def logger(self) -> FakeLogger | ExplodingLogger:
        return self._logger


# --------------------------------------------------------------------------- #
# Factories                                                                     #
# --------------------------------------------------------------------------- #

def mk_variant(
    *,
    component_type: str,
    variant_key: str | None = None,
    variant_content: str = "default content",
    metadata: dict[str, Any] | None = None,
    win_rate: float | None = None,
    sample_size: int = 0,
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
        win_rate=win_rate,
        sample_size=sample_size,
    )


def mk_variants_by_type(
    *,
    subject_content: str = "Subject: {{trigger_hook}}",
    icebreaker_content: str = "Hi {{first_name}}, noticed {{icebreaker_content}}.",
    pain_hook_content: str = "Many agencies hit {{pain_evidence}}.",
    offer_frame_content: str = "We help with X at {{company}}.",
    cta_content: str = "Worth a 20-minute call?",
    signature_content: str = "—Kirsten",
) -> dict[str, list[ComponentVariant]]:
    return {
        "subject_line": [mk_variant(component_type="subject_line", variant_content=subject_content)],
        "icebreaker": [mk_variant(component_type="icebreaker", variant_content=icebreaker_content)],
        "pain_hook": [mk_variant(component_type="pain_hook", variant_content=pain_hook_content)],
        "offer_frame": [mk_variant(component_type="offer_frame", variant_content=offer_frame_content)],
        "cta": [mk_variant(component_type="cta", variant_content=cta_content)],
        "signature": [mk_variant(component_type="signature", variant_content=signature_content)],
    }


def mk_contact(
    *,
    contact_id: str = "contact-1",
    first_name: str | None = "Jane",
    company: str = "Acme Corp",
    niche: str = "cro_growth_ugc_agency",
    offer_label: str = "pipeline_audit",
    sequence_round: int = 1,
    citable_details: list[dict[str, Any]] | None = None,
    buying_signals: list[dict[str, Any]] | None = None,
    trigger_events: list[dict[str, Any]] | None = None,
    ad_activity: dict[str, Any] | None = None,
    research_data_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if research_data_override is not None:
        research_data = research_data_override
    else:
        research_data = {
            "citable_details": citable_details or [],
            "buying_signals": buying_signals or [],
            "trigger_events": trigger_events or [],
        }
        if ad_activity is not None:
            research_data["ad_activity"] = ad_activity
    return {
        "contact_id": contact_id,
        "first_name": first_name,
        "company": company,
        "niche": niche,
        "offer_label": offer_label,
        "sequence_round": sequence_round,
        "research_data": research_data,
    }


def mk_composer(
    storage: FakeStorage,
    *,
    epsilon: float = 0.1,
    rng: random.Random | None = None,
    research_logger: FakeLogger | None = None,
) -> Composer:
    return Composer(
        storage,
        ResearchSelector(decision_logger=research_logger),
        epsilon=epsilon,
        rng=rng or random.Random(42),
    )


def _render_entry(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Find the composer's render_draft log entry (ignores research_contact)."""
    return next(e for e in entries if e["decision_type"] == "render_draft")


# --------------------------------------------------------------------------- #
# 1. Happy path                                                                 #
# --------------------------------------------------------------------------- #

async def test_happy_path_fills_renders_persists_logs() -> None:
    contact = mk_contact(
        citable_details=[
            {"type": "case_study", "detail": "Grew pipeline 3x in 90d", "source": "case_studies"},
        ],
        trigger_events=[
            {
                "type": "funding_round", "detail": "Raised Series B last month",
                "source": "claude_web_triggers", "recency_days": 15,
            },
        ],
    )
    storage = FakeStorage(variants_by_type=mk_variants_by_type())
    composer = mk_composer(storage)

    result = await composer.compose("client-1", contact)

    assert isinstance(result, ComposedDraft)
    assert result.contact_id == "contact-1"
    assert result.subject == "Subject: Raised Series B last month"
    assert "Hi Jane, noticed Raised Series B last month" in result.body
    assert "Many agencies hit Grew pipeline 3x in 90d" in result.body
    assert "We help with X at Acme Corp" in result.body
    assert result.body.endswith("Worth a 20-minute call?\n\n—Kirsten")
    assert result.component_selections == {
        "subject_line": "subject_line_v1", "icebreaker": "icebreaker_v1",
        "pain_hook": "pain_hook_v1", "offer_frame": "offer_frame_v1",
        "cta": "cta_v1", "signature": "signature_v1",
    }
    assert result.fills_missing == []
    assert result.persisted_draft_id == "draft-1"
    assert len(storage.persisted_drafts) == 1
    # decision_log entry emitted with render_draft type
    render_entry = _render_entry(storage.logger.entries)
    assert render_entry["decision"].startswith("render_draft:contact-1:Subject:")
    assert render_entry["context"]["component_tuple"]["cta"] == "cta_v1"


# --------------------------------------------------------------------------- #
# 2. Bandit — pure exploit                                                      #
# --------------------------------------------------------------------------- #

async def test_bandit_pure_exploit_picks_highest_win_rate() -> None:
    # Three subject variants with different win_rates; epsilon=0 means always
    # exploit the top scorer.
    variants = mk_variants_by_type()
    variants["subject_line"] = [
        mk_variant(component_type="subject_line", variant_key="sub_low", variant_content="low", win_rate=0.05, sample_size=100),
        mk_variant(component_type="subject_line", variant_key="sub_high", variant_content="high", win_rate=0.40, sample_size=100),
        mk_variant(component_type="subject_line", variant_key="sub_mid", variant_content="mid", win_rate=0.20, sample_size=100),
    ]
    storage = FakeStorage(variants_by_type=variants)
    composer = mk_composer(storage, epsilon=0.0)

    result = await composer.compose("client-1", mk_contact())

    assert isinstance(result, ComposedDraft)
    assert result.subject == "high"
    assert result.component_selections["subject_line"] == "sub_high"


# --------------------------------------------------------------------------- #
# 3. Bandit — pure explore                                                      #
# --------------------------------------------------------------------------- #

async def test_bandit_pure_explore_is_random() -> None:
    # With epsilon=1.0 + a two-variant pool where one has a crushing win_rate,
    # we must still observe the low-win variant across seeds — proving exploit
    # is NOT being consulted. Sweep seeds and confirm both outcomes appear.
    keys_seen: set[str] = set()
    for seed in range(30):
        variants = mk_variants_by_type()
        variants["subject_line"] = [
            mk_variant(component_type="subject_line", variant_key="sub_a", variant_content="a", win_rate=0.99),
            mk_variant(component_type="subject_line", variant_key="sub_b", variant_content="b", win_rate=0.01),
        ]
        storage = FakeStorage(variants_by_type=variants)
        composer = mk_composer(storage, epsilon=1.0, rng=random.Random(seed))

        result = await composer.compose("client-1", mk_contact())

        assert isinstance(result, ComposedDraft)
        keys_seen.add(result.component_selections["subject_line"])
        if keys_seen == {"sub_a", "sub_b"}:
            break
    assert keys_seen == {"sub_a", "sub_b"}, (
        f"epsilon=1.0 should explore both variants; only saw {keys_seen}"
    )


# --------------------------------------------------------------------------- #
# 4. Bandit — no win_rate → neutral prior, random tiebreak                      #
# --------------------------------------------------------------------------- #

async def test_bandit_no_win_rate_data_random_tiebreak() -> None:
    variants = mk_variants_by_type()
    variants["subject_line"] = [
        mk_variant(component_type="subject_line", variant_key="sub_a", variant_content="a"),
        mk_variant(component_type="subject_line", variant_key="sub_b", variant_content="b"),
        mk_variant(component_type="subject_line", variant_key="sub_c", variant_content="c"),
    ]
    storage = FakeStorage(variants_by_type=variants)
    composer = mk_composer(storage, epsilon=0.0, rng=random.Random(99))

    result = await composer.compose("client-1", mk_contact())
    # Seeded RNG, pure exploit, all tied at 0.5 prior → random.choice from leaders.
    assert isinstance(result, ComposedDraft)
    assert result.component_selections["subject_line"] in {"sub_a", "sub_b", "sub_c"}

    # Different seed picks a different winner (proves randomness is engaged).
    storage2 = FakeStorage(variants_by_type={
        **variants,
        "subject_line": [
            mk_variant(component_type="subject_line", variant_key="sub_a", variant_content="a"),
            mk_variant(component_type="subject_line", variant_key="sub_b", variant_content="b"),
            mk_variant(component_type="subject_line", variant_key="sub_c", variant_content="c"),
        ],
    })
    composer2 = mk_composer(storage2, epsilon=0.0, rng=random.Random(1))
    result2 = await composer2.compose("client-1", mk_contact())
    assert isinstance(result2, ComposedDraft)
    # At least one of the two seeds should land on a different key — we assert
    # that the set of reachable keys is >1 by trying a few seeds.
    keys_seen: set[str] = {result.component_selections["subject_line"], result2.component_selections["subject_line"]}
    if len(keys_seen) == 1:
        for seed in range(2, 50):
            st = FakeStorage(variants_by_type={
                **variants,
                "subject_line": [
                    mk_variant(component_type="subject_line", variant_key="sub_a", variant_content="a"),
                    mk_variant(component_type="subject_line", variant_key="sub_b", variant_content="b"),
                    mk_variant(component_type="subject_line", variant_key="sub_c", variant_content="c"),
                ],
            })
            cx = mk_composer(st, epsilon=0.0, rng=random.Random(seed))
            r = await cx.compose("client-1", mk_contact())
            assert isinstance(r, ComposedDraft)
            keys_seen.add(r.component_selections["subject_line"])
            if len(keys_seen) > 1:
                break
    assert len(keys_seen) > 1


# --------------------------------------------------------------------------- #
# 5. Bandit — sample_size tiebreak                                              #
# --------------------------------------------------------------------------- #

async def test_bandit_sample_size_breaks_win_rate_tie() -> None:
    variants = mk_variants_by_type()
    variants["subject_line"] = [
        mk_variant(component_type="subject_line", variant_key="sub_small", variant_content="small", win_rate=0.30, sample_size=20),
        mk_variant(component_type="subject_line", variant_key="sub_big", variant_content="big", win_rate=0.30, sample_size=500),
        mk_variant(component_type="subject_line", variant_key="sub_mid", variant_content="mid", win_rate=0.30, sample_size=100),
    ]
    storage = FakeStorage(variants_by_type=variants)
    composer = mk_composer(storage, epsilon=0.0, rng=random.Random(0))

    result = await composer.compose("client-1", mk_contact())

    assert isinstance(result, ComposedDraft)
    # Largest sample_size wins outright — no RNG should be invoked.
    assert result.component_selections["subject_line"] == "sub_big"


# --------------------------------------------------------------------------- #
# 6. Skip on zero variants for a required type                                  #
# --------------------------------------------------------------------------- #

async def test_skip_when_required_component_type_has_zero_variants() -> None:
    variants = mk_variants_by_type()
    variants["cta"] = []  # no approved cta
    storage = FakeStorage(variants_by_type=variants)
    composer = mk_composer(storage)

    result = await composer.compose("client-1", mk_contact())

    assert isinstance(result, ComposerSkip)
    assert result.reason == "no_variants_for:cta"
    # decision_log records the skip.
    entry = _render_entry(storage.logger.entries)
    assert entry["context"]["skip_reason"] == "no_variants_for:cta"


# --------------------------------------------------------------------------- #
# 7. Ad-activity filtering — OFF — drops dependent variants                     #
# --------------------------------------------------------------------------- #

async def test_ad_activity_variants_filtered_when_directories_not_enabled() -> None:
    variants = mk_variants_by_type()
    # Add a second icebreaker variant that references ad_activity_observation.
    variants["icebreaker"] = [
        mk_variant(
            component_type="icebreaker",
            variant_key="ice_safe",
            variant_content="Hi {{first_name}}, plain icebreaker.",
        ),
        mk_variant(
            component_type="icebreaker",
            variant_key="ice_ad",
            variant_content="Hi {{first_name}}, saw {{ad_activity_observation}}",
            win_rate=0.99,  # would win bandit if not filtered out
        ),
    ]
    # No active directories → ad-activity variants must be filtered.
    storage = FakeStorage(variants_by_type=variants, active_directories=[])
    composer = mk_composer(storage, epsilon=0.0)

    result = await composer.compose("client-1", mk_contact())

    assert isinstance(result, ComposedDraft)
    assert result.component_selections["icebreaker"] == "ice_safe"


async def test_skip_when_ad_activity_filtering_empties_a_type() -> None:
    variants = mk_variants_by_type()
    # The ONLY icebreaker references ad_activity_observation; filtering empties the pool.
    variants["icebreaker"] = [
        mk_variant(
            component_type="icebreaker",
            variant_key="ice_ad_only",
            variant_content="Hi {{first_name}}, saw {{ad_activity_observation}}",
        ),
    ]
    storage = FakeStorage(variants_by_type=variants, active_directories=[])
    composer = mk_composer(storage)

    result = await composer.compose("client-1", mk_contact())

    assert isinstance(result, ComposerSkip)
    assert result.reason == "no_variants_for:icebreaker"
    assert result.details["ad_activity_enabled"] is False


# --------------------------------------------------------------------------- #
# 8. Ad-activity filtering — ON — dependent variants remain in the pool         #
# --------------------------------------------------------------------------- #

async def test_ad_activity_variants_kept_when_directory_enabled() -> None:
    variants = mk_variants_by_type()
    variants["icebreaker"] = [
        mk_variant(
            component_type="icebreaker",
            variant_key="ice_safe",
            variant_content="Hi {{first_name}}, plain.",
            win_rate=0.10,
        ),
        mk_variant(
            component_type="icebreaker",
            variant_key="ice_ad",
            variant_content="Hi {{first_name}}, saw {{ad_activity_observation}}",
            win_rate=0.99,
        ),
    ]
    storage = FakeStorage(
        variants_by_type=variants,
        active_directories=["google_ads_library"],
    )
    composer = mk_composer(storage, epsilon=0.0)  # pure exploit
    contact = mk_contact(ad_activity={
        "ad_count": 12, "platforms": ["google"], "active_within_days": 30,
    })

    result = await composer.compose("client-1", contact)

    assert isinstance(result, ComposedDraft)
    # The higher-win variant IS selected (filter didn't drop it).
    assert result.component_selections["icebreaker"] == "ice_ad"
    assert "Running 12 Google ads over the last 30 days." in result.body


# --------------------------------------------------------------------------- #
# 9. _render_ad_activity_observation — valid payload                            #
# --------------------------------------------------------------------------- #

def test_render_ad_activity_observation_renders_full_sentence() -> None:
    sentence = _render_ad_activity_observation({
        "ad_count": 12, "platforms": ["google"], "active_within_days": 30,
    })
    assert sentence == "Running 12 Google ads over the last 30 days."


def test_render_ad_activity_observation_multiple_platforms() -> None:
    sentence = _render_ad_activity_observation({
        "ad_count": 5, "platforms": ["google", "linkedin"], "active_within_days": 14,
    })
    assert sentence == "Running 5 Google + LinkedIn ads over the last 14 days."


# --------------------------------------------------------------------------- #
# 10. _render_ad_activity_observation — missing / malformed payload             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("payload", [
    None,
    {},
    {"ad_count": 0, "platforms": ["google"]},
    {"ad_count": -2, "platforms": ["google"]},
    {"ad_count": 5, "platforms": []},
    {"ad_count": 5, "platforms": "google"},     # wrong type
    {"ad_count": 5, "platforms": [None, 0]},    # no valid strings
    {"ad_count": "12", "platforms": ["google"]},  # str not int
    {"ad_count": True, "platforms": ["google"]},  # bool sneaking past isinstance(int)
    "not a dict",
    42,
])
def test_render_ad_activity_observation_returns_empty_on_bad_input(payload: Any) -> None:
    assert _render_ad_activity_observation(payload) == ""


def test_render_ad_activity_observation_defaults_window_to_30() -> None:
    sentence = _render_ad_activity_observation({
        "ad_count": 1, "platforms": ["google"],  # no active_within_days
    })
    assert "over the last 30 days" in sentence


# --------------------------------------------------------------------------- #
# 11. _humanize_platforms dedup + case-insensitive                              #
# --------------------------------------------------------------------------- #

def test_humanize_platforms_dedups_and_maps_labels() -> None:
    assert _humanize_platforms(["google", "LINKEDIN", "google"]) == "Google + LinkedIn"


def test_humanize_platforms_falls_back_to_title_case_for_unknown() -> None:
    assert _humanize_platforms(["snapchat"]) == "Snapchat"


# --------------------------------------------------------------------------- #
# 12. first_name fallback                                                       #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("first_name,expected_greeting", [
    (None, "Hi there,"),
    ("", "Hi there,"),
    ("   ", "Hi there,"),
    ("Kirsten", "Hi Kirsten,"),
])
async def test_first_name_fallback_to_there(
    first_name: str | None, expected_greeting: str,
) -> None:
    storage = FakeStorage(variants_by_type=mk_variants_by_type(
        icebreaker_content="Hi {{first_name}}, short.",
    ))
    composer = mk_composer(storage)
    contact = mk_contact(first_name=first_name)

    result = await composer.compose("client-1", contact)

    assert isinstance(result, ComposedDraft)
    assert expected_greeting in result.body


# --------------------------------------------------------------------------- #
# 13. Missing research fill → placeholder empty + fills_missing populated       #
# --------------------------------------------------------------------------- #

async def test_missing_research_fill_flagged_in_fills_missing() -> None:
    # No citable_details / buying_signals / trigger_events → all 3 research
    # placeholders unfilled. cta_content passes through so it's not missing.
    storage = FakeStorage(variants_by_type=mk_variants_by_type())
    composer = mk_composer(storage)

    result = await composer.compose("client-1", mk_contact())

    assert isinstance(result, ComposedDraft)
    # Template had {{trigger_hook}}, {{icebreaker_content}}, {{pain_evidence}}
    assert "trigger_hook" in result.fills_missing
    assert "icebreaker_content" in result.fills_missing
    assert "pain_evidence" in result.fills_missing
    # cta_content is filled from the component; not missing.
    assert "cta_content" not in result.fills_missing
    # Each name appears once (dedup working).
    assert len(result.fills_missing) == len(set(result.fills_missing))
    # Subject still renders, just with the missing placeholder as empty string.
    assert result.subject == "Subject: "


# --------------------------------------------------------------------------- #
# 14. dry_run                                                                   #
# --------------------------------------------------------------------------- #

async def test_dry_run_does_not_persist_but_still_logs() -> None:
    storage = FakeStorage(variants_by_type=mk_variants_by_type())
    composer = mk_composer(storage)

    result = await composer.compose("client-1", mk_contact(), dry_run=True)

    assert isinstance(result, ComposedDraft)
    assert result.persisted_draft_id is None
    assert storage.persisted_drafts == []
    entry = _render_entry(storage.logger.entries)
    assert entry["context"]["dry_run"] is True
    assert entry["context"]["persisted_draft_id"] is None


async def test_dry_run_forwarded_to_research_selector() -> None:
    # Regression guard: composer must forward dry_run=True into
    # ResearchSelector.select_fills, which surfaces it in the
    # research_contact decision_log entry context. A silent flip to
    # dry_run=False in composer.py would otherwise go undetected.
    research_logger = FakeLogger()
    storage = FakeStorage(variants_by_type=mk_variants_by_type())
    composer = mk_composer(storage, research_logger=research_logger)

    await composer.compose("client-1", mk_contact(), dry_run=True)

    research_entries = [
        e for e in research_logger.entries
        if e["decision_type"] == "research_contact"
    ]
    assert len(research_entries) == 1
    assert research_entries[0]["context"]["dry_run"] is True


# --------------------------------------------------------------------------- #
# 15. Persist failure does not abort                                            #
# --------------------------------------------------------------------------- #

async def test_persist_failure_still_returns_draft_and_logs() -> None:
    storage = FakeStorage(
        variants_by_type=mk_variants_by_type(),
        persist_raises=RuntimeError("db down"),
    )
    composer = mk_composer(storage)

    result = await composer.compose("client-1", mk_contact())

    assert isinstance(result, ComposedDraft)
    assert result.persisted_draft_id is None
    # decision_log still fired with persisted_draft_id=None.
    entry = _render_entry(storage.logger.entries)
    assert entry["context"]["persisted_draft_id"] is None
    assert entry["context"]["dry_run"] is False


# --------------------------------------------------------------------------- #
# 16. Skip path also logs                                                       #
# --------------------------------------------------------------------------- #

async def test_skip_path_emits_decision_log() -> None:
    variants = mk_variants_by_type()
    variants["signature"] = []
    storage = FakeStorage(variants_by_type=variants)
    composer = mk_composer(storage)

    result = await composer.compose("client-1", mk_contact())

    assert isinstance(result, ComposerSkip)
    entry = _render_entry(storage.logger.entries)
    assert entry["decision"].startswith("render_draft:skip:contact-1:")
    assert entry["context"]["skip_reason"] == "no_variants_for:signature"


# --------------------------------------------------------------------------- #
# 17. component_selections uses variant_key, not UUID                           #
# --------------------------------------------------------------------------- #

async def test_component_selections_uses_variant_key_not_uuid() -> None:
    variants = mk_variants_by_type()
    # Rename each variant to prove we're serialising the key, not a UUID.
    variants["subject_line"] = [mk_variant(
        component_type="subject_line", variant_key="human_readable_subject_v3",
        variant_content="subject",
    )]
    variants["cta"] = [mk_variant(
        component_type="cta", variant_key="human_readable_cta_v3",
        variant_content="cta",
    )]
    storage = FakeStorage(variants_by_type=variants)
    composer = mk_composer(storage)

    result = await composer.compose("client-1", mk_contact())

    assert isinstance(result, ComposedDraft)
    assert result.component_selections["subject_line"] == "human_readable_subject_v3"
    assert result.component_selections["cta"] == "human_readable_cta_v3"
    entry = _render_entry(storage.logger.entries)
    assert entry["context"]["component_tuple"]["subject_line"] == "human_readable_subject_v3"
    # Verify the persisted draft row also carries the key.
    persisted = storage.persisted_drafts[0]
    assert persisted["component_selections"]["cta"] == "human_readable_cta_v3"


# --------------------------------------------------------------------------- #
# 18. Body assembly order                                                       #
# --------------------------------------------------------------------------- #

async def test_body_assembly_order_and_separator() -> None:
    storage = FakeStorage(variants_by_type=mk_variants_by_type(
        icebreaker_content="ICE",
        pain_hook_content="PAIN",
        offer_frame_content="OFFER",
        cta_content="CTA",
        signature_content="SIG",
    ))
    composer = mk_composer(storage)

    result = await composer.compose("client-1", mk_contact())

    assert isinstance(result, ComposedDraft)
    assert result.body == "ICE\n\nPAIN\n\nOFFER\n\nCTA\n\nSIG"


# --------------------------------------------------------------------------- #
# 19. Exploding logger doesn't crash composer                                   #
# --------------------------------------------------------------------------- #

async def test_exploding_logger_does_not_crash_composer() -> None:
    storage = FakeStorage(
        variants_by_type=mk_variants_by_type(),
        logger=ExplodingLogger(),
    )
    composer = mk_composer(storage)

    result = await composer.compose("client-1", mk_contact())

    assert isinstance(result, ComposedDraft)
    assert result.persisted_draft_id == "draft-1"


async def test_exploding_logger_on_skip_path_does_not_crash() -> None:
    variants = mk_variants_by_type()
    variants["cta"] = []
    storage = FakeStorage(variants_by_type=variants, logger=ExplodingLogger())
    composer = mk_composer(storage)

    result = await composer.compose("client-1", mk_contact())

    assert isinstance(result, ComposerSkip)


# --------------------------------------------------------------------------- #
# Extra: decision_log context carries channel, sequence_round, signals          #
# --------------------------------------------------------------------------- #

async def test_decision_log_context_has_channel_round_signals() -> None:
    contact = mk_contact(
        sequence_round=3,
        citable_details=[{"type": "case_study", "detail": "fact", "source": "x"}],
    )
    storage = FakeStorage(variants_by_type=mk_variants_by_type())
    composer = mk_composer(storage)

    await composer.compose("client-1", contact)

    entry = _render_entry(storage.logger.entries)
    ctx = entry["context"]
    assert ctx["channel"] == "email"
    assert ctx["sequence_round"] == 3
    assert ctx["niche"] == "cro_growth_ugc_agency"
    assert ctx["offer_label"] == "pipeline_audit"
    assert isinstance(ctx["signals_referenced"], list)


# --------------------------------------------------------------------------- #
# Extra: single-variant pool skips bandit                                       #
# --------------------------------------------------------------------------- #

async def test_single_variant_pool_skips_bandit() -> None:
    # With exactly one variant per type, RNG should not be consulted — we
    # prove this by passing an RNG that would explode on .random() / .choice().
    class ExplodingRNG:
        def random(self) -> float:  # pragma: no cover — must not be called
            raise AssertionError("bandit invoked with single variant")
        def choice(self, seq: Any) -> Any:  # pragma: no cover
            raise AssertionError("bandit invoked with single variant")

    storage = FakeStorage(variants_by_type=mk_variants_by_type())
    composer = Composer(
        storage,
        ResearchSelector(),
        epsilon=0.5,
        rng=ExplodingRNG(),  # type: ignore[arg-type]
    )

    result = await composer.compose("client-1", mk_contact())
    assert isinstance(result, ComposedDraft)
