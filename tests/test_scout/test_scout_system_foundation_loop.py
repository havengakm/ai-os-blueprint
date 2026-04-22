"""Tests for ``systems/scout/skill.py::ScoutSystem`` — stage-dispatcher foundation loop.

Each ``run_<stage>`` method on ScoutSystem must wrap the inner pipeline
stage with the mandatory foundation-loop calls (load_foundation →
check_autonomy → find_similar_decisions) BEFORE dispatching to the
inner orchestrator. Knowledge pulling is uniform across stages: the
``task_query`` passed to ``load_foundation`` drives the similarity
search in ``memory_store.load_full_context`` and populates
``foundation_context['relevant_knowledge']`` — no separate
``retrieve_knowledge`` call per stage. These tests assert call ordering,
args, and method-specific behaviour (compose fans out per-contact with
the existing render response shape).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from systems.scout.skill import ScoutSystem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _StubResult:
    """Minimal dataclass result stand-in for any stage."""

    client_id: str
    dry_run: bool = False


def _foundation_mocks():
    """Build AsyncMock foundation modules with realistic return shapes."""
    memory = MagicMock()
    memory.load_full_context = AsyncMock(return_value={})
    decisions = MagicMock()
    decisions.log_decision = AsyncMock(return_value="dec-id")
    patterns = MagicMock()
    patterns.find_similar = AsyncMock(return_value=[])
    autonomy = MagicMock()
    autonomy.check = AsyncMock(return_value="suggest")
    knowledge = MagicMock()
    knowledge.retrieve = AsyncMock(return_value=[])
    return memory, decisions, patterns, autonomy, knowledge


def _build_scout_with_stage_stub(stage_attr: str, stage_stub: Any) -> ScoutSystem:
    """Build a ScoutSystem where the named stage factory returns ``stage_stub``.

    ``stage_attr`` is one of: pull_stage_factory, score_stage_factory,
    screen_stage_factory, identity_stage_factory, enrich_stage_factory,
    composer_factory.
    """
    memory, decisions, patterns, autonomy, knowledge = _foundation_mocks()
    kwargs: dict[str, Any] = dict(
        memory_store=memory,
        decision_logger=decisions,
        pattern_matcher=patterns,
        autonomy_gate=autonomy,
        knowledge_store=knowledge,
    )
    kwargs[stage_attr] = lambda: stage_stub
    return ScoutSystem(**kwargs)


# ---------------------------------------------------------------------------
# Stage foundation-loop tests (pull/score/screen/identity/enrich)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_pull_invokes_foundation_loop_in_order():
    stage = MagicMock()
    stage.run = AsyncMock(return_value=_StubResult(client_id="c1"))
    scout = _build_scout_with_stage_stub("pull_stage_factory", stage)

    result = await scout.run_pull("c1", dry_run=True, limit=10)

    # Foundation loop was invoked
    scout.memory.load_full_context.assert_awaited_once()
    load_kwargs = scout.memory.load_full_context.call_args.kwargs
    assert load_kwargs["client_id"] == "c1"
    assert "pull" in load_kwargs["task_query"].lower()

    scout.autonomy.check.assert_awaited_once_with("c1", "source_selection")
    scout.patterns.find_similar.assert_awaited_once()
    # Knowledge retrieval does NOT fire for pull
    scout.knowledge.retrieve.assert_not_awaited()

    # Inner stage dispatched with the caller's args
    stage.run.assert_awaited_once_with("c1", dry_run=True)
    assert isinstance(result, _StubResult)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory_attr,method_name,decision_type,extra_run_kwargs",
    [
        ("score_stage_factory", "run_score", "score_contact", {"limit": 5, "phase": "v1"}),
        ("screen_stage_factory", "run_screen", "screen_contact", {"limit": 5}),
        ("identity_stage_factory", "run_identity", "identity_lookup", {"limit": 5}),
        ("enrich_stage_factory", "run_enrich", "enrich_contact", {"limit": 5}),
    ],
)
async def test_run_stage_invokes_foundation_loop(
    factory_attr: str,
    method_name: str,
    decision_type: str,
    extra_run_kwargs: dict[str, Any],
):
    stage = MagicMock()
    stage.run = AsyncMock(return_value=_StubResult(client_id="c1"))
    scout = _build_scout_with_stage_stub(factory_attr, stage)

    method = getattr(scout, method_name)
    await method("c1", dry_run=False, **extra_run_kwargs)

    scout.memory.load_full_context.assert_awaited_once()
    scout.autonomy.check.assert_awaited_once_with("c1", decision_type)
    scout.patterns.find_similar.assert_awaited_once()
    # Knowledge retrieval skipped for non-compose stages
    scout.knowledge.retrieve.assert_not_awaited()
    stage.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_score_passes_phase_through_to_stage():
    stage = MagicMock()
    stage.run = AsyncMock(return_value=_StubResult(client_id="c1"))
    scout = _build_scout_with_stage_stub("score_stage_factory", stage)

    await scout.run_score("c1", dry_run=False, limit=3, phase="v2")

    stage.run.assert_awaited_once_with("c1", dry_run=False, limit=3, phase="v2")


# ---------------------------------------------------------------------------
# Compose tests — knowledge retrieval + per-contact fan-out
# ---------------------------------------------------------------------------


class _StubComposer:
    """Composer stub with configurable per-call return values."""

    def __init__(self, outcomes: list[Any]):
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def compose(self, client_id, contact, *, dry_run=False):
        self.calls.append({"client_id": client_id, "contact": contact, "dry_run": dry_run})
        return self._outcomes.pop(0)


@pytest.mark.asyncio
async def test_run_compose_task_query_targets_copywriting_knowledge():
    """Compose uses a copywriting-framework-targeted ``task_query`` —
    ``memory_store.load_full_context`` runs the similarity search and
    populates ``foundation_context['relevant_knowledge']``. No separate
    ``retrieve_knowledge`` call fires (same uniform 3-prime pattern as
    every other stage)."""
    from systems.scout.outreach.composer import ComposedDraft

    draft = ComposedDraft(
        contact_id="X",
        subject="hi",
        body="body",
        component_selections={},
        sources_referenced=[],
        fills_missing=[],
        persisted_draft_id=None,
    )
    composer = _StubComposer(outcomes=[draft])
    scout = _build_scout_with_stage_stub("composer_factory", composer)

    await scout.run_compose("c1", [{"contact_id": "X"}], dry_run=True)

    scout.memory.load_full_context.assert_awaited_once()
    load_kwargs = scout.memory.load_full_context.call_args.kwargs
    assert load_kwargs["client_id"] == "c1"
    query_lower = load_kwargs["task_query"].lower()
    assert "copywriting" in query_lower or "outbound" in query_lower

    scout.autonomy.check.assert_awaited_once_with("c1", "render_draft")
    scout.patterns.find_similar.assert_awaited_once()
    # Uniform behaviour: compose no longer special-cases knowledge retrieval
    scout.knowledge.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_compose_fans_out_per_contact_and_splits_composed_skipped():
    from systems.scout.outreach.composer import ComposedDraft, ComposerSkip

    draft = ComposedDraft(
        contact_id="X",
        subject="hi",
        body="body",
        component_selections={},
        sources_referenced=[],
        fills_missing=[],
        persisted_draft_id="d1",
    )
    skip = ComposerSkip(contact_id="Y", reason="no_variants", details={})

    composer = _StubComposer(outcomes=[draft, skip])
    scout = _build_scout_with_stage_stub("composer_factory", composer)

    result = await scout.run_compose(
        "c1",
        [{"contact_id": "X"}, {"contact_id": "Y"}],
        dry_run=False,
    )

    # composer.compose called once per contact with dry_run forwarded
    assert len(composer.calls) == 2
    assert all(call["client_id"] == "c1" for call in composer.calls)
    assert all(call["dry_run"] is False for call in composer.calls)

    # Response shape matches the /api/pipeline/render contract
    assert result["client_id"] == "c1"
    assert result["dry_run"] is False
    assert result["total_eligible"] == 2
    assert result["total_composed"] == 1
    assert result["total_skipped"] == 1
    assert len(result["composed"]) == 1
    assert len(result["skipped"]) == 1


@pytest.mark.asyncio
async def test_run_compose_empty_contacts_still_invokes_foundation():
    """No contacts = still run foundation loop (observability), return empty buckets."""
    composer = _StubComposer(outcomes=[])
    scout = _build_scout_with_stage_stub("composer_factory", composer)

    result = await scout.run_compose("c1", [], dry_run=True)

    scout.memory.load_full_context.assert_awaited_once()
    # Knowledge comes via load_foundation's task_query, not a separate call
    scout.knowledge.retrieve.assert_not_awaited()
    assert result["total_eligible"] == 0
    assert result["total_composed"] == 0
    assert result["total_skipped"] == 0
    assert composer.calls == []


# ---------------------------------------------------------------------------
# from_registry factory smoke test
# ---------------------------------------------------------------------------


def test_from_registry_builds_scout_with_production_factories():
    """ScoutSystem.from_registry() wires backends → factories → stage types."""
    from systems.scout.outreach.composer import Composer
    from systems.scout.pipeline.enrich import EnrichStage
    from systems.scout.pipeline.identity import IdentityStage
    from systems.scout.pipeline.pull import PullOrchestrator
    from systems.scout.pipeline.score_stage import ScoreStage
    from systems.scout.pipeline.screen import ScreenStage

    # Build a minimal registry with MagicMock backends — just enough for the
    # factories to instantiate without touching real Supabase.
    registry = MagicMock()

    scout = ScoutSystem.from_registry(registry)

    # Foundation modules plumbed through
    assert scout.memory is registry.memory_store
    assert scout.decisions is registry.decision_logger
    assert scout.patterns is registry.pattern_matcher
    assert scout.autonomy is registry.autonomy_gate
    assert scout.knowledge is registry.knowledge_store

    # Factories produce the right types
    assert isinstance(scout._pull_factory(), PullOrchestrator)
    assert isinstance(scout._score_factory(), ScoreStage)
    assert isinstance(scout._screen_factory(), ScreenStage)
    assert isinstance(scout._identity_factory(), IdentityStage)
    assert isinstance(scout._enrich_factory(), EnrichStage)
    assert isinstance(scout._composer_factory(), Composer)


# ---------------------------------------------------------------------------
# handle() and _handle_* stubs preserved (conversational path untouched)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_still_routes_keywords():
    """The keyword-routed handle() stubs must not be broken by Task 16.5."""
    memory, decisions, patterns, autonomy, knowledge = _foundation_mocks()
    scout = ScoutSystem(
        memory_store=memory,
        decision_logger=decisions,
        pattern_matcher=patterns,
        autonomy_gate=autonomy,
        knowledge_store=knowledge,
    )
    result = await scout.handle("how's outbound pipeline going", "c1", "u1")
    assert "Pipeline status query" in result.text
