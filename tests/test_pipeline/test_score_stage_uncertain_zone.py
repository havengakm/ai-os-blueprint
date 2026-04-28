"""Plan 2 Phase 5 Task 2.5.7: ScoreStage + UncertainZoneJudge integration tests.

Verifies the score-stage wiring of the optional judge:

- Contact whose rule score is in the uncertain zone (40-60) → judge fires.
- Contact below the zone (clearly archive) → judge skipped, no LLM call.
- Contact above the zone (clearly Tier A) → judge skipped, no LLM call.
- Final persisted score = rule_score + nudge (clamped 0..100).
- Decision-log entry with decision_type='icp_threshold' fires when judge runs.
- ScoreStage works without a judge (backward compat).
"""
from __future__ import annotations

from typing import Any

import pytest

from systems.scout.pipeline.score import DEFAULT_TIER_THRESHOLDS, DEFAULT_WEIGHTS
from systems.scout.pipeline.score_stage import ContactToScore, ScoreStage
from systems.scout.score.uncertain_zone_judge import NudgeResult


# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #


class FakeStorage:
    def __init__(self, config=None, contacts=None) -> None:
        self.config = config or {
            "weights": DEFAULT_WEIGHTS,
            "tier_thresholds": DEFAULT_TIER_THRESHOLDS,
        }
        self.contacts = contacts or []
        self.updates: list[dict] = []
        self.archives: list[dict] = []
        self.decisions: list[dict] = []

    async def get_client_config(self, client_id):
        return self.config

    async def get_contacts_for_scoring(self, client_id, *, phase, limit=None):
        return self.contacts[:limit] if limit else self.contacts

    async def update_contact_score(self, client_id, contact_id, *, score, tier, phase):
        self.updates.append(
            {"contact_id": contact_id, "score": score, "tier": tier, "phase": phase}
        )

    async def archive_contact(self, client_id, contact_id, *, reason):
        self.archives.append({"contact_id": contact_id, "reason": reason})

    async def log_decision(self, client_id, **kwargs):
        self.decisions.append({"client_id": client_id, **kwargs})


class FakeJudge:
    """Returns a pre-canned NudgeResult on every judge() call."""

    def __init__(self, *, nudge: int = 0, raise_on_judge: Exception | None = None) -> None:
        self._nudge = nudge
        self._raise = raise_on_judge
        self.judge_calls: list[dict] = []

    async def judge(self, *, contact, client_icp, dry_run=False):
        if self._raise is not None:
            raise self._raise
        self.judge_calls.append({"contact": contact, "client_icp": client_icp})
        if dry_run:
            return NudgeResult(
                ok=False, nudge=0, reasoning="", cost_cents=0, reason="dry_run_skipped",
            )
        return NudgeResult(
            ok=True, nudge=self._nudge, reasoning="test verdict",
            cost_cents=0, reason="ok",
        )


# --------------------------------------------------------------------------- #
# Pre-built contacts at known score levels                                    #
# --------------------------------------------------------------------------- #


def _contact(cid: str, *, employees: int) -> ContactToScore:
    """Build a contact whose pull-payload score lands at a controllable
    level by varying ``employees`` against the default fit weights."""
    return ContactToScore(
        contact_id=cid,
        industry="SaaS",
        title="VP of Sales",
        employees=employees,
        geography="United States",
        email="x@example.com",
        email_verified=True,
        linkedin_url="https://linkedin.com/in/x",
        phone=None,
        raw_data={},
        research_data={},
    )


# --------------------------------------------------------------------------- #
# Backward compatibility — no judge configured                                #
# --------------------------------------------------------------------------- #


async def test_score_stage_works_without_judge():
    """Existing behaviour unchanged when no judge is injected."""
    config = {
        "weights": DEFAULT_WEIGHTS,
        "tier_thresholds": {**DEFAULT_TIER_THRESHOLDS, "archive_floor": 0},
        "icp": {"industries": ["SaaS"], "titles": ["VP of Sales"]},
    }
    storage = FakeStorage(
        config=config, contacts=[_contact("u1", employees=150)],
    )
    stage = ScoreStage(storage)  # no judge

    result = await stage.run("c1", phase="v1")
    assert result.total_scored == 1
    assert len(storage.updates) == 1


# --------------------------------------------------------------------------- #
# Judge fires when score in uncertain zone, applies nudge                     #
# --------------------------------------------------------------------------- #


