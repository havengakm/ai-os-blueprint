"""Tests for scripts/load_context.py.

Verifies the two-pass Obsidian-backlink resolver: Pass 1 inserts all rows
without related-id arrays; Pass 2 populates them from resolved [[tokens]];
unresolved links land in data/reports/load_context_unresolved_links-*.log.
"""
from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.load_context import (  # noqa: E402
    _extract_backlinks,
    _strip_brackets,
    load_context,
)


# ── Fake Supabase ────────────────────────────────────────────────────────────

@dataclass
class _FakeResult:
    data: list[dict[str, Any]] = field(default_factory=list)


class _Query:
    def __init__(self, parent: "FakeSupabase", table_name: str) -> None:
        self._parent = parent
        self._table = table_name
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None
        self._on_conflict: str | None = None
        self._select_cols: str | None = None
        self._filters: list[tuple[str, str, Any]] = []
        self._update_payload: dict[str, Any] | None = None

    # select chain
    def select(self, cols: str) -> "_Query":
        self._op = "select"
        self._select_cols = cols
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "eq", val))
        return self

    # upsert chain
    def upsert(self, payload: dict[str, Any], on_conflict: str | None = None) -> "_Query":
        self._op = "upsert"
        self._payload = payload
        self._on_conflict = on_conflict
        return self

    # update chain
    def update(self, payload: dict[str, Any]) -> "_Query":
        self._op = "update"
        self._update_payload = payload
        return self

    def execute(self) -> _FakeResult:
        if self._op == "select":
            rows = self._parent._tables.get(self._table, [])
            for col, op, val in self._filters:
                if op == "eq":
                    rows = [r for r in rows if r.get(col) == val]
            return _FakeResult(data=list(rows))

        if self._op == "upsert":
            assert self._payload is not None
            rows = self._parent._tables.setdefault(self._table, [])
            key_fields = (self._on_conflict or "id").split(",")
            match = None
            for r in rows:
                if all(r.get(k) == self._payload.get(k) for k in key_fields):
                    match = r
                    break
            if match is not None:
                match.update(self._payload)
                returned = match
            else:
                new = dict(self._payload)
                new.setdefault("id", str(uuid.uuid4()))
                rows.append(new)
                returned = new
            self._parent._upsert_calls.append({
                "table": self._table,
                "payload": self._payload,
                "on_conflict": self._on_conflict,
                "returned_id": returned.get("id"),
            })
            return _FakeResult(data=[returned])

        if self._op == "update":
            assert self._update_payload is not None
            rows = self._parent._tables.get(self._table, [])
            for col, op, val in self._filters:
                if op == "eq":
                    rows = [r for r in rows if r.get(col) == val]
            for r in rows:
                r.update(self._update_payload)
            self._parent._update_calls.append({
                "table": self._table,
                "filters": self._filters,
                "payload": self._update_payload,
            })
            return _FakeResult(data=list(rows))

        raise RuntimeError(f"Unknown op: {self._op}")


class FakeSupabase:
    def __init__(self, seed: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = seed or {}
        self._upsert_calls: list[dict[str, Any]] = []
        self._update_calls: list[dict[str, Any]] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.1] * 1024


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ── Unit tests for bracket helpers ───────────────────────────────────────────

def test_extract_backlinks_basic() -> None:
    text = "Kirsten learned the [[AIDA]] approach from [[Nick Saraev]]."
    assert _extract_backlinks(text) == ["AIDA", "Nick Saraev"]


def test_extract_backlinks_dedupes_preserve_order() -> None:
    text = "See [[Nick Saraev]] and [[AIDA]]. Also [[Nick Saraev]] again."
    assert _extract_backlinks(text) == ["Nick Saraev", "AIDA"]


def test_extract_backlinks_with_alias() -> None:
    text = "Ask [[Nick Saraev|Nick]] about it."
    # The target is Nick Saraev, not the alias.
    assert _extract_backlinks(text) == ["Nick Saraev"]


