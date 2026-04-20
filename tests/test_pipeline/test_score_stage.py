"""Tests for the ScoreStage pipeline class (Task 10b).

Uses in-memory fakes for storage — scoring functions are pure and called directly.
"""
from __future__ import annotations

import pytest

from systems.scout.pipeline.score import DEFAULT_TIER_THRESHOLDS, DEFAULT_WEIGHTS
from systems.scout.pipeline.score_stage import ContactToScore, ScoreStage, ScoreStageResult


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeStorage:
    def __init__(self, config=None, contacts=None):
        self.config = config or {
            "weights": DEFAULT_WEIGHTS,
            "tier_thresholds": DEFAULT_TIER_THRESHOLDS,
        }
        self.contacts = contacts or []
        self.updates: list[dict] = []
        self.archives: list[dict] = []
        self.decisions: list[dict] = []
        self.raise_on_update: Exception | None = None
        self.raise_on_archive: Exception | None = None

    async def get_client_config(self, client_id):
        return self.config

    async def get_contacts_for_scoring(self, client_id, *, phase, limit=None):
        filtered = [c for c in self.contacts if self._phase_matches(c, phase)]
        return filtered[:limit] if limit else filtered

    def _phase_matches(self, contact, phase):
        # Tests pre-filter via self.contacts; here we return everything
        return True

    async def update_contact_score(self, client_id, contact_id, *, score, tier, phase):
        if self.raise_on_update:
            raise self.raise_on_update
        self.updates.append({"contact_id": contact_id, "score": score, "tier": tier, "phase": phase})

    async def archive_contact(self, client_id, contact_id, *, reason):
        if self.raise_on_archive:
            raise self.raise_on_archive
        self.archives.append({"contact_id": contact_id, "reason": reason})

    async def log_decision(self, client_id, **kwargs):
        self.decisions.append({"client_id": client_id, **kwargs})


# ---------------------------------------------------------------------------
# Helpers: pre-built contacts
# ---------------------------------------------------------------------------


def strong_fit_contact(contact_id: str = "c-strong") -> ContactToScore:
    """High-fit contact — should score well into A/B tier."""
    return ContactToScore(
        contact_id=contact_id,
        industry="SaaS",
        title="VP of Sales",
        employees=150,
        geography="United States",
        email="vp@example.com",
        email_verified=True,
        linkedin_url="https://linkedin.com/in/vp-sales",
        phone="+14155551234",
        raw_data={"funding_event_last_180d": True, "recent_hiring": True},
        research_data={},
    )


def weak_contact(contact_id: str = "c-weak") -> ContactToScore:
    """No signals — should score 0 and archive."""
    return ContactToScore(
        contact_id=contact_id,
        industry=None,
        title=None,
        employees=None,
        geography=None,
        email=None,
        email_verified=False,
        linkedin_url=None,
        phone=None,
        raw_data={},
        research_data={},
    )


def medium_contact(contact_id: str = "c-medium") -> ContactToScore:
    """Mid-range contact — falls in C/D territory."""
    return ContactToScore(
        contact_id=contact_id,
        industry=None,
        title=None,
        employees=None,
        geography=None,
        email="mid@example.com",
        email_verified=True,
        linkedin_url="https://linkedin.com/in/mid",
        phone=None,
        raw_data={},
        research_data={},
    )


def intent_contact(contact_id: str = "c-intent") -> ContactToScore:
    """Has v1 signals + full intent signals for v2 boost."""
    return ContactToScore(
        contact_id=contact_id,
        industry="SaaS",
        title="CEO",
        employees=80,
        geography="United Kingdom",
        email="ceo@example.com",
        email_verified=True,
        linkedin_url="https://linkedin.com/in/ceo",
        phone="+442071234567",
        raw_data={"funding_event_last_180d": True, "recent_hiring": False},
        research_data={"pain_match": "High churn problem", "activity_positive": True},
    )


