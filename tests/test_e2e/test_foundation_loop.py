"""End-to-end integration test — foundation loop fires for every Scout stage.

Task 17 Part B. Proves the 3-call foundation loop (load_full_context →
autonomy_gate.check → pattern_matcher.find_similar) fires in the correct
order for every stage the Scout daemon dispatches through ``ScoutSystem``.

This test is Scout-contract scoped: it builds a ``ScoutSystem`` directly
with mocked foundation + stage factories. It does NOT import the daemon
orchestration layer — the "continue on failure" semantics that
``run_client_cycle`` provides are covered in
``tests/test_daemon/test_client_worker.py``.

Pipeline stage order (daemon view, 7 stages):
    pull → score(v1) → screen → identity → enrich → score(v2) → compose

Autonomy decision_type per stage:
    pull        -> source_selection
    score(v1)   -> score_contact
    screen      -> screen_contact
    identity    -> identity_lookup
    enrich      -> enrich_contact
    score(v2)   -> score_contact   (same type as v1)
    compose     -> render_draft
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from aios.scout.skill import ScoutSystem


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


@dataclass
class _StubStageResult:
    """Minimal result stand-in for any batch stage."""

    client_id: str
    dry_run: bool = False


def _foundation_with_log() -> tuple[MagicMock, list[str]]:
    """Build foundation mocks whose awaits append to a shared call_log.

    Every foundation method records what it was called on, in order,
    across ALL stages. Use this to assert ordering across the whole
    pipeline, not just within one stage.
    """
    call_log: list[str] = []

    async def _record_load(**kwargs: Any) -> dict[str, Any]:
        call_log.append(f"load_full_context:{kwargs.get('task_query', '')[:30]}")
        return {}

    async def _record_check(client_id: str, action_type: str) -> str:
        call_log.append(f"autonomy.check:{action_type}")
        return "suggest"

    async def _record_similar(**kwargs: Any) -> list[dict]:
        call_log.append(f"patterns.find_similar:{kwargs.get('decision_type', '')}")
        return []

    async def _record_retrieve(**kwargs: Any) -> list[dict]:  # pragma: no cover
        # Should NOT fire — compose now pulls knowledge via load_full_context.
        call_log.append(f"knowledge.retrieve:{kwargs.get('query', '')[:30]}")
        return []

    async def _record_log_decision(**kwargs: Any) -> str:  # pragma: no cover
        call_log.append(f"decisions.log_decision:{kwargs.get('decision_type', '')}")
        return "dec-id"

    memory = MagicMock()
    memory.load_full_context = AsyncMock(side_effect=_record_load)
    autonomy = MagicMock()
    autonomy.check = AsyncMock(side_effect=_record_check)
    patterns = MagicMock()
    patterns.find_similar = AsyncMock(side_effect=_record_similar)
    knowledge = MagicMock()
    knowledge.retrieve = AsyncMock(side_effect=_record_retrieve)
    decisions = MagicMock()
    decisions.log_decision = AsyncMock(side_effect=_record_log_decision)

    foundation = MagicMock()
    foundation.memory = memory
    foundation.autonomy = autonomy
    foundation.patterns = patterns
    foundation.knowledge = knowledge
    foundation.decisions = decisions

    return foundation, call_log


def _build_scout(
    foundation: MagicMock,
    *,
    stages: dict[str, MagicMock],
) -> ScoutSystem:
    """Wire the 6 factories so each stage method gets its pre-built mock."""
    return ScoutSystem(
        memory_store=foundation.memory,
        decision_logger=foundation.decisions,
        pattern_matcher=foundation.patterns,
        autonomy_gate=foundation.autonomy,
        knowledge_store=foundation.knowledge,
        pull_stage_factory=lambda: stages["pull"],
        score_stage_factory=lambda: stages["score"],
        screen_stage_factory=lambda: stages["screen"],
        identity_stage_factory=lambda: stages["identity"],
        enrich_stage_factory=lambda: stages["enrich"],
        composer_factory=lambda: stages["composer"],
    )


def _build_batch_stage(
    result: _StubStageResult,
    *,
    call_log: list[str],
    name: str,
) -> MagicMock:
    """Build a stage mock whose .run() appends 'stage.run:<name>' to call_log."""

    async def _run(*args: Any, **kwargs: Any) -> _StubStageResult:
        call_log.append(f"stage.run:{name}")
        return result

    stage = MagicMock()
    stage.run = AsyncMock(side_effect=_run)
    return stage


# --------------------------------------------------------------------------- #
# 1. Full 7-stage pipeline — every foundation call fires in order             #
# --------------------------------------------------------------------------- #


async def test_full_pipeline_foundation_calls_in_order() -> None:
    """Seven stages × three foundation calls + seven stage.run() = 28 entries.

    Per-stage ordering inside the foundation loop is covered by
    ``test_scout_system_foundation_loop.py``. This test adds the
    CROSS-STAGE proof: the dispatcher walks stages in the expected
    daemon order.
    """
    foundation, call_log = _foundation_with_log()
    stages = {
        name: _build_batch_stage(
            _StubStageResult(client_id="test-client"),
            call_log=call_log, name=name,
        )
        for name in ("pull", "score", "screen", "identity", "enrich")
    }

    # Composer mock — per-contact fan out. One contact = one compose call.
    from aios.scout.outreach.composer import ComposedDraft
    draft = ComposedDraft(
        contact_id="X",
        subject="hi",
        body="body",
        component_selections={},
        sources_referenced=[],
        fills_missing=[],
        persisted_draft_id=None,
    )

    async def _compose(*args: Any, **kwargs: Any) -> ComposedDraft:
        call_log.append("composer.compose:X")
        return draft

    composer = MagicMock()
    composer.compose = AsyncMock(side_effect=_compose)
    stages["composer"] = composer

    scout = _build_scout(foundation, stages=stages)

    await scout.run_pull("test-client", dry_run=True)
    await scout.run_score("test-client", dry_run=True, phase="v1")
    await scout.run_screen("test-client", dry_run=True)
    await scout.run_identity("test-client", dry_run=True)
    await scout.run_enrich("test-client", dry_run=True)
    await scout.run_score("test-client", dry_run=True, phase="v2")
    await scout.run_compose("test-client", [{"contact_id": "X"}], dry_run=True)

    # Per-method count assertions
    assert foundation.memory.load_full_context.await_count == 7
    assert foundation.autonomy.check.await_count == 7
    assert foundation.patterns.find_similar.await_count == 7
    # Knowledge.retrieve is NOT called directly — compose pulls via task_query
    foundation.knowledge.retrieve.assert_not_awaited()

    # Autonomy action_types in dispatched order
    action_types = [c.args[1] for c in foundation.autonomy.check.await_args_list]
    assert action_types == [
        "source_selection",
        "score_contact",
        "screen_contact",
        "identity_lookup",
        "enrich_contact",
        "score_contact",  # v2 re-score
        "render_draft",
    ]

    # The foundation-loop triplet fires BEFORE the stage for every stage —
    # so the call_log pattern per stage is always:
    #   load_full_context → autonomy.check → patterns.find_similar → stage.run
    load_events = [i for i, e in enumerate(call_log) if e.startswith("load_full_context")]
    check_events = [i for i, e in enumerate(call_log) if e.startswith("autonomy.check")]
    similar_events = [i for i, e in enumerate(call_log) if e.startswith("patterns.find_similar")]

    assert len(load_events) == 7
    assert len(check_events) == 7
    assert len(similar_events) == 7
    # For every stage n: load_n < check_n < similar_n
    for load_i, check_i, similar_i in zip(load_events, check_events, similar_events):
        assert load_i < check_i < similar_i


# --------------------------------------------------------------------------- #
# 2. Foundation primes BEFORE the stage runs (per stage)                      #
# --------------------------------------------------------------------------- #


async def test_each_stage_loads_foundation_before_running() -> None:
    """For every stage method, load_full_context must happen BEFORE stage.run()."""
    foundation, call_log = _foundation_with_log()
    stages = {
        name: _build_batch_stage(
            _StubStageResult(client_id="test-client"),
            call_log=call_log, name=name,
        )
        for name in ("pull", "score", "screen", "identity", "enrich")
    }
    composer = MagicMock()
    composer.compose = AsyncMock(return_value=None)  # no contacts
    stages["composer"] = composer

    scout = _build_scout(foundation, stages=stages)

    methods = [
        ("run_pull", "pull", {"dry_run": True}),
        ("run_score", "score", {"dry_run": True, "phase": "v1"}),
        ("run_screen", "screen", {"dry_run": True}),
        ("run_identity", "identity", {"dry_run": True}),
        ("run_enrich", "enrich", {"dry_run": True}),
    ]

    for method_name, stage_name, kwargs in methods:
        call_log.clear()
        method = getattr(scout, method_name)
        await method("test-client", **kwargs)
        # load_full_context must appear and must precede stage.run
        load_i = next(
            (i for i, e in enumerate(call_log) if e.startswith("load_full_context")),
            None,
        )
        run_i = next(
            (i for i, e in enumerate(call_log) if e == f"stage.run:{stage_name}"),
            None,
        )
        assert load_i is not None, f"{method_name}: no load_full_context recorded"
        assert run_i is not None, f"{method_name}: no stage.run recorded"
        assert load_i < run_i, f"{method_name}: foundation loaded AFTER stage.run"


# --------------------------------------------------------------------------- #
# 3. Compose task_query targets copywriting knowledge                         #
# --------------------------------------------------------------------------- #


async def test_compose_task_query_targets_copywriting_frameworks() -> None:
    """``run_compose`` passes a copywriting- or outbound-oriented task_query
    to load_full_context — that steers the similarity search over
    knowledge_base toward the relevant copywriting frameworks."""
    foundation, _ = _foundation_with_log()
    stages = {
        name: _build_batch_stage(
            _StubStageResult(client_id="test-client"),
            call_log=[], name=name,
        )
        for name in ("pull", "score", "screen", "identity", "enrich")
    }
    composer = MagicMock()
    composer.compose = AsyncMock(return_value=None)  # no contacts -> no fan out
    stages["composer"] = composer

    scout = _build_scout(foundation, stages=stages)
    await scout.run_compose("test-client", [], dry_run=True)

    foundation.memory.load_full_context.assert_awaited_once()
    load_kwargs = foundation.memory.load_full_context.call_args.kwargs
    query = load_kwargs.get("task_query", "").lower()
    assert "copywriting" in query or "outbound" in query


# --------------------------------------------------------------------------- #
# 4. Stage-failure isolation — compose still primes even when enrich raised   #
# --------------------------------------------------------------------------- #


async def test_foundation_loop_survives_stage_failure() -> None:
    """If an earlier stage raises, scout's stage methods are independent:
    the next call still primes the foundation (task 16.5's _prime_foundation
    always runs before stage.run). This proves Scout's wrappers don't
    leak state between stages.

    The broader "continue pipeline on failure" semantic is the daemon's
    responsibility and is covered in test_client_worker.py.
    """
    foundation, call_log = _foundation_with_log()

    async def _raise_enrich(*args: Any, **kwargs: Any) -> None:
        call_log.append("stage.run:enrich_raised")
        raise RuntimeError("enrich exploded")

    enrich_stage = MagicMock()
    enrich_stage.run = AsyncMock(side_effect=_raise_enrich)

    stages = {
        "pull": _build_batch_stage(_StubStageResult(client_id="test-client"), call_log=call_log, name="pull"),
        "score": _build_batch_stage(_StubStageResult(client_id="test-client"), call_log=call_log, name="score"),
        "screen": _build_batch_stage(_StubStageResult(client_id="test-client"), call_log=call_log, name="screen"),
        "identity": _build_batch_stage(_StubStageResult(client_id="test-client"), call_log=call_log, name="identity"),
        "enrich": enrich_stage,
    }
    composer = MagicMock()
    composer.compose = AsyncMock(return_value=None)  # no contacts -> no fan out
    stages["composer"] = composer

    scout = _build_scout(foundation, stages=stages)

    # enrich raises — caller sees the exception
    with pytest.raises(RuntimeError, match="enrich exploded"):
        await scout.run_enrich("test-client", dry_run=True)

    # Foundation was still primed for enrich (happened before stage.run)
    assert foundation.memory.load_full_context.await_count == 1
    assert foundation.autonomy.check.await_count == 1

    # Compose still primes cleanly — scout's stage methods don't share state
    await scout.run_compose("test-client", [], dry_run=True)
    assert foundation.memory.load_full_context.await_count == 2
    assert foundation.autonomy.check.await_count == 2


# --------------------------------------------------------------------------- #
# 5. client_id propagation                                                    #
# --------------------------------------------------------------------------- #


async def test_foundation_calls_use_correct_client_id() -> None:
    """Every foundation call across every stage must see the same client_id
    that the caller passed — not a cached or fixture default."""
    foundation, _ = _foundation_with_log()
    stages = {
        name: _build_batch_stage(
            _StubStageResult(client_id="test-client"),
            call_log=[], name=name,
        )
        for name in ("pull", "score", "screen", "identity", "enrich")
    }
    composer = MagicMock()
    composer.compose = AsyncMock(return_value=None)
    stages["composer"] = composer

    scout = _build_scout(foundation, stages=stages)

    await scout.run_pull("test-client", dry_run=True)
    await scout.run_score("test-client", dry_run=True, phase="v1")
    await scout.run_screen("test-client", dry_run=True)
    await scout.run_identity("test-client", dry_run=True)
    await scout.run_enrich("test-client", dry_run=True)
    await scout.run_compose("test-client", [], dry_run=True)

    # Every load_full_context saw client_id="test-client"
    for call in foundation.memory.load_full_context.await_args_list:
        assert call.kwargs.get("client_id") == "test-client"

    # Every autonomy.check first arg was "test-client"
    for call in foundation.autonomy.check.await_args_list:
        assert call.args[0] == "test-client"

    # Every find_similar saw client_id="test-client"
    for call in foundation.patterns.find_similar.await_args_list:
        assert call.kwargs.get("client_id") == "test-client"
