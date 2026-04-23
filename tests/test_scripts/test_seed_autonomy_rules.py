"""Tests for scripts/seed_autonomy_rules.py."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.seed_autonomy_rules import ACTION_TYPES, main, seed_autonomy_rules  # noqa: E402


# ── Fake Supabase client ─────────────────────────────────────────────────────

@dataclass
class _FakeResult:
    data: list[dict[str, Any]] = field(default_factory=list)


class _FakeQuery:
    def __init__(self, parent: "FakeSupabase", table_name: str) -> None:
        self._parent = parent
        self._table = table_name
        self._op: str | None = None
        self._upsert_payload: dict[str, Any] | None = None
        self._filters: list[tuple[str, str, Any]] = []
        self._on_conflict: str | None = None
        self._select_cols: str | None = None

    # select chain
    def select(self, cols: str) -> "_FakeQuery":
        self._op = "select"
        self._select_cols = cols
        return self

    def eq(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append((col, "eq", val))
        return self

    # upsert chain
    def upsert(self, payload: dict[str, Any], on_conflict: str | None = None) -> "_FakeQuery":
        self._op = "upsert"
        self._upsert_payload = payload
        self._on_conflict = on_conflict
        return self

    def execute(self) -> _FakeResult:
        if self._op == "select":
            # Filter existing rows by filters
            rows = self._parent._tables.get(self._table, [])
            for col, op, val in self._filters:
                if op == "eq":
                    rows = [r for r in rows if r.get(col) == val]
            return _FakeResult(data=list(rows))

        if self._op == "upsert":
            assert self._upsert_payload is not None
            self._parent._upsert_calls.append(
                {
                    "table": self._table,
                    "payload": self._upsert_payload,
                    "on_conflict": self._on_conflict,
                }
            )
            # Simulate upsert semantics: add if not present on conflict key.
            rows = self._parent._tables.setdefault(self._table, [])
            key_fields = (self._on_conflict or "id").split(",")
            match = None
            for r in rows:
                if all(r.get(k) == self._upsert_payload.get(k) for k in key_fields):
                    match = r
                    break
            if match is not None:
                match.update(self._upsert_payload)
            else:
                rows.append(dict(self._upsert_payload))
            return _FakeResult(data=[self._upsert_payload])

        raise RuntimeError(f"Unknown op: {self._op}")


class FakeSupabase:
    def __init__(self, seed: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = seed or {}
        self._upsert_calls: list[dict[str, Any]] = []

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self, name)


# ── Tests ────────────────────────────────────────────────────────────────────

def test_action_types_is_20() -> None:
    assert len(ACTION_TYPES) == 20
    assert len(set(ACTION_TYPES)) == 20  # no duplicates


def test_full_run_upserts_all_20_when_empty() -> None:
    fake = FakeSupabase()
    summary = seed_autonomy_rules(fake, client_id="client-abc")

    assert summary == {"created": 20, "skipped": 0, "errors": 0}
    assert len(fake._upsert_calls) == 20
    for call in fake._upsert_calls:
        assert call["table"] == "autonomy_rules"
        assert call["on_conflict"] == "client_id,action_type"
        assert call["payload"]["client_id"] == "client-abc"
        assert call["payload"]["autonomy_level"] == "suggest"


def test_skips_existing_rows() -> None:
    fake = FakeSupabase(
        seed={
            "autonomy_rules": [
                {"client_id": "c1", "action_type": "copy_variant",
                 "autonomy_level": "suggest"},
                {"client_id": "c1", "action_type": "send_timing",
                 "autonomy_level": "draft"},
            ]
        }
    )
    summary = seed_autonomy_rules(fake, client_id="c1")

    assert summary["created"] == 18
    assert summary["skipped"] == 2
    assert summary["errors"] == 0
    # Only 18 upserts were actually made
    assert len(fake._upsert_calls) == 18
    upserted_types = {c["payload"]["action_type"] for c in fake._upsert_calls}
    assert "copy_variant" not in upserted_types
    assert "send_timing" not in upserted_types


def test_dry_run_does_not_write() -> None:
    fake = FakeSupabase()
    summary = seed_autonomy_rules(fake, client_id="c1", dry_run=True)

    # Dry-run classifies all 20 as "would create"
    assert summary == {"created": 20, "skipped": 0, "errors": 0}
    # But no writes happened
    assert fake._upsert_calls == []


def test_main_missing_env_exits_1(monkeypatch: pytest.MonkeyPatch,
                                  capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    rc = main(["--client-id=foo"])

    assert rc == 1
    captured = capsys.readouterr()
    assert "SUPABASE_URL" in captured.err


def test_main_uses_injected_client(monkeypatch: pytest.MonkeyPatch,
                                    capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")

    fake = FakeSupabase()
    import scripts.seed_autonomy_rules as mod
    monkeypatch.setattr(mod, "_build_client", lambda url, key: fake)

    rc = main(["--client-id=c1", "--dry-run"])

    assert rc == 0
    captured = capsys.readouterr()
    assert "20 created" in captured.out
