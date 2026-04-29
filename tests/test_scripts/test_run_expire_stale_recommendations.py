"""Smoke tests for scripts/run_expire_stale_recommendations.py."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from scripts import run_expire_stale_recommendations


class _FakeEngine:
    def __init__(self, expired_count: int) -> None:
        self._expired = expired_count
        self.calls: list[tuple[datetime, int | None]] = []

    async def expire_stale(
        self, *, now: datetime, threshold_days: int | None = None,
    ) -> int:
        self.calls.append((now, threshold_days))
        return self._expired


async def test_run_uses_engine_default_when_threshold_none(monkeypatch, capsys):
    fake = _FakeEngine(expired_count=3)
    monkeypatch.setattr(
        run_expire_stale_recommendations, "_get_engine", lambda: fake,
    )

    args = argparse.Namespace(threshold_days=None)
    rc = await run_expire_stale_recommendations._run(args)

    assert rc == 0
    assert len(fake.calls) == 1
    now, threshold = fake.calls[0]
    assert now.tzinfo == timezone.utc
    assert threshold is None

    out = capsys.readouterr().out
    assert "optimizer_recommendations" in out
    assert "expired=3" in out
    assert "threshold_days=engine_default" in out


async def test_run_passes_threshold_override(monkeypatch, capsys):
    fake = _FakeEngine(expired_count=0)
    monkeypatch.setattr(
        run_expire_stale_recommendations, "_get_engine", lambda: fake,
    )

    args = argparse.Namespace(threshold_days=14)
    rc = await run_expire_stale_recommendations._run(args)

    assert rc == 0
    assert fake.calls[0][1] == 14

    out = capsys.readouterr().out
    assert "expired=0" in out
    assert "threshold_days=14" in out
