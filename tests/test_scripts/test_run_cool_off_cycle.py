"""Smoke tests for scripts/run_cool_off_cycle.py."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from scripts import run_cool_off_cycle
from systems.beacon.reply.cool_off import CoolOffCycleResult


class _FakeRuntime:
    def __init__(self, result: CoolOffCycleResult) -> None:
        self._result = result
        self.calls: list[tuple[str, datetime]] = []

    async def run_cycle(
        self, client_id: str, *, now: datetime,
    ) -> CoolOffCycleResult:
        self.calls.append((client_id, now))
        return self._result


async def test_run_invokes_runtime_and_prints_summary(monkeypatch, capsys):
    fake = _FakeRuntime(
        CoolOffCycleResult(
            cooled_off_count=4, re_entered_count=2, marked_dead_count=1,
        )
    )
    monkeypatch.setattr(run_cool_off_cycle, "_get_runtime", lambda: fake)

    args = argparse.Namespace(client_id="acme-co-zero")
    rc = await run_cool_off_cycle._run(args)

    assert rc == 0
    assert len(fake.calls) == 1
    client_id, now = fake.calls[0]
    assert client_id == "acme-co-zero"
    assert now.tzinfo == timezone.utc

    out = capsys.readouterr().out
    assert "cool_off cycle" in out
    assert "client=acme-co-zero" in out
    assert "cooled_off=4" in out
    assert "re_entered=2" in out
    assert "marked_dead=1" in out


async def test_run_with_zero_result_still_prints(monkeypatch, capsys):
    """Quiet day (nothing to do) still emits a structured stdout line."""
    fake = _FakeRuntime(CoolOffCycleResult())  # all zeros
    monkeypatch.setattr(run_cool_off_cycle, "_get_runtime", lambda: fake)

    args = argparse.Namespace(client_id="c1")
    rc = await run_cool_off_cycle._run(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "cooled_off=0" in out
    assert "re_entered=0" in out
    assert "marked_dead=0" in out
