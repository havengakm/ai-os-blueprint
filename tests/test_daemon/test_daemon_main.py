"""Smoke tests for ``aios/daemon/main.py::run_daemon`` and
``run_nightly_cycle``."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aios.daemon.main import run_daemon, run_nightly_cycle


@pytest.mark.asyncio
async def test_run_daemon_shuts_down_when_event_preset():
    """run_daemon wires a scheduler + blocks on the shutdown event. When
    the caller passes a pre-set event, the daemon exits cleanly after
    registering and starting the scheduler."""
    # Pre-set event → daemon loop exits immediately.
    event = asyncio.Event()
    event.set()

    fake_scheduler = MagicMock()
    fake_scheduler.add_nightly_job = MagicMock()
    fake_scheduler.start = MagicMock()
    fake_scheduler.shutdown = MagicMock()

    fake_registry = MagicMock()
    fake_settings = MagicMock(environment="test")

    # run_daemon imports get_registry + get_settings lazily; patch at
    # source modules so the import inside the coroutine picks up the mock.
    with patch("api.deps.get_registry", return_value=fake_registry), \
         patch("config.settings.get_settings", return_value=fake_settings):
        await run_daemon(shutdown_event=event, scheduler=fake_scheduler)

    # Job was registered and scheduler started + shut down cleanly.
    fake_scheduler.add_nightly_job.assert_called_once()
    fake_scheduler.start.assert_called_once()
    fake_scheduler.shutdown.assert_called_once()
    # ``wait=True`` passed to shutdown.
    assert fake_scheduler.shutdown.call_args.kwargs.get("wait") is True


@pytest.mark.asyncio
async def test_run_nightly_cycle_skips_missing_client_config():
    """When fetch_client_config returns None for a client, the daemon logs
    and moves on — no crash."""
    registry = MagicMock()
    factory = MagicMock()

    with patch(
        "aios.daemon.main.list_active_clients",
        new=AsyncMock(return_value=["c1", "c2"]),
    ), patch(
        "aios.daemon.main.fetch_client_config",
        new=AsyncMock(side_effect=[None, {"active_directories": []}]),
    ), patch(
        "aios.daemon.main._build_scout_for_client",
        return_value=MagicMock(),
    ), patch(
        "aios.daemon.main.run_client_cycle",
        new=AsyncMock(return_value=MagicMock(ok=True, errors=[])),
    ) as mock_cycle:
        await run_nightly_cycle(registry, factory)

    # c2 was the only client with a config row — only one cycle ran.
    mock_cycle.assert_awaited_once()
    assert mock_cycle.await_args.args[1] == "c2"


@pytest.mark.asyncio
async def test_run_nightly_cycle_isolates_per_client_failures():
    """If one client raises during setup (unhandled in run_client_cycle),
    the daemon catches it and continues to the next client."""
    registry = MagicMock()
    factory = MagicMock()

    async def fake_cycle(_scout, client_id, **_kwargs):
        if client_id == "c1":
            raise RuntimeError("c1 blew up")
        return MagicMock(ok=True, errors=[])

    with patch(
        "aios.daemon.main.list_active_clients",
        new=AsyncMock(return_value=["c1", "c2", "c3"]),
    ), patch(
        "aios.daemon.main.fetch_client_config",
        new=AsyncMock(return_value={"active_directories": []}),
    ), patch(
        "aios.daemon.main._build_scout_for_client",
        return_value=MagicMock(),
    ), patch(
        "aios.daemon.main.run_client_cycle",
        new=AsyncMock(side_effect=fake_cycle),
    ) as mock_cycle:
        await run_nightly_cycle(registry, factory)

    # All three were attempted; c2 + c3 ran after c1 crashed.
    assert mock_cycle.await_count == 3


@pytest.mark.asyncio
async def test_run_nightly_cycle_no_active_clients_is_noop():
    registry = MagicMock()
    factory = MagicMock()
    with patch(
        "aios.daemon.main.list_active_clients",
        new=AsyncMock(return_value=[]),
    ), patch(
        "aios.daemon.main.run_client_cycle",
        new=AsyncMock(),
    ) as mock_cycle:
        await run_nightly_cycle(registry, factory)
    mock_cycle.assert_not_called()


def test_build_scout_for_client_wires_icebreaker_adapter():
    """Regression: the daemon's scout builder MUST inject an IcebreakerAdapter
    into the EnrichStage. Without it the adapter is never invoked in live
    runs and every contact lands with icebreaker_tier=None.
    """
    from aios.daemon.main import _build_scout_for_client
    from systems.scout.enrich.icebreaker_adapter import IcebreakerAdapter

    registry = MagicMock()
    factory = MagicMock()
    client_config: dict = {"active_directories": []}

    scout = _build_scout_for_client(registry, factory, client_config)

    # ScoutSystem stores stage factories — instantiate the enrich stage the
    # way the real cycle would, then inspect the wired adapter.
    enrich_stage = scout._enrich_factory()
    assert enrich_stage._icebreaker_adapter is not None, (
        "IcebreakerAdapter not wired into EnrichStage — icebreakers will "
        "never fire in live runs (bug observed in fix/enrich-compose-pipeline-bugs)"
    )
    assert isinstance(enrich_stage._icebreaker_adapter, IcebreakerAdapter)
