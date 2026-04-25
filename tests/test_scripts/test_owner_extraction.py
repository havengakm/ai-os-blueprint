"""Tests for scripts/_owner_extraction.py.

Exercises:
  - early-return when website_text is empty (saves a Haiku call).
  - JSON parsing (happy path + code-fence + malformed).
  - category_match safety net (is_match=true forced to false when
    Claude's own reasoning contradicts it).
  - domain filtering (bad hosts collapsed to None).

Anthropic client is always mocked — no real API calls.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts._owner_extraction import (  # noqa: E402
    OwnerExtractionResult,
    _parse_claude_json,
    extract_owner_with_haiku,
)


# ── Fakes ─────────────────────────────────────────────────────────────────────

@dataclass
class _FakeBlock:
    type: str = "text"
    text: str = ""


@dataclass
class _FakeResp:
    content: list[Any] = field(default_factory=list)


class _FakeMessages:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.last_model: str | None = None
        self.last_user_content: str | None = None

    def create(self, *, model, max_tokens, system, messages):
        self.last_model = model
        self.last_user_content = messages[0]["content"]
        return _FakeResp(content=[_FakeBlock(text=self.response_text)])


class _FakeClient:
    def __init__(self, response_text: str):
        self.messages = _FakeMessages(response_text)


# ── _parse_claude_json ───────────────────────────────────────────────────────

def test_parse_claude_json_plain():
    assert _parse_claude_json('{"a": 1}') == {"a": 1}


def test_parse_claude_json_with_json_fence():
    assert _parse_claude_json("```json\n{\"x\": 2}\n```") == {"x": 2}


def test_parse_claude_json_with_plain_fence():
    assert _parse_claude_json("```\n{\"y\": 3}\n```") == {"y": 3}


def test_parse_claude_json_malformed_returns_none():
    assert _parse_claude_json("not json at all") is None


# ── extract_owner_with_haiku ─────────────────────────────────────────────────

def test_extract_empty_text_skips_claude_call():
    """When website_text is empty we must not pay for a hopeless call."""
    client = _FakeClient("{}")
    out = extract_owner_with_haiku(
        client=client,
        studio_name="Foo Studio",
        website_text="",
        category_filter="pilates studio",
        known_domain="foostudio.com",
    )
    assert isinstance(out, OwnerExtractionResult)
    assert out.first_name is None
    assert out.domain == "foostudio.com"
    assert out.is_match is False
    # Critical: the fake client was not invoked.
    assert client.messages.last_model is None


def test_extract_happy_path_returns_owner():
    fake_json = """{
        "category_reasoning": "Dedicated pilates studio — primary offering matches.",
        "is_match": true,
        "first_name": "Jane",
        "last_name": "Doe",
        "title": "Founder",
        "linkedin_url": "https://linkedin.com/in/janedoe",
        "notes": "Hiring front-desk staff.",
        "confidence": 0.9
    }"""
    client = _FakeClient(fake_json)
    out = extract_owner_with_haiku(
        client=client,
        studio_name="Pure Pilates",
        website_text="Founded by Jane Doe in 2019. We teach pilates.",
        category_filter="pilates studio",
        known_domain="purepilates.com",
    )
    assert out.first_name == "Jane"
    assert out.last_name == "Doe"
    assert out.title == "Founder"
    assert out.is_match is True
    assert out.domain == "purepilates.com"
    assert out.confidence == 0.9
    assert "Hiring" in out.notes
    # Haiku model is used, never Sonnet.
    assert client.messages.last_model == "claude-haiku-4-5-20251001"
    # Known domain passed through even when Claude returns none (here
    # it returned none — since no `domain` field).
    assert "Jane Doe" in (client.messages.last_user_content or "")


def test_extract_category_safety_net_overrides_true_to_false():
    """Claude sometimes returns is_match=true even when its own reasoning
    says the primary offering doesn't match. The post-hoc regex must
    override to false."""
    fake_json = """{
        "category_reasoning": "Ballet Austin is a professional ballet company; pilates is supplementary.",
        "is_match": true,
        "first_name": null,
        "last_name": null,
        "title": null,
        "linkedin_url": null,
        "notes": "",
        "confidence": 0.3
    }"""
    client = _FakeClient(fake_json)
    out = extract_owner_with_haiku(
        client=client,
        studio_name="Ballet Austin",
        website_text="Ballet Austin is the city's professional ballet company...",
        category_filter="pilates or yoga studio",
        known_domain="balletaustin.org",
    )
    assert out.is_match is False
    # Override reason is captured in notes for downstream audit.
    assert "overridden" in out.notes.lower()


def test_extract_bad_domain_collapses_to_none():
    """If Claude returns a directory host like google.com or linkedin.com
    as the domain, we must replace it with None (or fall back to
    known_domain)."""
    fake_json = """{
        "category_reasoning": "Yoga studio.",
        "is_match": true,
        "first_name": "Sam",
        "last_name": "Lee",
        "title": "Owner",
        "linkedin_url": null,
        "notes": "",
        "confidence": 0.8,
        "domain": "facebook.com"
    }"""
    client = _FakeClient(fake_json)
    out = extract_owner_with_haiku(
        client=client,
        studio_name="Sam's Yoga",
        website_text="Owned by Sam Lee. Yoga and meditation.",
        category_filter="yoga studio",
        known_domain=None,
    )
    # Claude-provided bad domain collapsed. No known_domain fallback → None.
    assert out.domain is None


def test_extract_malformed_json_returns_safe_defaults():
    """When Claude produces unparseable output we must not crash — we
    must return a result with all fields None/safe so the orchestrator
    can skip this contact without losing its place in the queue."""
    client = _FakeClient("this is not json")
    out = extract_owner_with_haiku(
        client=client,
        studio_name="Broken Studio",
        website_text="Some body text.",
        category_filter="pilates studio",
        known_domain="broken.com",
    )
    assert out.first_name is None
    assert out.last_name is None
    assert out.is_match is True  # default; safety net catches contradictions
    # Domain falls back to known_domain since Claude returned nothing usable.
    assert out.domain == "broken.com"
