"""Tests for scripts/ingest_clutch_corpus.py."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.ingest_clutch_corpus import (  # noqa: E402
    DEFAULT_ICP_SCORE,
    DEFAULT_ICP_TIER,
    SOURCE_NAME,
    _parse_employee_band,
    _row_to_contact,
    ingest_corpus,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_row() -> dict[str, str]:
    """One representative scraper CSV row (Wildish & Co.-style, with content)."""
    return {
        "company_name": "Wildish & Co.",
        "website": "https://www.wildishandco.co.uk",
        "domain": "www.wildishandco.co.uk",
        "location": "London, England",
        "timezone": "UK_EU_ZA",
        "niche": "creative_branding",
        "employee_count": "10 - 49",
        "min_budget": "$25,000+",
        "hourly_rate": "$100 - $149 / hr",
        "rating": "4.9",
        "review_count": "4942",
        "services": "50% Branding, 20% Advertising, 20% Web Design",
        "sources": "clutch",
        "meta_title": "Creative Agency, London | Wildish & Co.",
        "meta_description": "The creative agency in London",
        "linkedin": "https://www.linkedin.com/company/wildish",
        "emails_found": "hello@wildishandco.co.uk, jobs@wildishandco.co.uk",
        "best_email": "hello@wildishandco.co.uk",
        "homepage_text": "Creative Agency, London | Wildish & Co.",
        "about_text": "Wildish & Co. is an independent creative agency.",
        "portfolio_text": "",
        "testimonials_text": "",
        "services_text": "Work That Worked. We help ambitious brands.",
        "clutch_url": "https://clutch.co/profile/wildish-co",
        "designrush_url": "",
    }


# ── _parse_employee_band ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2 - 9", 5),
        ("10 - 49", 29),
        ("50 - 249", 149),
        ("250 - 999", 624),
        ("1,000 - 9,999", 5499),
        ("10,000+", 10000),
        ("", None),
        (None, None),
        ("not a range", None),
        ("  50 - 249  ", 149),  # whitespace-tolerant
    ],
)
def test_parse_employee_band(raw: str | None, expected: int | None) -> None:
    assert _parse_employee_band(raw) == expected


# ── _row_to_contact ───────────────────────────────────────────────────────────

def test_row_maps_direct_columns(sample_row: dict[str, str]) -> None:
    payload = _row_to_contact(
        sample_row,
        client_id="c1",
        niche="cro_growth_ugc_agency",
        offer_label="pipeline_audit",
    )
    assert payload is not None
    assert payload["client_id"] == "c1"
    assert payload["source"] == SOURCE_NAME
    assert payload["source_id"] == "www.wildishandco.co.uk"
    assert payload["niche"] == "cro_growth_ugc_agency"
    assert payload["company"] == "Wildish & Co."
    assert payload["company_domain"] == "www.wildishandco.co.uk"
    assert payload["email"] == "hello@wildishandco.co.uk"
    assert payload["linkedin_url"] == "https://www.linkedin.com/company/wildish"
    assert payload["employees"] == 29  # "10 - 49"
    assert payload["timezone"] == "UK_EU_ZA"
    assert payload["status"] == "enriched"
    assert payload["icp_score"] == DEFAULT_ICP_SCORE
    assert payload["icp_tier"] == DEFAULT_ICP_TIER
    assert "enriched_at" in payload


def test_row_missing_domain_returns_none(sample_row: dict[str, str]) -> None:
    sample_row["domain"] = ""
    assert _row_to_contact(
        sample_row, client_id="c1", niche="x", offer_label="y",
    ) is None


def test_row_missing_company_returns_none(sample_row: dict[str, str]) -> None:
    sample_row["company_name"] = "   "
    assert _row_to_contact(
        sample_row, client_id="c1", niche="x", offer_label="y",
    ) is None


def test_research_data_website_content(sample_row: dict[str, str]) -> None:
    payload = _row_to_contact(
        sample_row, client_id="c1", niche="n", offer_label="o",
    )
    assert payload is not None
    wc = payload["research_data"]["website_content"]
    assert wc["homepage_text"] == "Creative Agency, London | Wildish & Co."
    assert wc["about_text"] == "Wildish & Co. is an independent creative agency."
    assert wc["services_text"] == "Work That Worked. We help ambitious brands."
    assert wc["testimonials_text"] == ""
    assert wc["portfolio_text"] == ""


def test_research_data_clutch_metadata(sample_row: dict[str, str]) -> None:
    payload = _row_to_contact(
        sample_row, client_id="c1", niche="n", offer_label="o",
    )
    assert payload is not None
    meta = payload["research_data"]["clutch_metadata"]
    assert meta["rating"] == "4.9"
    assert meta["review_count"] == "4942"
    assert meta["hourly_rate"] == "$100 - $149 / hr"
    assert meta["min_budget"] == "$25,000+"
    assert meta["location"] == "London, England"
    assert meta["website"] == "https://www.wildishandco.co.uk"


def test_empty_best_email_becomes_none(sample_row: dict[str, str]) -> None:
    sample_row["best_email"] = ""
    payload = _row_to_contact(
        sample_row, client_id="c1", niche="n", offer_label="o",
    )
    assert payload is not None
    assert payload["email"] is None  # not empty string


def test_offer_label_threads_into_research_data(sample_row: dict[str, str]) -> None:
    payload = _row_to_contact(
        sample_row, client_id="c1", niche="n", offer_label="custom_offer_xyz",
    )
    assert payload is not None
    assert payload["research_data"]["offer_label"] == "custom_offer_xyz"
    assert payload["research_data"]["key_pain_point"] is None
    assert payload["research_data"]["citable_details"] == []


def test_raw_data_contains_urls_and_meta(sample_row: dict[str, str]) -> None:
    payload = _row_to_contact(
        sample_row, client_id="c1", niche="n", offer_label="o",
    )
    assert payload is not None
    raw = payload["raw_data"]
    assert raw["clutch_url"] == "https://clutch.co/profile/wildish-co"
    assert raw["sources"] == "clutch"
    assert raw["meta_title"] == "Creative Agency, London | Wildish & Co."


# ── ingest_corpus: dry-run + skip accounting ─────────────────────────────────

class _FakeQuery:
    def __init__(self, parent: "_FakeSupabase") -> None:
        self._parent = parent
        self._payload: dict[str, Any] | None = None
        self._on_conflict: str | None = None

    def upsert(self, payload: dict[str, Any], on_conflict: str | None = None) -> "_FakeQuery":
        self._payload = payload
        self._on_conflict = on_conflict
        return self

    def execute(self) -> Any:
        assert self._payload is not None
        self._parent.upsert_calls.append(
            {"payload": self._payload, "on_conflict": self._on_conflict}
        )

        class _R:
            data = [self._payload] if False else [self._payload]  # placeholder

        _R.data = [self._payload]
        return _R()


class _FakeSupabase:
    def __init__(self) -> None:
        self.upsert_calls: list[dict[str, Any]] = []

    def table(self, name: str) -> _FakeQuery:
        assert name == "contacts"
        return _FakeQuery(self)


def test_ingest_corpus_dry_run_no_writes(sample_row: dict[str, str]) -> None:
    fake = _FakeSupabase()
    rows = [sample_row, dict(sample_row, domain="", company_name="NoDomain Inc.")]
    summary = ingest_corpus(
        fake, rows, client_id="c1", niche="n", offer_label="o", dry_run=True,
    )
    assert summary == {"loaded": 1, "skipped": 1, "errors": 0}
    assert fake.upsert_calls == []


def test_ingest_corpus_writes_when_not_dry_run(sample_row: dict[str, str]) -> None:
    fake = _FakeSupabase()
    summary = ingest_corpus(
        fake, [sample_row], client_id="c1", niche="n", offer_label="o",
    )
    assert summary == {"loaded": 1, "skipped": 0, "errors": 0}
    assert len(fake.upsert_calls) == 1
    call = fake.upsert_calls[0]
    assert call["on_conflict"] == "client_id,source,source_id"
    assert call["payload"]["source_id"] == "www.wildishandco.co.uk"
