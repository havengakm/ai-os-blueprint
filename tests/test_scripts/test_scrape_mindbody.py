"""Tests for scripts/scrape_mindbody.py.

Scope: pure functions only. No live Mindbody, no Claude API. The directory
parser is tested against a fixture HTML snippet modelled on the real
Mindbody markup. Row-builder + validator are tested on hand-crafted dicts.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.scrape_mindbody import (  # noqa: E402
    CSV_FIELDNAMES,
    _parse_claude_json,
    build_row,
    email_from_owner,
    fallback_email,
    normalise_domain,
    parse_directory_studios,
    short_name_from_company,
    validate_row,
)


# ── parse_directory_studios ──────────────────────────────────────────────────

_FIXTURE_DIRECTORY_HTML = """
<html><body>
  <main>
    <ul class="studios">
      <li>
        <a href="/explore/locations/one-flow-yoga-and-wellness">One Flow Yoga and Wellness</a>
      </li>
      <li>
        <a href="/explore/locations/yoga-life-cape-town-wc">Yoga Life Cape Town</a>
      </li>
      <li>
        <!-- duplicate; should be deduped -->
        <a href="/explore/locations/yoga-life-cape-town-wc">Yoga Life (duplicate)</a>
      </li>
      <li>
        <a href="/explore/locations/sweat1000-cape-town">Sweat1000 Cape Town</a>
      </li>
    </ul>
    <!-- unrelated anchor that should NOT be captured -->
    <a href="/explore/fitness/studios-johannesburg-gp-za">Johannesburg</a>
  </main>
