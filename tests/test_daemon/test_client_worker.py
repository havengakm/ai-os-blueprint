"""Tests for ``aios/daemon/client_worker.py::run_client_cycle``."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from aios.daemon.client_worker import (
    STAGE_ORDER,
    run_client_cycle,
)


def _build_scout_mock() -> MagicMock:
    scout = MagicMock()
    scout.run_pull = AsyncMock(return_value={"ok": True})
    scout.run_score = AsyncMock(return_value={"ok": True})
    scout.run_screen = AsyncMock(return_value={"ok": True})
    scout.run_identity = AsyncMock(return_value={"ok": True})
    scout.run_enrich = AsyncMock(return_value={"ok": True})
    return scout


@pytest.mark.asyncio
async def test_run_client_cycle_runs_every_stage_in_order():
    """Happy path: pull → score_v1 → screen → identity → enrich →
    score_v2. Compose is excluded (NotImplementedError on purpose)."""
    scout = _build_scout_mock()
    # Exclude compose (requires composer_backend.fetch_eligible_contacts —
    # not in Plan 1 scope).
    stages = tuple(s for s in STAGE_ORDER if s != "compose")

    result = await run_client_cycle(scout, "c1", dry_run=False, stages=stages)

    assert result.client_id == "c1"
    assert not result.errors
    assert [r.stage for r in result.stages_run] == list(stages)
    assert all(r.ok for r in result.stages_run)

    # Score runs twice: once v1, once v2. Other stages once each.
    scout.run_pull.assert_awaited_once()
    assert scout.run_score.await_count == 2
    scout.run_screen.assert_awaited_once()
    scout.run_identity.assert_awaited_once()
    scout.run_enrich.assert_awaited_once()

    phases = [c.kwargs.get("phase") for c in scout.run_score.await_args_list]
    assert phases == ["v1", "v2"]


@pytest.mark.asyncio
async def test_run_client_cycle_dry_run_forwarded_to_every_stage():
    """dry_run=True propagates to every run_<stage> call."""
    scout = _build_scout_mock()
    stages = ("pull", "score_v1", "screen", "identity", "enrich", "score_v2")

    await run_client_cycle(scout, "c1", dry_run=True, stages=stages)

    assert scout.run_pull.await_args.kwargs["dry_run"] is True
    assert scout.run_screen.await_args.kwargs["dry_run"] is True
    assert scout.run_identity.await_args.kwargs["dry_run"] is True
    assert scout.run_enrich.await_args.kwargs["dry_run"] is True
    for call in scout.run_score.await_args_list:
        assert call.kwargs["dry_run"] is True


@pytest.mark.asyncio
async def test_run_client_cycle_isolates_per_stage_failures():
    """When screen raises, subsequent stages still run and the cycle
    finishes with an error recorded for screen only."""
    scout = _build_scout_mock()
    scout.run_screen = AsyncMock(side_effect=RuntimeError("boom"))
    stages = ("pull", "score_v1", "screen", "identity", "enrich", "score_v2")

    result = await run_client_cycle(scout, "c1", dry_run=False, stages=stages)

    # All six stages have a record, one of them failed.
    assert len(result.stages_run) == 6
    ok_map = {r.stage: r.ok for r in result.stages_run}
    assert ok_map["pull"] is True
    assert ok_map["score_v1"] is True
    assert ok_map["screen"] is False
    # Degraded mode: identity/enrich/score_v2 still ran after screen failed.
    assert ok_map["identity"] is True
    assert ok_map["enrich"] is True
    assert ok_map["score_v2"] is True

    # Exactly one error recorded, pointing at screen.
    assert len(result.errors) == 1
    assert result.errors[0]["stage"] == "screen"
    assert result.errors[0]["error_type"] == "RuntimeError"
    assert "boom" in result.errors[0]["error_message"]

    # Downstream awaitables actually ran despite screen's failure.
    scout.run_identity.assert_awaited_once()
    scout.run_enrich.assert_awaited_once()
    assert scout.run_score.await_count == 2


@pytest.mark.asyncio
async def test_run_client_cycle_compose_stage_raises_not_implemented():
    """Compose is an explicit NotImplementedError for Plan 1 — caller
    sees a stage-level error entry rather than a crashed daemon."""
    scout = _build_scout_mock()

    result = await run_client_cycle(
        scout, "c1", dry_run=False, stages=("compose",),
    )

    assert len(result.stages_run) == 1
    run = result.stages_run[0]
    assert run.stage == "compose"
    assert run.ok is False
    assert run.error_type == "NotImplementedError"
    assert len(result.errors) == 1


@pytest.mark.asyncio
async def test_run_client_cycle_rejects_unknown_stage():
    scout = _build_scout_mock()
    with pytest.raises(ValueError):
        await run_client_cycle(
            scout, "c1", dry_run=False, stages=("pull", "bogus"),
        )


@pytest.mark.asyncio
async def test_run_client_cycle_default_stages_include_all_seven():
    """Without ``stages=`` arg, every stage in STAGE_ORDER runs. Compose
    errors cleanly; every other stage succeeds."""
    scout = _build_scout_mock()

    result = await run_client_cycle(scout, "c1", dry_run=False)

    assert [r.stage for r in result.stages_run] == list(STAGE_ORDER)
    # Six ok + one compose error.
    assert sum(1 for r in result.stages_run if r.ok) == 6
    assert len(result.errors) == 1
    assert result.errors[0]["stage"] == "compose"
