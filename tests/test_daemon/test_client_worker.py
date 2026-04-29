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
    scout.run_cheap_resolve = AsyncMock(return_value={"ok": True})
    scout.run_score = AsyncMock(return_value={"ok": True})
    scout.run_screen = AsyncMock(return_value={"ok": True})
    scout.run_identity = AsyncMock(return_value={"ok": True})
    scout.run_enrich = AsyncMock(return_value={"ok": True})
    scout.run_compose = AsyncMock(return_value={"ok": True})
    return scout


def _build_composer_backend_mock(contacts: list[dict] | None = None) -> MagicMock:
    """Minimal structural stand-in for ComposerStorageBackend.

    Only ``fetch_eligible_contacts`` is exercised by the daemon's
    compose stage; the rest of the protocol is never called here.
    """
    backend = MagicMock()
    backend.fetch_eligible_contacts = AsyncMock(
        return_value=list(contacts or []),
    )
    return backend


@pytest.mark.asyncio
async def test_run_client_cycle_runs_every_stage_in_order():
    """Happy path: pull → score_v1 → screen → identity → enrich →
    score_v2 → compose."""
    scout = _build_scout_mock()
    composer_backend = _build_composer_backend_mock(
        contacts=[{"contact_id": "u1", "niche": "n"}],
    )

    result = await run_client_cycle(
        scout, "c1",
        dry_run=False,
        stages=STAGE_ORDER,
        composer_backend=composer_backend,
    )

    assert result.client_id == "c1"
    assert not result.errors
    assert [r.stage for r in result.stages_run] == list(STAGE_ORDER)
    assert all(r.ok for r in result.stages_run)

    # Score runs twice: once v1, once v2. Other stages once each.
    scout.run_pull.assert_awaited_once()
    assert scout.run_score.await_count == 2
    scout.run_screen.assert_awaited_once()
    scout.run_identity.assert_awaited_once()
    scout.run_enrich.assert_awaited_once()
    scout.run_compose.assert_awaited_once()
    composer_backend.fetch_eligible_contacts.assert_awaited_once_with("c1")

    phases = [c.kwargs.get("phase") for c in scout.run_score.await_args_list]
    assert phases == ["v1", "v2"]


@pytest.mark.asyncio
async def test_run_client_cycle_dry_run_forwarded_to_every_stage():
    """dry_run=True propagates to every run_<stage> call — including compose."""
    scout = _build_scout_mock()
    composer_backend = _build_composer_backend_mock(
        contacts=[{"contact_id": "u1", "niche": "n"}],
    )

    await run_client_cycle(
        scout, "c1",
        dry_run=True,
        stages=STAGE_ORDER,
        composer_backend=composer_backend,
    )

    assert scout.run_pull.await_args.kwargs["dry_run"] is True
    assert scout.run_screen.await_args.kwargs["dry_run"] is True
    assert scout.run_identity.await_args.kwargs["dry_run"] is True
    assert scout.run_enrich.await_args.kwargs["dry_run"] is True
    assert scout.run_compose.await_args.kwargs["dry_run"] is True
    for call in scout.run_score.await_args_list:
        assert call.kwargs["dry_run"] is True


@pytest.mark.asyncio
async def test_run_client_cycle_isolates_per_stage_failures():
    """When screen raises, subsequent stages still run and the cycle
    finishes with an error recorded for screen only."""
    scout = _build_scout_mock()
    scout.run_screen = AsyncMock(side_effect=RuntimeError("boom"))
    composer_backend = _build_composer_backend_mock()  # empty -> compose skips cleanly

    result = await run_client_cycle(
        scout, "c1",
        dry_run=False,
        stages=STAGE_ORDER,
        composer_backend=composer_backend,
    )

    # All seven stages have a record, one of them failed.
    assert len(result.stages_run) == len(STAGE_ORDER)
    ok_map = {r.stage: r.ok for r in result.stages_run}
    assert ok_map["pull"] is True
    assert ok_map["score_v1"] is True
    assert ok_map["screen"] is False
    # Degraded mode: identity/enrich/score_v2/compose still ran after screen failed.
    assert ok_map["identity"] is True
    assert ok_map["enrich"] is True
    assert ok_map["score_v2"] is True
    assert ok_map["compose"] is True

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
async def test_run_client_cycle_compose_stage_composes_eligible_contacts():
    """Compose stage fetches eligibles and dispatches to run_compose."""
    scout = _build_scout_mock()
    contacts = [
        {"contact_id": "u1", "niche": "n"},
        {"contact_id": "u2", "niche": "n"},
    ]
    composer_backend = _build_composer_backend_mock(contacts=contacts)

    result = await run_client_cycle(
        scout, "c1",
        dry_run=False,
        stages=("compose",),
        composer_backend=composer_backend,
    )

    assert len(result.stages_run) == 1
    assert result.stages_run[0].stage == "compose"
    assert result.stages_run[0].ok is True
    assert not result.errors

    composer_backend.fetch_eligible_contacts.assert_awaited_once_with("c1")
    scout.run_compose.assert_awaited_once()
    # run_compose called with (client_id, contacts) and dry_run kwarg.
    call = scout.run_compose.await_args
    assert call.args[0] == "c1"
    assert call.args[1] == contacts
    assert call.kwargs["dry_run"] is False


