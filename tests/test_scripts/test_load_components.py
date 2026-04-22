"""Tests for scripts/load_components.py."""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.load_components as mod  # noqa: E402
from systems.scout.outreach.component_store import (  # noqa: E402
    ComponentVariant,
    VariantKeyTuple,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

_VALID_YAML = textwrap.dedent(
    """\
    ---
    variant_key: "v1_happy"
    component_type: "icebreaker"
    niche: "cro_growth_ugc_agency"
    offer_label: "pipeline_audit"
    variant_content: |
      Hello {{first_name}}.
    status: "draft"
    metadata:
      author: "Test"
    ab_epsilon: 0.1
    """
)

# File under components/icebreaker/ but declares component_type='WRONG_TYPE'
# — ComponentStore catches the mismatch and records it on summary.errors.
_INVALID_YAML = textwrap.dedent(
    """\
    ---
    variant_key: "v1_bad"
    component_type: "WRONG_TYPE"
    niche: "cro_growth_ugc_agency"
    offer_label: "pipeline_audit"
    variant_content: "x"
    """
)


def _write_variant(root: Path, component_type: str, filename: str, body: str) -> None:
    path = root / "cro_growth_ugc_agency" / "components" / component_type / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")


class _StubRealBackend:
    """Fake SupabaseComponentStoreBackend. ``raise_on_write=True`` asserts
    the dry-run path never hits real-backend writes."""

    def __init__(self, *, raise_on_write: bool = False) -> None:
        self.fetch_calls: list[tuple[str, list[VariantKeyTuple]]] = []
        self.insert_calls: list[tuple[str, list[ComponentVariant]]] = []
        self.update_calls: list[tuple[str, list[tuple[str, ComponentVariant]]]] = []
        self._raise_on_write = raise_on_write

    async def fetch_existing(
        self, client_id: str, keys: list[VariantKeyTuple],
    ) -> dict[VariantKeyTuple, dict[str, Any]]:
        self.fetch_calls.append((client_id, list(keys)))
        return {}

    async def insert_variants(
        self, client_id: str, variants: list[ComponentVariant],
    ) -> None:
        if self._raise_on_write:
            raise AssertionError("insert_variants called during dry-run")
        self.insert_calls.append((client_id, list(variants)))

    async def update_variants(
        self, client_id: str, updates: list[tuple[str, ComponentVariant]],
    ) -> None:
        if self._raise_on_write:
            raise AssertionError("update_variants called during dry-run")
        self.update_calls.append((client_id, list(updates)))


def _patch_backend(
    monkeypatch: pytest.MonkeyPatch, backend: _StubRealBackend,
) -> None:
    """Swap in our stub so main() doesn't touch Supabase."""
    monkeypatch.setattr(mod, "_build_supabase", lambda url, key: object())
    monkeypatch.setattr(
        mod, "SupabaseComponentStoreBackend", lambda client: backend,
    )


# ── Tests ───────────────────────────────────────────────────────────────────

def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        mod.main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--client-id" in out
    assert "--root" in out
    assert "--dry-run" in out
    assert "--no-confirm" in out


def test_missing_supabase_env_exits_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    rc = mod.main(["--client-id=c1", "--dry-run"])

    assert rc == 1
    err = capsys.readouterr().err
    assert "SUPABASE_URL" in err
    assert "SUPABASE_SERVICE_ROLE_KEY" in err


def test_missing_root_exits_zero_with_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_env(monkeypatch)
    backend = _StubRealBackend(raise_on_write=True)
    _patch_backend(monkeypatch, backend)

    missing_root = tmp_path / "does_not_exist"
    rc = mod.main([
        "--client-id=c1", f"--root={missing_root}", "--dry-run",
    ])

    assert rc == 0
    err = capsys.readouterr().err
    assert "not found" in err
    assert str(missing_root) in err
    assert backend.fetch_calls == []


def test_dry_run_happy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_env(monkeypatch)
    _write_variant(tmp_path, "icebreaker", "v1.yaml", _VALID_YAML)

    backend = _StubRealBackend(raise_on_write=True)
    _patch_backend(monkeypatch, backend)

    rc = mod.main([
        "--client-id=c1", f"--root={tmp_path}", "--dry-run",
    ])

    assert rc == 0
    # Dry-run READS from the real backend but MUST NOT write.
    assert len(backend.fetch_calls) == 1
    assert backend.insert_calls == []
    assert backend.update_calls == []

    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "1 inserted" in out


def test_dry_run_does_not_write_to_real_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_env(monkeypatch)
    _write_variant(tmp_path, "icebreaker", "v1.yaml", _VALID_YAML)
    _write_variant(
        tmp_path, "icebreaker", "v2.yaml",
        _VALID_YAML.replace("v1_happy", "v1_happy_two"),
    )

    backend = _StubRealBackend(raise_on_write=True)
    _patch_backend(monkeypatch, backend)

    rc = mod.main([
        "--client-id=c1", f"--root={tmp_path}", "--dry-run",
    ])

    assert rc == 0
    out = capsys.readouterr().out
    assert "2 inserted" in out
    # No writes leaked to the real backend.
    assert backend.insert_calls == []
    assert backend.update_calls == []


def test_live_run_no_confirm_skips_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_env(monkeypatch)
    _write_variant(tmp_path, "icebreaker", "v1.yaml", _VALID_YAML)

    backend = _StubRealBackend(raise_on_write=False)
    _patch_backend(monkeypatch, backend)

    def _boom(*_a: Any, **_kw: Any) -> None:
        raise AssertionError("input() should not be called with --no-confirm")

    monkeypatch.setattr("builtins.input", _boom)

    rc = mod.main([
        "--client-id=c1", f"--root={tmp_path}", "--no-confirm",
    ])

    assert rc == 0
    # Live sync produced exactly one insert batch on the real backend.
    assert len(backend.insert_calls) == 1
    client_id, variants = backend.insert_calls[0]
    assert client_id == "c1"
    assert len(variants) == 1
    assert variants[0].variant_key == "v1_happy"


def test_invalid_yaml_exits_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_env(monkeypatch)
    _write_variant(tmp_path, "icebreaker", "bad.yaml", _INVALID_YAML)

    backend = _StubRealBackend(raise_on_write=True)
    _patch_backend(monkeypatch, backend)

    rc = mod.main([
        "--client-id=c1", f"--root={tmp_path}", "--dry-run",
    ])

    assert rc == 1
    err = capsys.readouterr().err
    assert "component_type" in err


# ── setup_client.sh smoke checks (subprocess) ───────────────────────────────

def test_setup_client_sh_help_exits_zero() -> None:
    script = _REPO_ROOT / "scripts" / "setup_client.sh"
    result = subprocess.run(
        ["bash", str(script), "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "client-id" in result.stdout
    assert "--dry-run" in result.stdout
    assert "--no-confirm" in result.stdout


def test_setup_client_sh_no_args_exits_one() -> None:
    script = _REPO_ROOT / "scripts" / "setup_client.sh"
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    assert "client-id required" in result.stderr
