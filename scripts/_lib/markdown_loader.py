"""Shared utilities for markdown-based loader scripts.

Both scripts/load_knowledge.py and scripts/load_context.py walk a tree of
markdown files with YAML frontmatter. This module provides the file-walk
and frontmatter-parsing primitives in one place.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


FRONTMATTER_DELIMITER = "---"


@dataclass
class MarkdownDoc:
    """A parsed markdown document: frontmatter (YAML dict) + body (str)."""
    path: Path
    frontmatter: dict[str, Any]
    body: str


def parse_markdown(path: Path) -> MarkdownDoc | None:
    """Parse a markdown file with optional YAML frontmatter.

    Returns:
        MarkdownDoc with frontmatter=dict (empty if none) and body=str.
        None if the file can't be read.

    Raises:
        ValueError: frontmatter is present but malformed (bad YAML, or no
                    closing delimiter).
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("Unable to read %s: %s", path, e)
        return None

    frontmatter: dict[str, Any] = {}
    body = raw

    # Only treat as frontmatter if the file starts with '---\n'. Accept a BOM.
    stripped = raw.lstrip("﻿")
    lines = stripped.splitlines(keepends=True)

    if lines and lines[0].rstrip() == FRONTMATTER_DELIMITER:
        # Find the closing delimiter.
        close_idx = None
        for i in range(1, len(lines)):
            if lines[i].rstrip() == FRONTMATTER_DELIMITER:
                close_idx = i
                break

        if close_idx is None:
            raise ValueError(
                f"{path}: frontmatter opened with '---' but no closing delimiter found"
            )

        fm_block = "".join(lines[1:close_idx])
        try:
            parsed = yaml.safe_load(fm_block)
        except yaml.YAMLError as e:
            raise ValueError(f"{path}: malformed YAML frontmatter: {e}") from e

        if parsed is None:
            frontmatter = {}
        elif isinstance(parsed, dict):
            frontmatter = parsed
        else:
            raise ValueError(
                f"{path}: frontmatter YAML must be a mapping, got {type(parsed).__name__}"
            )

        body = "".join(lines[close_idx + 1:])

    return MarkdownDoc(path=path, frontmatter=frontmatter, body=body.strip())


def walk_markdown(root: Path, pattern: str = "**/*.md") -> list[Path]:
    """Glob for markdown files under root. Returns a sorted list (deterministic).
    Returns an empty list if root does not exist."""
    if not root.exists():
        return []
    return sorted(p for p in root.glob(pattern) if p.is_file())
