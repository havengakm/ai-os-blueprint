"""Tests for scripts/configure_trigify_monitors.py."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.configure_trigify_monitors as mod  # noqa: E402
from aios.scout.sources.trigify_monitors import (  # noqa: E402
    MonitorSpec,
    ProvisioningResult,
)


_VALID_YAML = """\
intent_keywords:
  - phrase: "social signals"
    scope_terms: ["gtm"]
competitors:
  - name: "Clay.com"
    linkedin_url: "https://linkedin.com/company/clay-labs"
brand:
  - "TestBrand"
"""


class _FakeCreator:
    """Records calls; returns a canned ProvisioningResult."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.live_result = ProvisioningResult(
            client_id="c1",
            created=[("[c1]-intent-social-signals", "sid-1")],
            skipped_existing=[],
            failed=[],
            all_search_ids=["sid-1"],
        )

    async def provision_from_yaml(
        self,
        client_id: str,
        yaml_spec: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> ProvisioningResult:
        self.calls.append({
            "client_id": client_id, "yaml_spec": yaml_spec, "dry_run": dry_run,
        })
        if dry_run:
            return ProvisioningResult(
                client_id=client_id,
                dry_run_planned=[
                    MonitorSpec(
                        name="[c1]-intent-social-signals",
                        monitor_type="intent_keyword",
                        trigify_payload={"query": "social signals", "platforms": ["linkedin"]},
                        source_yaml_section="intent_keywords",
                    ),
                ],
            )
        self.live_result.client_id = client_id
        return self.live_result


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("TRIGIFY_API_KEY", "test-trigify-key")


def _patch_deps(
    monkeypatch: pytest.MonkeyPatch, creator: _FakeCreator | None,
) -> None:
    """Avoid hitting Supabase + Trigify from the CLI under test."""
    monkeypatch.setattr(mod, "_build_supabase", lambda url, key: object())
    if creator is not None:
        # Replace the constructor so main()'s `TrigifyMonitorCreator(storage=...)`
        # call returns our fake.
        monkeypatch.setattr(
            mod, "TrigifyMonitorCreator",
            lambda storage=None, **_kw: creator,
        )


# --------------------------------------------------------------------------- #
# argparse / help                                                              #
# --------------------------------------------------------------------------- #


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        mod.main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    # Spot-check the key flags appear.
    assert "--client-id" in captured.out
    assert "--dry-run" in captured.out
    assert "--no-confirm" in captured.out


# --------------------------------------------------------------------------- #
# Missing YAML                                                                 #
# --------------------------------------------------------------------------- #


def test_dry_run_missing_yaml_exits_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_env(monkeypatch)
    missing = tmp_path / "does_not_exist.yaml"

    rc = mod.main([
        "--client-id=c1",
        f"--yaml-path={missing}",
        "--dry-run",
    ])

    assert rc == 1
    err = capsys.readouterr().err
    assert "YAML not found" in err
    assert str(missing) in err


# --------------------------------------------------------------------------- #
# Dry-run happy path                                                           #
# --------------------------------------------------------------------------- #


def test_dry_run_invokes_provision_with_dry_run_true(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_env(monkeypatch)
    yaml_path = tmp_path / "m.yaml"
    yaml_path.write_text(_VALID_YAML)

    creator = _FakeCreator()
    _patch_deps(monkeypatch, creator)

    rc = mod.main([
        "--client-id=c1",
        f"--yaml-path={yaml_path}",
        "--dry-run",
    ])

    assert rc == 0
    # Exactly one provision call, with dry_run=True.
    assert len(creator.calls) == 1
    call = creator.calls[0]
    assert call["client_id"] == "c1"
    assert call["dry_run"] is True
    # The YAML was parsed into the spec dict.
    assert "intent_keywords" in call["yaml_spec"]

    out = capsys.readouterr().out
    assert "Dry-run" in out
    assert "intent_keyword" in out
    assert "[c1]-intent-social-signals" in out


# --------------------------------------------------------------------------- #
# Live run with --no-confirm                                                   #
# --------------------------------------------------------------------------- #


def test_live_run_no_confirm_skips_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_env(monkeypatch)
    yaml_path = tmp_path / "m.yaml"
    yaml_path.write_text(_VALID_YAML)

    creator = _FakeCreator()
    _patch_deps(monkeypatch, creator)

    # Sentinel so we can detect any accidental input() call.
    def _boom(*_a: Any, **_kw: Any) -> None:
        raise AssertionError("input() should not be called with --no-confirm")

    monkeypatch.setattr("builtins.input", _boom)

    rc = mod.main([
        "--client-id=c1",
        f"--yaml-path={yaml_path}",
        "--no-confirm",
    ])

    assert rc == 0
    # Two calls: dry-run preview THEN live provision.
    assert len(creator.calls) == 2
    assert creator.calls[0]["dry_run"] is True
    assert creator.calls[1]["dry_run"] is False

    out = capsys.readouterr().out
    assert "created" in out.lower()


def test_live_run_nonzero_exit_when_failed_non_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_env(monkeypatch)
    yaml_path = tmp_path / "m.yaml"
    yaml_path.write_text(_VALID_YAML)

    creator = _FakeCreator()
    creator.live_result.failed.append(
        ("[c1]-competitor-clay-com", "HTTP 500: internal error"),
    )
    _patch_deps(monkeypatch, creator)
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "y")

    rc = mod.main([
        "--client-id=c1",
        f"--yaml-path={yaml_path}",
        "--no-confirm",
    ])

    assert rc == 1
    err = capsys.readouterr().err
    assert "HTTP 500" in err


# --------------------------------------------------------------------------- #
# Missing env vars                                                             #
# --------------------------------------------------------------------------- #


def test_missing_supabase_env_exits_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    yaml_path = tmp_path / "m.yaml"
    yaml_path.write_text(_VALID_YAML)

    rc = mod.main([
        "--client-id=c1",
        f"--yaml-path={yaml_path}",
        "--dry-run",
    ])

    assert rc == 1
    err = capsys.readouterr().err
    assert "SUPABASE_URL" in err