@pytest.mark.asyncio
async def test_run_client_cycle_compose_stage_skips_when_no_eligibles():
    """Compose stage records ok=True and does NOT call run_compose when
    the backend returns an empty list."""
    scout = _build_scout_mock()
    composer_backend = _build_composer_backend_mock(contacts=[])

    result = await run_client_cycle(
        scout, "c1",
        dry_run=False,
        stages=("compose",),
        composer_backend=composer_backend,
    )

    assert len(result.stages_run) == 1
    assert result.stages_run[0].stage == "compose"
    assert result.stages_run[0].ok is True
    assert not result.errors
    composer_backend.fetch_eligible_contacts.assert_awaited_once_with("c1")
    scout.run_compose.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_client_cycle_compose_stage_errors_without_backend():
    """If the compose stage is selected but no composer_backend is
    threaded through, the stage surfaces a clean error (not a crash)."""
    scout = _build_scout_mock()

    result = await run_client_cycle(
        scout, "c1", dry_run=False, stages=("compose",),
    )

    assert len(result.stages_run) == 1
    run = result.stages_run[0]
    assert run.stage == "compose"
    assert run.ok is False
    assert run.error_type == "RuntimeError"
    assert len(result.errors) == 1
    scout.run_compose.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_client_cycle_rejects_unknown_stage():
    scout = _build_scout_mock()
    with pytest.raises(ValueError):
        await run_client_cycle(
            scout, "c1", dry_run=False, stages=("pull", "bogus"),
        )


@pytest.mark.asyncio
async def test_run_client_cycle_default_stages_include_all_eight():
    """Without ``stages=`` arg, every stage in STAGE_ORDER runs green when
    a composer_backend is supplied. As of 2026-04-29 (Pattern C), the
    pipeline has 8 stages — pull, cheap_resolve, score_v1, screen,
    identity, enrich, score_v2, compose."""
    scout = _build_scout_mock()
    composer_backend = _build_composer_backend_mock(
        contacts=[{"contact_id": "u1", "niche": "n"}],
    )

    result = await run_client_cycle(
        scout, "c1", dry_run=False, composer_backend=composer_backend,
    )

    assert [r.stage for r in result.stages_run] == list(STAGE_ORDER)
    assert sum(1 for r in result.stages_run if r.ok) == len(STAGE_ORDER)
    assert not result.errors


@pytest.mark.asyncio
async def test_run_client_cycle_forwards_max_companies_to_pull_only():
    """When set, max_companies_per_source threads to run_pull. Other
    stages don't receive it."""
    scout = _build_scout_mock()

    await run_client_cycle(
        scout, "c1",
        dry_run=False,
        stages=("pull", "score_v1", "screen"),
        max_companies_per_source=5,
    )

    assert scout.run_pull.await_args.kwargs["max_companies_per_source"] == 5
    # Other stages don't accept / receive the kwarg.
    assert "max_companies_per_source" not in scout.run_score.await_args.kwargs
    assert "max_companies_per_source" not in scout.run_screen.await_args.kwargs


@pytest.mark.asyncio
async def test_run_client_cycle_omits_max_companies_when_none():
    """Default None means the kwarg is NOT passed — orchestrator's own
    default applies. Avoids accidentally pinning the cap to None."""
    scout = _build_scout_mock()

    await run_client_cycle(
        scout, "c1",
        dry_run=False,
        stages=("pull",),
        max_companies_per_source=None,
    )

    assert "max_companies_per_source" not in scout.run_pull.await_args.kwargs