</body></html>
"""


def test_parse_directory_studios_extracts_unique_slugs() -> None:
    studios = parse_directory_studios(_FIXTURE_DIRECTORY_HTML)
    slugs = [s["slug"] for s in studios]
    assert slugs == [
        "one-flow-yoga-and-wellness",
        "yoga-life-cape-town-wc",
        "sweat1000-cape-town",
    ]


def test_parse_directory_studios_returns_absolute_mindbody_urls() -> None:
    studios = parse_directory_studios(_FIXTURE_DIRECTORY_HTML)
    for s in studios:
        assert s["mindbody_url"].startswith(
            "https://www.mindbodyonline.com/explore/locations/"
        )


def test_parse_directory_studios_handles_empty_html() -> None:
    assert parse_directory_studios("") == []
    assert parse_directory_studios("<html></html>") == []


# ── normalise_domain ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("https://www.example.co.za/about", "example.co.za"),
    ("http://example.co.za", "example.co.za"),
    ("www.example.co.za", "example.co.za"),
    ("example.co.za", "example.co.za"),
    ("https://example.co.za/", "example.co.za"),
    ("", None),
    (None, None),
    ("   ", None),
])
def test_normalise_domain(raw: str | None, expected: str | None) -> None:
    assert normalise_domain(raw) == expected


# ── short_name_from_company ──────────────────────────────────────────────────

@pytest.mark.parametrize("company, expected", [
    ("Sweat1000 (Pty) Ltd", "Sweat1000"),
    ("Yoga Life Pty Ltd", "Yoga Life"),
    ("One Flow Yoga and Wellness", "One Flow Yoga and Wellness"),
    ("The Local Studio CC", "The Local Studio"),
    ("Fit Inc.", "Fit"),
])
def test_short_name_strips_legal_suffixes(company: str, expected: str) -> None:
    assert short_name_from_company(company) == expected


# ── email_from_owner / fallback_email ────────────────────────────────────────

def test_email_from_owner_happy_path() -> None:
    assert email_from_owner("Jane", "example.co.za") == "jane@example.co.za"


def test_email_from_owner_strips_non_alpha() -> None:
    assert email_from_owner("Jean-Pierre", "example.co.za") == "jeanpierre@example.co.za"


def test_email_from_owner_blank_inputs() -> None:
    assert email_from_owner(None, "example.co.za") is None
    assert email_from_owner("", "example.co.za") is None
    assert email_from_owner("Jane", None) is None


def test_fallback_email() -> None:
    assert fallback_email("example.co.za") == "info@example.co.za"
    assert fallback_email(None) is None


# ── _parse_claude_json ───────────────────────────────────────────────────────

def test_parse_claude_json_clean_json() -> None:
    parsed = _parse_claude_json('{"domain": "x.co.za", "first_name": "Jane"}')
    assert parsed == {"domain": "x.co.za", "first_name": "Jane"}


def test_parse_claude_json_strips_code_fences() -> None:
    raw = '```json\n{"domain": "x.co.za"}\n```'
    assert _parse_claude_json(raw) == {"domain": "x.co.za"}


def test_parse_claude_json_returns_none_on_junk() -> None:
    assert _parse_claude_json("not json at all") is None


# ── build_row ────────────────────────────────────────────────────────────────

def _resolved(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "domain": "oneflow.co.za",
        "first_name": "Jane",
        "last_name": "Doe",
        "title": "Founder",
        "linkedin_url": "https://za.linkedin.com/in/jane-doe",
        "notes": "Opened second studio Feb 2026.",
        "confidence": 0.8,
    }
    base.update(overrides)
    return base


def test_build_row_named_owner_uses_firstname_at_domain() -> None:
    row = build_row(
        studio_name="One Flow Yoga",
        mindbody_url="https://www.mindbodyonline.com/explore/locations/one-flow",
        resolved=_resolved(),
        city="Cape Town",
        niche="fitness_wellness",
    )
    assert row is not None
    assert row["email"] == "jane@oneflow.co.za"
    assert row["first_name"] == "Jane"
    assert row["last_name"] == "Doe"
    assert row["title"] == "Founder"
    assert row["niche"] == "fitness_wellness"
    assert row["short_company_name"] == "One Flow Yoga"
    assert "Cape Town" in row["notes"]
    assert "Opened second studio Feb 2026." in row["notes"]


def test_build_row_no_owner_falls_back_to_info_with_placeholder_first_name() -> None:
    row = build_row(
        studio_name="Mystery Studio",
        mindbody_url="https://www.mindbodyonline.com/explore/locations/mystery",
        resolved=_resolved(
            first_name=None, last_name=None, title=None, linkedin_url=None,
        ),
        city="Cape Town",
        niche="fitness_wellness",
    )
    assert row is not None
    assert row["email"] == "info@oneflow.co.za"
    # Placeholder first_name is required because the ingester rejects rows
    # with blank first_name.
    assert row["first_name"] == "Owner"
    assert "generic info@" in row["notes"]


def test_build_row_returns_none_without_domain() -> None:
    row = build_row(
        studio_name="Domainless",
        mindbody_url="https://www.mindbodyonline.com/explore/locations/x",
        resolved=_resolved(domain=None),
        city="Cape Town",
        niche="fitness_wellness",
    )
    assert row is None


# ── validate_row ─────────────────────────────────────────────────────────────

def _valid_row() -> dict[str, str]:
    return {
        "company": "Sweat1000",
        "domain": "sweat1000.co.za",
        "linkedin_url": "",
        "first_name": "Paul",
        "last_name": "Iacovou",
        "title": "Founder",
        "email": "paul@sweat1000.co.za",
        "short_company_name": "Sweat1000",
        "niche": "fitness_wellness",
        "notes": "Cape Town",
    }


def test_validate_row_accepts_happy_path() -> None:
    assert validate_row(_valid_row()) == []


@pytest.mark.parametrize("missing_key", ["company", "domain", "email", "niche"])
def test_validate_row_rejects_missing_required_field(missing_key: str) -> None:
    row = _valid_row()
    row[missing_key] = ""
    missing = validate_row(row)
    assert missing_key in missing


def test_validate_row_rejects_whitespace_only() -> None:
    row = _valid_row()
    row["company"] = "   "
    assert "company" in validate_row(row)


# ── CSV_FIELDNAMES sanity ────────────────────────────────────────────────────

def test_csv_fieldnames_match_ingester_contract() -> None:
    # Keep scraper output in lockstep with ingest_preresolved_contacts.py.
    expected = [
        "company", "domain", "linkedin_url", "first_name", "last_name",
        "title", "email", "short_company_name", "niche", "notes",
    ]
    assert CSV_FIELDNAMES == expected
