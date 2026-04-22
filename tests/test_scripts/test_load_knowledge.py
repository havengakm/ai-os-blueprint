"""Tests for scripts/load_knowledge.py."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.load_knowledge import load_knowledge  # noqa: E402


# ── Fakes ────────────────────────────────────────────────────────────────────

@dataclass
class _FakeResult:
    data: list[dict[str, Any]] = field(default_factory=list)


class _UpsertQuery:
    def __init__(self, parent: "FakeSupabase", table_name: str) -> None:
        self._parent = parent
        self._table = table_name
        self._payload: dict[str, Any] | None = None
        self._on_conflict: str | None = None

    def upsert(self, payload: dict[str, Any], on_conflict: str | None = None) -> "_UpsertQuery":
        self._payload = payload
        self._on_conflict = on_conflict
        return self

    def execute(self) -> _FakeResult:
        assert self._payload is not None
        self._parent.upserts.append({
            "table": self._table,
            "payload": self._payload,
            "on_conflict": self._on_conflict,
        })
        return _FakeResult(data=[self._payload])


class FakeSupabase:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []

    def table(self, name: str) -> _UpsertQuery:
        return _UpsertQuery(self, name)


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.0] * 1024


# ── Tests ────────────────────────────────────────────────────────────────────

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


async def test_loads_three_files(tmp_path: Path) -> None:
    _write(tmp_path / "a.md",
           "---\nsource: saraev\ncategory: framework\ntitle: AIDA\ntags: [cold]\n---\nAIDA body.\n")
    _write(tmp_path / "b.md",
           "---\nsource: hormozi\ncategory: principle\ntitle: Offer Stack\n---\nStack body.\n")
    _write(tmp_path / "sub" / "c.md",
           "---\nsource: brunson\ncategory: template\ntitle: Hook Template\n---\nHook body.\n")

    fake_sb = FakeSupabase()
    fake_emb = FakeEmbedder()

    summary = await load_knowledge(
        supabase=fake_sb, embedder=fake_emb,
        root=tmp_path, client_id="global",
    )

    assert summary == {"loaded": 3, "skipped": 0, "errors": 0}
    assert len(fake_sb.upserts) == 3
    assert len(fake_emb.calls) == 3
    for u in fake_sb.upserts:
        assert u["table"] == "knowledge_base"
        assert u["on_conflict"] == "client_id,source,title"
        assert u["payload"]["client_id"] == "global"
        assert "embedding" in u["payload"]
        assert len(u["payload"]["embedding"]) == 1024


async def test_malformed_frontmatter_counted_as_error(tmp_path: Path) -> None:
    _write(tmp_path / "good.md",
           "---\nsource: s\ncategory: framework\ntitle: t\n---\nbody\n")
    _write(tmp_path / "bad.md",
           "---\ntitle: [unclosed\n---\nbody\n")

    summary = await load_knowledge(
        supabase=FakeSupabase(), embedder=FakeEmbedder(),
        root=tmp_path, client_id="global",
    )

    assert summary["loaded"] == 1
    assert summary["errors"] == 1


async def test_missing_required_frontmatter_skipped(tmp_path: Path) -> None:
    _write(tmp_path / "no_category.md",
           "---\nsource: s\ntitle: t\n---\nbody\n")
    _write(tmp_path / "bad_category.md",
           "---\nsource: s\ncategory: not_in_enum\ntitle: t\n---\nbody\n")
    _write(tmp_path / "empty_body.md",
           "---\nsource: s\ncategory: framework\ntitle: t\n---\n")

    summary = await load_knowledge(
        supabase=FakeSupabase(), embedder=FakeEmbedder(),
        root=tmp_path, client_id="global",
    )

    assert summary == {"loaded": 0, "skipped": 3, "errors": 0}


async def test_empty_directory_no_crash(tmp_path: Path) -> None:
    summary = await load_knowledge(
        supabase=FakeSupabase(), embedder=FakeEmbedder(),
        root=tmp_path, client_id="global",
    )
    assert summary == {"loaded": 0, "skipped": 0, "errors": 0}


async def test_nonexistent_directory_no_crash(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    summary = await load_knowledge(
        supabase=FakeSupabase(), embedder=FakeEmbedder(),
        root=missing, client_id="global",
    )
    assert summary == {"loaded": 0, "skipped": 0, "errors": 0}


async def test_dry_run_does_not_write_or_embed(tmp_path: Path) -> None:
    _write(tmp_path / "a.md",
           "---\nsource: saraev\ncategory: framework\ntitle: AIDA\n---\nbody\n")

    fake_sb = FakeSupabase()
    fake_emb = FakeEmbedder()

    summary = await load_knowledge(
        supabase=fake_sb, embedder=fake_emb,
        root=tmp_path, client_id="global", dry_run=True,
    )

    assert summary["loaded"] == 1
    assert fake_sb.upserts == []
    assert fake_emb.calls == []
