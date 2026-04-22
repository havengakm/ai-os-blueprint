"""NightlyScheduler — thin APScheduler wrapper for the AIOS daemon (Task 16.6).

Wraps ``AsyncIOScheduler`` so the daemon never directly imports apscheduler
machinery. Every job is wrapped in a try/except at registration time, so a
raising coroutine cannot propagate up into the scheduler loop and kill it —
the daemon's job must survive one bad client cycle to serve the rest.

Defaults:
    cron "0 2 * * *"  — 02:00 UTC nightly
    override via ``AIOS_DAEMON_CRON`` env var.

TODO (Plan 7): per-client timezone support. Right now all clients run at the
same UTC cron; per-client windows belong in a richer scheduler that reads
``client_config.send_window_timezone`` and enqueues one job per client.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

DEFAULT_NIGHTLY_CRON = "0 2 * * *"


class NightlyScheduler:
    """Thin wrapper around AsyncIOScheduler for nightly daemon jobs.

    One daemon, one scheduler, as many jobs as you register. Jobs catch
    their own exceptions so a single failure never takes down the loop.
    """

    def __init__(self, scheduler: AsyncIOScheduler | None = None) -> None:
        """``scheduler`` lets tests inject a fake; production passes None."""
        self._scheduler = scheduler or AsyncIOScheduler(timezone="UTC")

    def add_nightly_job(
        self,
        cron_spec: str,
        coro_factory: Callable[[], Awaitable[Any]],
        *,
        job_id: str = "nightly_cycle",
    ) -> None:
        """Register ``coro_factory`` to run on ``cron_spec`` (5-field cron).

        ``coro_factory`` is a zero-arg callable that returns an awaitable on
        each call (NOT a pre-constructed coroutine — that would be consumed
        after the first run).
        """
        trigger = CronTrigger.from_crontab(cron_spec, timezone="UTC")

        async def _runner() -> None:
            # Shield the scheduler from any job-level exception.
            try:
                await coro_factory()
            except Exception:
                logger.exception(
                    "scheduler job failed job_id=%s — loop continues", job_id,
                )

        self._scheduler.add_job(
            _runner,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
        )
        logger.info(
            "scheduler job registered job_id=%s cron=%r", job_id, cron_spec,
        )

    def start(self) -> None:
        """Start the underlying AsyncIOScheduler."""
        self._scheduler.start()
        logger.info("scheduler started")

    def shutdown(self, *, wait: bool = True) -> None:
        """Shut down the scheduler. ``wait=True`` blocks until jobs finish."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("scheduler shutdown wait=%s", wait)

    @property
    def running(self) -> bool:
        """True iff the underlying scheduler is still running."""
        return bool(self._scheduler.running)

    def get_job(self, job_id: str) -> Any:
        """Return the job object by id (or None). Exposed for tests."""
        return self._scheduler.get_job(job_id)
