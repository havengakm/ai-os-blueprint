"""AIOS autonomous daemon entry point (Task 16.6).

Long-running worker. Pseudocode:

    registry = get_registry()
    factory  = AdapterFactory(settings, registry)
    scheduler = NightlyScheduler()
    scheduler.add_nightly_job(cron, lambda: run_nightly_cycle(registry, factory))
    scheduler.start()
    await shutdown_event.wait()   # SIGTERM sets the event
    scheduler.shutdown()

Per-client error isolation lives in ``run_nightly_cycle``: one bad client
logs and is skipped, the daemon continues iterating the rest.

Envelope env vars:
    AIOS_DAEMON_CRON       — cron expression, default "0 2 * * *" (UTC)
    AIOS_DAEMON_DRY_RUN    — "true" forwards dry_run=True to every stage

Plan 7 follow-ups (TODO markers in-line):
    - per-client timezone cron (currently all-UTC)
    - weekly optimization jobs (report / cohort evaluator / stats puller)
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import TYPE_CHECKING

from aios.daemon.adapter_factory import AdapterFactory
from aios.daemon.client_registry import (
    fetch_client_config,
    list_active_clients,
)
from aios.daemon.client_worker import run_client_cycle
from aios.daemon.scheduler import DEFAULT_NIGHTLY_CRON, NightlyScheduler

if TYPE_CHECKING:
    from aios.foundation.registry import SystemRegistry

logger = logging.getLogger(__name__)


def _build_scout_for_client(
    registry: "SystemRegistry",
    factory: AdapterFactory,
    client_config: dict,
):
    """Build a ScoutSystem wired to REAL adapters for this client.

    Imported lazily so the scout package isn't pulled in at daemon-module
    import time (keeps ``python -m aios.daemon --help`` fast).

    This differs from ``ScoutSystem.from_registry`` — that method ships
    zero-adapter orchestrators (safe defaults for API-triggered runs).
    The daemon needs real adapters for each client's active_directories.
    """
    from systems.scout.outreach.composer import Composer
    from systems.scout.outreach.research import ResearchSelector
    from systems.scout.pipeline.enrich import EnrichStage
    from systems.scout.pipeline.identity import IdentityStage
    from systems.scout.pipeline.score_stage import ScoreStage
    from systems.scout.pipeline.screen import ScreenStage
    from systems.scout.skill import ScoutSystem

    return ScoutSystem(
        memory_store=registry.memory_store,
        decision_logger=registry.decision_logger,
        pattern_matcher=registry.pattern_matcher,
        autonomy_gate=registry.autonomy_gate,
        knowledge_store=registry.knowledge_store,
        pull_stage_factory=lambda: factory.build_pull_orchestrator(client_config),
        score_stage_factory=lambda: ScoreStage(storage=registry.score_backend),
        screen_stage_factory=lambda: ScreenStage(storage=registry.screen_backend),
        identity_stage_factory=lambda: IdentityStage(
            orchestrator=factory.build_identity_orchestrator(client_config),
            storage=registry.identity_backend,
        ),
        enrich_stage_factory=lambda: EnrichStage(
            orchestrator=factory.build_enrich_orchestrator(client_config),
            storage=registry.enrich_backend,
        ),
        composer_factory=lambda: Composer(
            storage=registry.composer_backend,
            research_selector=ResearchSelector(),
        ),
    )


async def run_nightly_cycle(
    registry: "SystemRegistry",
    factory: AdapterFactory,
    *,
    dry_run: bool = False,
) -> None:
    """Iterate every active client; run the nightly pipeline for each.

    Per-client try/except isolates failures. One client's crash never
    propagates up into the scheduler — every subsequent client still gets
    its cycle. The NightlyScheduler also shields itself at the job level,
    but belt-and-braces isolation makes the failure mode easier to reason
    about.
    """
    client_ids = await list_active_clients(registry)
    if not client_ids:
        logger.info("nightly cycle: no active clients; nothing to do")
        return

    logger.info(
        "nightly cycle start clients=%d dry_run=%s", len(client_ids), dry_run,
    )
    completed = 0
    failed = 0
    for client_id in client_ids:
        try:
            client_config = await fetch_client_config(registry, client_id)
            if client_config is None:
                logger.error(
                    "nightly cycle: skipping client=%s (no client_config row)",
                    client_id,
                )
                failed += 1
                continue

            scout = _build_scout_for_client(registry, factory, client_config)
            await run_client_cycle(scout, client_id, dry_run=dry_run)
            completed += 1
        except Exception:
            # Defence in depth. run_client_cycle catches stage-level
            # errors; this catches scheduler-plumbing and config errors.
            logger.exception(
                "nightly cycle: unhandled error for client=%s — continuing",
                client_id,
            )
            failed += 1

    logger.info(
        "nightly cycle end completed=%d failed=%d total=%d",
        completed, failed, len(client_ids),
    )


async def run_daemon(
    shutdown_event: asyncio.Event | None = None,
    *,
    scheduler: NightlyScheduler | None = None,
) -> None:
    """Top-level daemon coroutine.

    Parameters:
        shutdown_event: if supplied, the daemon waits on this event rather
            than installing signal handlers. Tests inject a pre-set event
            to short-circuit the loop.
        scheduler: injectable NightlyScheduler for tests.
    """
    from api.deps import get_registry
    from config.settings import get_settings

    settings = get_settings()
    cron_spec = os.environ.get("AIOS_DAEMON_CRON", DEFAULT_NIGHTLY_CRON)
    dry_run = os.environ.get("AIOS_DAEMON_DRY_RUN", "").lower() == "true"

    logger.info(
        "daemon startup cron=%r dry_run=%s env=%s",
        cron_spec, dry_run, settings.environment,
    )

    registry = get_registry()
    factory = AdapterFactory(settings, registry)
    sched = scheduler or NightlyScheduler()

    async def _job() -> None:
        await run_nightly_cycle(registry, factory, dry_run=dry_run)

    sched.add_nightly_job(cron_spec, _job, job_id="nightly_cycle")
    sched.start()

    event = shutdown_event or _install_signal_handlers()
    try:
        await event.wait()
    finally:
        logger.info("daemon shutdown initiated")
        sched.shutdown(wait=True)
        logger.info("daemon shutdown complete")


def _install_signal_handlers() -> asyncio.Event:
    """Install SIGTERM / SIGINT handlers that set the returned Event."""
    event = asyncio.Event()
    loop = asyncio.get_event_loop()

    def _handler(signame: str) -> None:
        logger.info("daemon received %s; setting shutdown event", signame)
        event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handler, sig.name)
        except NotImplementedError:
            # Windows / some test envs — graceful fallback.
            logger.debug("signal handler install not supported for %s", sig)
    return event
