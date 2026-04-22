"""Tests for scripts._lib.markdown_loader."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Put the repo root on sys.path so `scripts._lib` resolves. The repo's `os/`
# package shadowing means we can't rely on pytest rootdir's default resolution.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts._lib.markdown_loader import parse_markdown, walk_markdown  # noqa: E402


def test_parse_valid_frontmatter(tmp_path: Path) -> None:
    f = tmp_path / "sample.md"
    f.write_text(
        "---\n"
        "title: Test Doc\n"
        "tags: [a, b, c]\n"
        "---\n"
        "\n"
        "Body text here.\n"
    )
    doc = parse_markdown(f)
    assert doc is not None
    assert doc.frontmatter == {"title": "Test Doc", "tags": ["a", "b", "c"]}
    assert doc.body == "Body text here."
    assert doc.path == f


def test_parse_malformed_frontmatter_raises(tmp_path: Path) -> None:
    f = tmp_path / "bad.md"
    f.write_text(
        "---\n"
        "title: [unclosed list\n"
        "---\n"
        "body\n"
    )
    with pytest.raises(ValueError):
        parse_markdown(f)


def test_parse_frontmatter_no_closing_delim_raises(tmp_path: Path) -> None:
    f = tmp_path / "bad2.md"
    f.write_text("---\ntitle: forever\nbody goes on but no closing delim\n")
    with pytest.raises(ValueError):
        parse_markdown(f)


def test_parse_no_frontmatter_returns_empty_dict(tmp_path: Path) -> None:
    f = tmp_path / "plain.md"
    f.write_text("# Heading\n\nBody text with no frontmatter.\n")
    doc = parse_markdown(f)
    assert doc is not None
    assert doc.frontmatter == {}
    assert doc.body.startswith("# Heading")


def test_parse_empty_frontmatter_returns_empty_dict(tmp_path: Path) -> None:
    f = tmp_path / "empty_fm.md"
    f.write_text("---\n---\nBody.\n")
    doc = parse_markdown(f)
    assert doc is not None
    assert doc.frontmatter == {}
    assert doc.body == "Body."


def test_parse_frontmatter_must_be_mapping(tmp_path: Path) -> None:
    f = tmp_path / "list_fm.md"
    f.write_text("---\n- item1\n- item2\n---\nbody\n")
    with pytest.raises(ValueError):
        parse_markdown(f)


def test_parse_unreadable_file_returns_none(tmp_path: Path) -> None:
    f = tmp_path / "no_read.md"
    f.write_text("content\n")
    os.chmod(f, 0o000)
    try:
        doc = parse_markdown(f)
        assert doc is None
    finally:
        os.chmod(f, 0o644)  # restore so tmp_path cleanup works


def test_walk_returns_sorted(tmp_path: Path) -> None:
    (tmp_path / "c.md").write_text("c")
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "b.md").write_text("b")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "d.md").write_text("d")
    paths = walk_markdown(tmp_path)
    names = [p.name for p in paths]
    assert names == sorted(names)
    assert len(paths) == 4


def test_walk_nonexistent_dir_returns_empty(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    assert walk_markdown(missing) == []


def test_walk_empty_dir_returns_empty(tmp_path: Path) -> None:
    assert walk_markdown(tmp_path) == []