def test_strip_brackets_preserves_name() -> None:
    text = "Kirsten learned from [[Nick Saraev]]."
    assert _strip_brackets(text) == "Kirsten learned from Nick Saraev."


def test_strip_brackets_alias_wins() -> None:
    text = "Ask [[Nick Saraev|Nick]] for it."
    assert _strip_brackets(text) == "Ask Nick for it."


def test_extract_backlinks_none_in_plain_text() -> None:
    assert _extract_backlinks("No brackets here.") == []


# ── Integration tests: two-pass load ─────────────────────────────────────────

async def test_pass1_inserts_all_then_pass2_populates_related(tmp_path: Path) -> None:
    _write(tmp_path / "nick.md",
           "---\ntitle: Nick Saraev\n---\nFounder of Procedure. Cold email frameworks.\n")
    _write(tmp_path / "aida.md",
           "---\ntitle: AIDA\n---\nAttention, Interest, Desire, Action.\n")
    _write(tmp_path / "kirsten.md",
           "---\ntitle: Kirsten\n---\n"
           "Kirsten learned from [[Nick Saraev]] and uses [[AIDA]] daily.\n")

    fake_sb = FakeSupabase()
    fake_emb = FakeEmbedder()
    reports_dir = tmp_path / "_reports"

    summary = await load_context(
        supabase=fake_sb, embedder=fake_emb,
        root=tmp_path, client_id="c1", reports_dir=reports_dir,
    )

    assert summary["loaded"] == 3
    assert summary["errors"] == 0
    assert summary["skipped"] == 0
    assert summary["resolved_links"] == 2
    assert summary["unresolved_links"] == 0
    assert summary["unresolved_log_path"] is None

    # Pass 1 upserts never included related_* arrays
    for call in fake_sb._upsert_calls:
        assert "related_context_ids" not in call["payload"]
        assert "related_fact_ids" not in call["payload"]

    # Pass 2 wrote one update (for kirsten.md)
    assert len(fake_sb._update_calls) == 1
    upd = fake_sb._update_calls[0]
    assert upd["table"] == "business_context"
    assert len(upd["payload"]["related_context_ids"]) == 2

    # Bodies were stripped of brackets (stored as plain text).
    rows = fake_sb._tables["business_context"]
    kirsten_row = next(r for r in rows if r["title"] == "Kirsten")
    assert "[[" not in kirsten_row["body"]
    assert "Nick Saraev" in kirsten_row["body"]
    assert "AIDA" in kirsten_row["body"]


async def test_unresolved_backlink_logged(tmp_path: Path) -> None:
    _write(tmp_path / "kirsten.md",
           "---\ntitle: Kirsten\n---\n"
           "She references [[Missing Entity]] which doesn't exist.\n")

    fake_sb = FakeSupabase()
    fake_emb = FakeEmbedder()
    reports_dir = tmp_path / "_reports"

    summary = await load_context(
        supabase=fake_sb, embedder=fake_emb,
        root=tmp_path, client_id="c1", reports_dir=reports_dir,
    )

    assert summary["unresolved_links"] == 1
    assert summary["resolved_links"] == 0
    assert summary["unresolved_log_path"] is not None

    log_content = summary["unresolved_log_path"].read_text()
    assert "Missing Entity" in log_content
    assert "kirsten.md" in log_content


async def test_resolves_to_client_facts_too(tmp_path: Path) -> None:
    """A [[token]] matching a client_facts.key resolves into related_fact_ids."""
    _write(tmp_path / "kirsten.md",
           "---\ntitle: Kirsten\n---\nUses the [[preferred_tool_stack]] daily.\n")

    fake_sb = FakeSupabase(seed={
        "client_facts": [
            {"id": "fact-1", "client_id": "c1", "key": "preferred_tool_stack",
             "value": {"tools": ["claude", "supabase"]}},
        ],
    })
    fake_emb = FakeEmbedder()
    reports_dir = tmp_path / "_reports"

    summary = await load_context(
        supabase=fake_sb, embedder=fake_emb,
        root=tmp_path, client_id="c1", reports_dir=reports_dir,
    )

    assert summary["resolved_links"] == 1
    assert summary["unresolved_links"] == 0
    assert len(fake_sb._update_calls) == 1
    upd = fake_sb._update_calls[0]
    assert upd["payload"]["related_fact_ids"] == ["fact-1"]
    assert "related_context_ids" not in upd["payload"]