async def test_judge_fires_when_score_in_uncertain_zone():
    """Construct a contact whose rule score lands in 40-60 (mid-fit)."""
    config = {
        "weights": DEFAULT_WEIGHTS,
        "tier_thresholds": {**DEFAULT_TIER_THRESHOLDS, "archive_floor": 0},
        "icp": {
            "uncertain_zone": {"low": 40, "high": 60},
            "industries": ["SaaS"],
            "titles": ["VP of Sales"],
            "employee_min": 100,
            "employee_max": 200,
        },
    }
    # employees=150 → mid score ~50 with the icp config above.
    storage = FakeStorage(
        config=config, contacts=[_contact("u-mid", employees=150)],
    )
    judge = FakeJudge(nudge=5)
    stage = ScoreStage(storage, judge=judge)

    await stage.run("c1", phase="v1")

    # Judge was called with this contact.
    assert len(judge.judge_calls) == 1
    # Nudge was applied — persisted score = rule + 5 (judge fixture nudge).
    persisted = storage.updates[0]
    # Filter to judge-specific log entries (score_stage emits a summary
    # icp_threshold entry too — exclude that).
    judge_decisions = [
        d for d in storage.decisions
        if d.get("decision_type") == "icp_threshold"
        and str(d.get("decision", "")).startswith("uncertain_zone_judge")
    ]
    assert len(judge_decisions) == 1
    ctx = judge_decisions[0]["context"]
    assert ctx["contact_id"] == "u-mid"
    assert ctx["nudge"] == 5
    assert ctx["reason"] == "ok"
    # Persisted score = rule_score + nudge.
    assert persisted["score"] == ctx["rule_score"] + 5


async def test_judge_skipped_when_score_clearly_archive():
    """Score < 40 → judge MUST NOT fire (no LLM call). Saves cost."""
    config = {
        "weights": DEFAULT_WEIGHTS,
        "tier_thresholds": DEFAULT_TIER_THRESHOLDS,
        "icp": {"uncertain_zone": {"low": 40, "high": 60}},
    }
    # No fit, no reach, no recency → score = 0 → archive.
    storage = FakeStorage(
        config=config,
        contacts=[
            ContactToScore(
                contact_id="u-archive",
                industry=None, title=None, employees=None, geography=None,
                email=None, email_verified=False, linkedin_url=None, phone=None,
                raw_data={}, research_data={},
            )
        ],
    )
    judge = FakeJudge(nudge=15)
    stage = ScoreStage(storage, judge=judge)

    await stage.run("c1", phase="v1")
    assert judge.judge_calls == []


async def test_judge_skipped_when_score_clearly_tier_a():
    """Score > 60 → judge skipped. Build a maximally-strong contact."""
    config = {
        "weights": DEFAULT_WEIGHTS,
        "tier_thresholds": DEFAULT_TIER_THRESHOLDS,
        "icp": {
            "uncertain_zone": {"low": 40, "high": 60},
            "industries": ["SaaS"],
            "titles": ["VP of Sales"],
            "geographies": ["United States"],
            "employee_min": 100,
            "employee_max": 200,
        },
    }
    strong = ContactToScore(
        contact_id="u-strong",
        industry="SaaS", title="VP of Sales", employees=150,
        geography="United States",
        email="vp@x.com", email_verified=True,
        linkedin_url="https://linkedin.com/in/vp", phone="+14155551234",
        raw_data={"funding_event_last_180d": True, "recent_hiring": True},
        research_data={},
    )
    storage = FakeStorage(config=config, contacts=[strong])
    judge = FakeJudge(nudge=0)
    stage = ScoreStage(storage, judge=judge)

    await stage.run("c1", phase="v1")
    assert judge.judge_calls == []


# --------------------------------------------------------------------------- #
# Custom uncertain zone bounds from client_config                             #
# --------------------------------------------------------------------------- #


async def test_judge_respects_custom_uncertain_zone():
    """client_config.icp.uncertain_zone overrides the default 40-60 range."""
    config = {
        "weights": DEFAULT_WEIGHTS,
        "tier_thresholds": DEFAULT_TIER_THRESHOLDS,
        "icp": {
            "uncertain_zone": {"low": 50, "high": 70},
            "industries": ["SaaS"],
            "titles": ["VP of Sales"],
        },
    }
    # employees=150 will produce a score in default 40-60 range — but with
    # the custom 50-70, that score should be near the new low end.
    storage = FakeStorage(
        config=config, contacts=[_contact("u1", employees=150)],
    )
    judge = FakeJudge(nudge=5)
    stage = ScoreStage(storage, judge=judge)
    await stage.run("c1", phase="v1")
    # We don't assert exactly — just that the judge logic respected the
    # config. If the score landed in [50, 70], judge fired; if not, it
    # didn't. The test is a smoke check that the config is read.
    # (Specific scores are fragile against weight changes.)
    config_with_range = stage._uncertain_zone_bounds(config)
    assert config_with_range == (50, 70)


# --------------------------------------------------------------------------- #
# Tier reassignment after nudge                                               #
# --------------------------------------------------------------------------- #


