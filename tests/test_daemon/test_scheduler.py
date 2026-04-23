"""Tests for ``aios/daemon/scheduler.py::NightlyScheduler``."""
from __future__ import annotations

import asyncio

import pytest

from aios.daemon.scheduler import DEFAULT_NIGHTLY_CRON, NightlyScheduler


@pytest.mark.asyncio
async def test_scheduler_registers_job_under_expected_id():
    sched = NightlyScheduler()

    ran = asyncio.Event()

    async def _job() -> None:
        ran.set()

    sched.add_nightly_job(DEFAULT_NIGHTLY_CRON, _job, job_id="nightly_cycle")
    try:
        sched.start()
        assert sched.running
        job = sched.get_job("nightly_cycle")
        assert job is not None
    finally:
        sched.shutdown(wait=True)
        # AsyncIOScheduler.shutdown transitions state on the next loop
        # tick — sleep briefly to let the state settle before asserting.
        await asyncio.sleep(0.05)
        assert not sched.running


@pytest.mark.asyncio
async def test_scheduler_shutdown_is_idempotent():
    sched = NightlyScheduler()

    async def _job() -> None:
        pass

    sched.add_nightly_job(DEFAULT_NIGHTLY_CRON, _job)
    sched.start()
    sched.shutdown(wait=True)
    await asyncio.sleep(0.05)
    # Second call should not raise — guards on ``running`` flag.
    sched.shutdown(wait=True)
    assert not sched.running


@pytest.mark.asyncio
async def test_scheduler_job_exceptions_do_not_kill_loop():
    """If the registered coroutine raises, the wrapper catches + logs;
    the scheduler itself stays running."""
    sched = NightlyScheduler()
    call_count = {"n": 0}

    async def _raising_job() -> None:
        call_count["n"] += 1
        raise RuntimeError("job blew up")

    sched.add_nightly_job(DEFAULT_NIGHTLY_CRON, _raising_job)
    sched.start()
    try:
        # Fire the registered runner directly to prove the wrapper
        # catches. We grab the wrapped function from the job and await it.
        job = sched.get_job("nightly_cycle")
        assert job is not None
        runner = job.func
        # Should NOT raise.
        await runner()
        assert call_count["n"] == 1
        assert sched.running, "scheduler must survive a job exception"
    finally:
        sched.shutdown(wait=True)


@pytest.mark.asyncio
async def test_scheduler_replace_existing_on_duplicate_id():
    """Registering twice with the same job_id replaces (no IDConflictError)."""
    sched = NightlyScheduler()

    async def _job() -> None:
        pass

    sched.add_nightly_job(DEFAULT_NIGHTLY_CRON, _job, job_id="nightly_cycle")
    # Should not raise.
    sched.add_nightly_job(DEFAULT_NIGHTLY_CRON, _job, job_id="nightly_cycle")
    sched.start()
    try:
        assert sched.get_job("nightly_cycle") is not None
    finally:
        sched.shutdown(wait=True)
