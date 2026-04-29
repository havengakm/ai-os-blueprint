"""Tests for ``scripts/run_daemon_once.py::main``."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import run_daemon_once  # noqa: E402
from aios.daemon.client_worker import ClientCycleResult, StageRun  # noqa: E402


def _fake_cycle_result(ok: bool = True) -> ClientCycleResult:
    stages = [
        StageRun(
            stage="pull",
            ok=ok,
            started_at="2026-04-22T00:00:00+00:00",
            completed_at="2026-04-22T00:00:01+00:00",
        ),
    ]
    errors = []
    if not ok:
        stages[0].error_type = "RuntimeError"
        stages[0].error_message = "boom"
        errors.append({
            "stage": "pull",
            "error_type": "RuntimeError",
            "error_message": "boom",
        })
    return ClientCycleResult(
        client_id="c1",
        started_at="2026-04-22T00:00:00+00:00",
        completed_at="2026-04-22T00:00:01+00:00",
        stages_run=stages,
        errors=errors,
    )


def test_run_daemon_once_exit_zero_on_happy_path():
    ok_result = _fake_cycle_result(ok=True)
    with patch(
        "run_daemon_once._run",
        new=AsyncMock(return_value=ok_result),
    ):
        exit_code = run_daemon_once.main(["--client-id", "c1"])
    assert exit_code == 0


def test_run_daemon_once_exit_one_when_stage_errored():
    bad_result = _fake_cycle_result(ok=False)
    with patch(
        "run_daemon_once._run",
        new=AsyncMock(return_value=bad_result),
    ):
        exit_code = run_daemon_once.main(["--client-id", "c1"])
    assert exit_code == 1


def test_run_daemon_once_exit_two_when_client_missing():
    with patch(
        "run_daemon_once._run",
        new=AsyncMock(return_value=None),
    ):
        exit_code = run_daemon_once.main(["--client-id", "nope"])
    assert exit_code == 2


def test_run_daemon_once_parses_stages_filter():
    ok_result = _fake_cycle_result(ok=True)
    mock_run = AsyncMock(return_value=ok_result)
    with patch("run_daemon_once._run", new=mock_run):
        run_daemon_once.main([
            "--client-id", "c1", "--stages", "pull,enrich", "--dry-run",
        ])

    # _run was called with the parsed tuple + dry_run=True.
    args = mock_run.await_args
    assert args.args[0] == "c1"
    assert args.args[1] is True  # dry_run
    assert args.args[2] == ("pull", "enrich")


def test_run_daemon_once_rejects_unknown_stage():
    with pytest.raises(SystemExit):
        run_daemon_once.main([
            "--client-id", "c1", "--stages", "pull,bogus",
        ])


def test_run_daemon_once_json_output_contains_client_id(capsys):
    ok_result = _fake_cycle_result(ok=True)
    with patch(
        "run_daemon_once._run",
        new=AsyncMock(return_value=ok_result),
    ):
        run_daemon_once.main(["--client-id", "c1", "--json"])
    captured = capsys.readouterr()
    assert '"client_id": "c1"' in captured.out


def test_run_daemon_once_forwards_max_companies_per_source():
    """``--max-companies-per-source N`` reaches _run as the 4th positional."""
    ok_result = _fake_cycle_result(ok=True)
    mock_run = AsyncMock(return_value=ok_result)
    with patch("run_daemon_once._run", new=mock_run):
        run_daemon_once.main([
            "--client-id", "c1",
            "--stages", "pull",
            "--max-companies-per-source", "5",
        ])

    args = mock_run.await_args
    # Positional args: (client_id, dry_run, stages, max_companies_per_source)
    assert args.args[3] == 5


def test_run_daemon_once_max_companies_default_none():
    """When the flag is omitted, _run gets None (orchestrator default)."""
    ok_result = _fake_cycle_result(ok=True)
    mock_run = AsyncMock(return_value=ok_result)
    with patch("run_daemon_once._run", new=mock_run):
        run_daemon_once.main(["--client-id", "c1"])

    args = mock_run.await_args
    assert args.args[3] is None