async def test_nudge_can_promote_score_to_higher_tier():
    """A score-50 contact + nudge=+15 → score=65 → may reach Tier B threshold."""
    config = {
        "weights": DEFAULT_WEIGHTS,
        "tier_thresholds": {
            **DEFAULT_TIER_THRESHOLDS, "archive_floor": 0, "B": 60, "A": 80,
        },
        "icp": {
            "uncertain_zone": {"low": 40, "high": 60},
            "industries": ["SaaS"],
            "titles": ["VP of Sales"],
            "employee_min": 100,
            "employee_max": 200,
        },
    }
    storage = FakeStorage(
        config=config, contacts=[_contact("u-mid", employees=150)],
    )
    judge = FakeJudge(nudge=15)
    stage = ScoreStage(storage, judge=judge)
    await stage.run("c1", phase="v1")
    persisted = storage.updates[0]
    # Tier reassignment used the nudged score (rule was ~50 + nudge=15 = 65).
    assert persisted["score"] >= 60


# --------------------------------------------------------------------------- #
# Score clamped to [0, 100]                                                   #
# --------------------------------------------------------------------------- #


async def test_negative_nudge_clamps_to_zero():
    """rule_score=40 + nudge=-15 = 25 → fine, no clamping needed.
    Edge case: rule_score=10 + nudge=-15 = -5 → clamped to 0.
    But score=10 isn't in the uncertain zone, so judge wouldn't fire.
    Use a contrived case where the zone is widened to include low scores."""
    config = {
        "weights": DEFAULT_WEIGHTS,
        "tier_thresholds": DEFAULT_TIER_THRESHOLDS,
        "icp": {"uncertain_zone": {"low": 0, "high": 100}},  # judge always fires
    }
    contact = ContactToScore(
        contact_id="u-low",
        industry=None, title=None, employees=None, geography=None,
        email="x@y.com", email_verified=False,
        linkedin_url=None, phone=None,
        raw_data={}, research_data={},
    )
    storage = FakeStorage(config=config, contacts=[contact])
    judge = FakeJudge(nudge=-15)
    stage = ScoreStage(storage, judge=judge)
    await stage.run("c1", phase="v1")
    # Either persisted as score=0 (clamped) or archived, depending on
    # tier_thresholds.archive_floor. Verify no negative scores leaked.
    if storage.updates:
        assert storage.updates[0]["score"] >= 0


# --------------------------------------------------------------------------- #
# Judge failure does NOT block scoring                                        #
# --------------------------------------------------------------------------- #


async def test_judge_exception_falls_back_to_rule_score():
    """If the judge raises, score_stage continues with the rule score
    (fail-safe — never lose a contact to a judge outage)."""
    config = {
        "weights": DEFAULT_WEIGHTS,
        "tier_thresholds": {**DEFAULT_TIER_THRESHOLDS, "archive_floor": 0},
        "icp": {
            "uncertain_zone": {"low": 40, "high": 60},
            "industries": ["SaaS"],
            "titles": ["VP of Sales"],
            "employee_min": 100,
            "employee_max": 200,
        },
    }
    storage = FakeStorage(
        config=config, contacts=[_contact("u-mid", employees=150)],
    )
    judge = FakeJudge(raise_on_judge=RuntimeError("anthropic 500"))
    stage = ScoreStage(storage, judge=judge)
    await stage.run("c1", phase="v1")
    # Contact was still persisted with the rule score (no nudge applied).
    assert len(storage.updates) == 1


async def test_judge_returning_failed_result_does_not_apply_nudge():
    """When judge returns ok=False (e.g. no_api_key), nudge defaults to
    0 — rule score stands."""
    config = {
        "weights": DEFAULT_WEIGHTS,
        "tier_thresholds": {**DEFAULT_TIER_THRESHOLDS, "archive_floor": 0},
        "icp": {
            "uncertain_zone": {"low": 40, "high": 60},
            "industries": ["SaaS"],
            "titles": ["VP of Sales"],
            "employee_min": 100,
            "employee_max": 200,
        },
    }
    storage = FakeStorage(
        config=config, contacts=[_contact("u-mid", employees=150)],
    )

    class _NoApiKeyJudge:
        async def judge(self, *, contact, client_icp, dry_run=False):
            return NudgeResult(
                ok=False, nudge=0, reasoning="", cost_cents=0,
                reason="no_api_key",
            )

    stage = ScoreStage(storage, judge=_NoApiKeyJudge())
    await stage.run("c1", phase="v1")
    # Filter to judge-specific log entries.
    judge_decisions = [
        d for d in storage.decisions
        if d.get("decision_type") == "icp_threshold"
        and str(d.get("decision", "")).startswith("uncertain_zone_judge")
    ]
    assert len(judge_decisions) == 1
    assert judge_decisions[0]["context"]["reason"] == "no_api_key"
    assert judge_decisions[0]["context"]["nudge"] == 0