async def test_no_backlinks_no_updates(tmp_path: Path) -> None:
    _write(tmp_path / "plain.md", "---\ntitle: Plain\n---\nNo brackets here.\n")

    fake_sb = FakeSupabase()
    summary = await load_context(
        supabase=fake_sb, embedder=FakeEmbedder(),
        root=tmp_path, client_id="c1", reports_dir=tmp_path / "_reports",
    )

    assert summary["loaded"] == 1
    assert summary["resolved_links"] == 0
    assert summary["unresolved_links"] == 0
    assert len(fake_sb._upsert_calls) == 1
    assert len(fake_sb._update_calls) == 0


async def test_dry_run_no_writes(tmp_path: Path) -> None:
    _write(tmp_path / "nick.md", "---\ntitle: Nick Saraev\n---\nBody.\n")
    _write(tmp_path / "k.md",
           "---\ntitle: Kirsten\n---\nLearned from [[Nick Saraev]] and [[Missing]].\n")

    fake_sb = FakeSupabase()
    fake_emb = FakeEmbedder()
    reports_dir = tmp_path / "_reports"

    summary = await load_context(
        supabase=fake_sb, embedder=fake_emb,
        root=tmp_path, client_id="c1", dry_run=True, reports_dir=reports_dir,
    )

    assert summary["loaded"] == 2
    assert summary["resolved_links"] == 1
    assert summary["unresolved_links"] == 1
    # No writes at all (upserts, updates, embeds)
    assert fake_sb._upsert_calls == []
    assert fake_sb._update_calls == []
    assert fake_emb.calls == []
    # And NO log file written on disk.
    assert summary["unresolved_log_path"] is None
    assert not reports_dir.exists()


async def test_empty_directory_handled_gracefully(tmp_path: Path) -> None:
    fake_sb = FakeSupabase()
    summary = await load_context(
        supabase=fake_sb, embedder=FakeEmbedder(),
        root=tmp_path, client_id="c1", reports_dir=tmp_path / "_reports",
    )

    assert summary == {
        "loaded": 0, "skipped": 0, "errors": 0,
        "resolved_links": 0, "unresolved_links": 0,
        "unresolved_log_path": None,
    }


async def test_missing_title_is_skipped(tmp_path: Path) -> None:
    _write(tmp_path / "no_title.md", "---\nsection_metadata: {}\n---\nbody\n")
    _write(tmp_path / "ok.md", "---\ntitle: OK\n---\nbody\n")

    fake_sb = FakeSupabase()
    summary = await load_context(
        supabase=fake_sb, embedder=FakeEmbedder(),
        root=tmp_path, client_id="c1", reports_dir=tmp_path / "_reports",
    )
    assert summary["loaded"] == 1
    assert summary["skipped"] == 1


async def test_backlink_to_other_context_file_resolves_across_files(tmp_path: Path) -> None:
    """Walk order matters: file A references file B, B references A. Both
    upsert in Pass 1, Pass 2 resolves both directions."""
    _write(tmp_path / "a.md", "---\ntitle: Alpha\n---\nRefers to [[Beta]].\n")
    _write(tmp_path / "b.md", "---\ntitle: Beta\n---\nRefers to [[Alpha]].\n")

    fake_sb = FakeSupabase()
    summary = await load_context(
        supabase=fake_sb, embedder=FakeEmbedder(),
        root=tmp_path, client_id="c1", reports_dir=tmp_path / "_reports",
    )

    assert summary["loaded"] == 2
    assert summary["resolved_links"] == 2
    assert summary["unresolved_links"] == 0
    assert len(fake_sb._update_calls) == 2
