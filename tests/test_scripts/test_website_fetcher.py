"""Tests for scripts/_website_fetcher.py pure-function helpers. Live
Playwright fetches are out of scope — the orchestration is exercised
by the integration path in scrape_mindbody / scrape_google_maps."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts._website_fetcher import (  # noqa: E402
    DEFAULT_PATHS,
    _build_url,
    strip_noise,
)


# ── strip_noise ──────────────────────────────────────────────────────────────

def test_strip_noise_removes_copyright():
    out = strip_noise("Our mission is blah.\n© 2024 ACME Ltd. All rights reserved.")
    assert "©" not in out
    assert "Our mission" in out


def test_strip_noise_removes_newsletter_cta():
    text = (
        "Join our community. Subscribe to our newsletter for updates! "
        "Enter your email below."
    )
    out = strip_noise(text)
    assert "newsletter" not in out.lower()
    assert "enter your email" not in out.lower()
    assert "Join our community" in out


def test_strip_noise_collapses_whitespace():
    assert strip_noise("foo   bar") == "foo bar"
    assert strip_noise("a\n\n\n\nb") == "a\n\nb"


def test_strip_noise_empty_safe():
    assert strip_noise("") == ""
    assert strip_noise("   ") == ""


def test_strip_noise_preserves_body_text():
    body = (
        "Our studio was founded by Jane Doe in 2019. "
        "We run daily yoga and pilates classes."
    )
    assert strip_noise(body) == body


# ── _build_url ───────────────────────────────────────────────────────────────

def test_build_url_empty_path_returns_domain():
    assert _build_url("example.com", "") == "https://example.com"


def test_build_url_with_path_no_leading_slash():
    assert _build_url("example.com", "about") == "https://example.com/about"


def test_build_url_with_leading_slash_stripped():
    assert _build_url("example.com", "/team") == "https://example.com/team"


def test_build_url_respects_https_scheme_already_present():
    assert _build_url("https://example.com", "about") == "https://example.com/about"


def test_build_url_respects_http_scheme():
    assert _build_url("http://example.com", "") == "http://example.com"


def test_build_url_strips_trailing_slash_on_domain():
    assert _build_url("example.com/", "about") == "https://example.com/about"


# ── DEFAULT_PATHS ────────────────────────────────────────────────────────────

def test_default_paths_ordered_home_first():
    # Home page is first so we short-circuit when the home page already
    # has an "Our Founder" teaser, before burning fetches on about/team.
    assert DEFAULT_PATHS[0] == ""


def test_default_paths_covers_common_layouts():
    # Minimum coverage: about + team + contact are always in the list.
    paths = set(DEFAULT_PATHS)
    assert "about" in paths
    assert "team" in paths
    assert "contact" in paths