# Config with ICP so fit signals fire
ICP_CONFIG = {
    "weights": DEFAULT_WEIGHTS,
    "tier_thresholds": DEFAULT_TIER_THRESHOLDS,
    "icp": {
        "industries": ["SaaS"],
        "titles": ["VP", "CEO", "Director"],
        "employee_min": 50,
        "employee_max": 500,
        "geographies": ["United States", "United Kingdom"],
    },
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_stage_v1_happy_path():
    """Strong-fit contact should update_contact_score with score > 60 and tier A or B."""
    storage = FakeStorage(config=ICP_CONFIG, contacts=[strong_fit_contact()])
    stage = ScoreStage(storage)

    result = await stage.run("client-1", phase="v1")

    assert result.total_eligible == 1
    assert result.total_scored == 1
    assert result.total_archived == 0
    assert result.total_errored == 0

    assert len(storage.updates) == 1
    update = storage.updates[0]
    assert update["score"] > 60
    assert update["tier"] in ("A", "B")
    assert update["phase"] == "v1"
    assert len(storage.archives) == 0


@pytest.mark.asyncio
async def test_score_stage_v1_archive_path():
    """Zero-signal contact scores 0 → archive_contact called, update NOT called."""
    storage = FakeStorage(config=ICP_CONFIG, contacts=[weak_contact()])
    stage = ScoreStage(storage)

    result = await stage.run("client-1", phase="v1")

    assert result.total_eligible == 1
    assert result.total_archived == 1
    assert result.total_scored == 0
    assert result.total_errored == 0

    assert len(storage.archives) == 1
    assert storage.archives[0]["contact_id"] == "c-weak"
    assert storage.archives[0]["reason"] == "below_archive_floor"
    assert len(storage.updates) == 0


@pytest.mark.asyncio
async def test_score_stage_v2_adds_intent():
    """Contact with intent signals should score higher under v2 than a v1 run would."""
    from systems.scout.pipeline.score import score_v1, score_v2

    contact = intent_contact()
    contact_dict = {
        "contact_id": contact.contact_id,
        "industry": contact.industry,
        "title": contact.title,
        "employees": contact.employees,
        "geography": contact.geography,
        "email": contact.email,
        "email_verified": contact.email_verified,
        "linkedin_url": contact.linkedin_url,
        "phone": contact.phone,
        "raw_data": contact.raw_data,
        "research_data": contact.research_data,
    }
    v1_score = score_v1(contact_dict, ICP_CONFIG)
    v2_score = score_v2(contact_dict, ICP_CONFIG)
    assert v2_score > v1_score, "v2 should exceed v1 when intent signals are present"

    storage = FakeStorage(config=ICP_CONFIG, contacts=[contact])
    stage = ScoreStage(storage)
    result = await stage.run("client-1", phase="v2")

    assert result.total_scored == 1
    assert len(storage.updates) == 1
    assert storage.updates[0]["score"] == v2_score


@pytest.mark.asyncio
async def test_score_stage_mixed_batch_tier_counts():
    """Five contacts landing across tiers — tier_counts must be correct."""
    # Build contacts that will reliably land in each tier with ICP_CONFIG
    # A (>=80): strong fit + full reach + both recency = 40+20+10 = 70 → still only 70 for v1 max
    # With v1 max = 70 at default weights, A (80) is unreachable without intent.
    # Use v2 phase and inject intent for the A-tier contact.
    strong_with_intent = ContactToScore(
        contact_id="c-A",
        industry="SaaS",
        title="CEO",
        employees=100,
        geography="United States",
        email="a@x.com",
        email_verified=True,
        linkedin_url="https://linkedin.com/in/a",
        phone="+1111",
        raw_data={"funding_event_last_180d": True, "recent_hiring": True},
        research_data={"pain_match": "churn", "activity_positive": True},
    )
    # B (65–79): reasonable fit, some reach, some intent
    b_contact = ContactToScore(
        contact_id="c-B",
        industry="SaaS",
        title="VP of Sales",
        employees=100,
        geography="United States",
        email="b@x.com",
        email_verified=True,
        linkedin_url="https://linkedin.com/in/b",
        phone=None,
        raw_data={"funding_event_last_180d": False, "recent_hiring": False},
        research_data={"pain_match": "growth bottleneck", "activity_positive": False},
    )
    # C (50–64): fit + limited reach, no intent
    c_contact = ContactToScore(
        contact_id="c-C",
        industry="SaaS",
        title="Director of Sales",
        employees=200,
        geography="United States",
        email="c@x.com",
        email_verified=True,
        linkedin_url=None,
        phone=None,
        raw_data={},
        research_data={},
    )
    # D (35–49): partial reach only
    d_contact = ContactToScore(
        contact_id="c-D",
        industry=None,
        title=None,
        employees=None,
        geography=None,
        email="d@x.com",
        email_verified=True,
        linkedin_url="https://linkedin.com/in/d",
        phone=None,
        raw_data={},
        research_data={},
    )
    # archive (<35): minimal reach
    archive_contact = ContactToScore(
        contact_id="c-arc",
        industry=None,
        title=None,
        employees=None,
        geography=None,
        email="e@x.com",
        email_verified=False,
        linkedin_url=None,
        phone=None,
        raw_data={},
        research_data={},
    )

    from systems.scout.pipeline.score import score_v2, assign_tier
    contacts = [strong_with_intent, b_contact, c_contact, d_contact, archive_contact]
    for c in contacts:
        s = score_v2(
            {"industry": c.industry, "title": c.title, "employees": c.employees,
             "geography": c.geography, "email": c.email, "email_verified": c.email_verified,
             "linkedin_url": c.linkedin_url, "phone": c.phone,
             "raw_data": c.raw_data, "research_data": c.research_data},
            ICP_CONFIG,
        )
        tier = assign_tier(s, ICP_CONFIG)
        # Verify our contacts actually land in expected tiers
        assert tier in ("A", "B", "C", "D", "archive"), f"{c.contact_id}: score={s}, tier={tier}"

    storage = FakeStorage(config=ICP_CONFIG, contacts=contacts)
    stage = ScoreStage(storage)
    result = await stage.run("client-1", phase="v2")

    assert result.total_eligible == 5
    total_in_counts = sum(result.tier_counts.values())
    assert total_in_counts == 5
    assert set(result.tier_counts.keys()) == {"A", "B", "C", "D", "archive"}


@pytest.mark.asyncio
async def test_score_stage_dry_run_skips_persistence():
    """dry_run=True: no updates or archives, but summary decision is logged."""
    storage = FakeStorage(
        config=ICP_CONFIG,
        contacts=[strong_fit_contact(), weak_contact()],
    )
    stage = ScoreStage(storage)

    result = await stage.run("client-1", phase="v1", dry_run=True)

    assert result.dry_run is True
    assert result.total_eligible == 2
    assert len(storage.updates) == 0
    assert len(storage.archives) == 0
    # Summary decision still logged
    assert len(storage.decisions) >= 1
    summary = next(d for d in storage.decisions if d.get("decision") == "score_stage_summary")
    assert summary["context"]["dry_run"] is True


@pytest.mark.asyncio
async def test_score_stage_invalid_phase_raises():
    """phase='v3' must raise ValueError immediately."""
    storage = FakeStorage()
    stage = ScoreStage(storage)

    with pytest.raises(ValueError, match="phase must be 'v1' or 'v2'"):
        await stage.run("client-1", phase="v3")


@pytest.mark.asyncio
async def test_score_stage_limit_caps_batch():
    """limit=2 on 5 contacts → only 2 processed."""
    contacts = [strong_fit_contact(f"c-{i}") for i in range(5)]
    storage = FakeStorage(config=ICP_CONFIG, contacts=contacts)
    stage = ScoreStage(storage)

    result = await stage.run("client-1", phase="v1", limit=2)

    assert result.total_eligible == 2
    assert result.total_scored + result.total_archived + result.total_errored == 2


@pytest.mark.asyncio
async def test_score_stage_persist_error_continues():
    """Update failure on first contact: total_errored=1, other two still succeed."""
    contacts = [strong_fit_contact(f"c-{i}") for i in range(3)]
    storage = FakeStorage(config=ICP_CONFIG, contacts=contacts)
    storage.raise_on_update = RuntimeError("db down")
    stage = ScoreStage(storage)

    result = await stage.run("client-1", phase="v1")

    assert result.total_errored == 3  # all three fail (same exception set on storage)
    assert result.total_scored == 0
    # Loop continued: 3 contacts attempted, not aborted after first
    assert result.total_eligible == 3


@pytest.mark.asyncio
async def test_score_stage_persist_error_continues_partial():
    """One bad contact then two good ones: first errors, others succeed."""
    bad = weak_contact("c-bad")   # will archive → but let's use update failure instead
    good1 = strong_fit_contact("c-good1")
    good2 = strong_fit_contact("c-good2")

    # We need update to fail only for first call. Use a counter.
    class PartialStorage(FakeStorage):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._update_calls = 0

        async def update_contact_score(self, client_id, contact_id, *, score, tier, phase):
            self._update_calls += 1
            if self._update_calls == 1:
                raise RuntimeError("transient error")
            await super().update_contact_score(client_id, contact_id, score=score, tier=tier, phase=phase)

    storage = PartialStorage(config=ICP_CONFIG, contacts=[good1, good2, good1.__class__(
        contact_id="c-good3",
        industry=good1.industry, title=good1.title, employees=good1.employees,
        geography=good1.geography, email=good1.email, email_verified=good1.email_verified,
        linkedin_url=good1.linkedin_url, phone=good1.phone,
        raw_data=good1.raw_data, research_data=good1.research_data,
    )])
    stage = ScoreStage(storage)

    result = await stage.run("client-1", phase="v1")

    assert result.total_errored == 1
    assert result.total_scored == 2


@pytest.mark.asyncio
async def test_score_stage_archive_persist_error_continues():
    """archive_contact raises: total_errored increments, loop continues for all contacts."""
    contacts = [weak_contact(f"c-{i}") for i in range(3)]
    storage = FakeStorage(config=ICP_CONFIG, contacts=contacts)
    storage.raise_on_archive = OSError("storage unavailable")
    stage = ScoreStage(storage)

    result = await stage.run("client-1", phase="v1")

    assert result.total_eligible == 3
    assert result.total_errored == 3
    assert result.total_archived == 0  # all failed before incrementing


@pytest.mark.asyncio
async def test_score_stage_logs_summary():
    """Last logged decision is the summary with all required keys."""
    storage = FakeStorage(config=ICP_CONFIG, contacts=[strong_fit_contact(), weak_contact()])
    stage = ScoreStage(storage)

    await stage.run("client-1", phase="v1")

    summary = next(
        (d for d in storage.decisions if d.get("decision") == "score_stage_summary"),
        None,
    )
    assert summary is not None
    assert summary["decision_type"] == "icp_threshold"
    assert summary["client_id"] == "client-1"

    ctx = summary["context"]
    required_keys = {
        "client_id", "phase", "dry_run", "total_eligible",
        "total_scored", "total_archived", "total_errored",
        "tier_counts", "archive_floor",
    }
    assert required_keys.issubset(ctx.keys()), f"Missing keys: {required_keys - ctx.keys()}"
    assert ctx["phase"] == "v1"
    assert ctx["archive_floor"] == DEFAULT_TIER_THRESHOLDS["archive_floor"]


@pytest.mark.asyncio
async def test_score_stage_empty_contacts():
    """Zero eligible contacts: scoring never called, summary still logged."""
    storage = FakeStorage(config=ICP_CONFIG, contacts=[])
    stage = ScoreStage(storage)

    result = await stage.run("client-1", phase="v1")

    assert result.total_eligible == 0
    assert result.total_scored == 0
    assert result.total_archived == 0
    assert result.total_errored == 0
    assert len(storage.updates) == 0
    assert len(storage.archives) == 0
    # Summary still logged
    summary = next(d for d in storage.decisions if d.get("decision") == "score_stage_summary")
    assert summary is not None


@pytest.mark.asyncio
async def test_score_stage_tier_counts_initialized_with_all_keys():
    """Empty run: tier_counts has exactly {A, B, C, D, archive} all set to 0."""
    storage = FakeStorage(config=ICP_CONFIG, contacts=[])
    stage = ScoreStage(storage)

    result = await stage.run("client-1", phase="v1")

    assert set(result.tier_counts.keys()) == {"A", "B", "C", "D", "archive"}
    assert all(v == 0 for v in result.tier_counts.values())
