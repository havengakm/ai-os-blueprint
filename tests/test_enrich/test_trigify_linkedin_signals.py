"""Slice C (2026-04-29): regression tests for the two reserved LinkedIn
intent flags emitted by TrigifyAdapter.

The flags are derived (no new HTTP) from the existing trigger_events
list. Trigify monitor config IS the topic filter — operators set up
keyword watchers on relevant topics, so a matched recent LinkedIn
event is by definition topic-relevant.

  research_data.linkedin_dm_recent_post_match  → match_key=='profile'
  research_data.linkedin_company_recent_post   → match_key in {'domain','name'}

Both gated on platform=='linkedin' AND recency_days <= LINKEDIN_RECENCY_DAYS.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from systems.scout.enrich.trigify import (
    LINKEDIN_RECENCY_DAYS,
    TrigifyAdapter,
    _has_recent_linkedin_event,
)


# --------------------------------------------------------------------------- #
# Helper unit tests — exercise _has_recent_linkedin_event directly             #
# --------------------------------------------------------------------------- #


def _ev(
    *,
    platform: str = "linkedin",
    match_key: str = "profile",
    recency_days: int | float | None = 14,
) -> dict:
    """Build a minimal trigger_event dict for the helper."""
    return {
        "platform": platform,
        "match_key": match_key,
        "recency_days": recency_days,
    }


def test_linkedin_dm_recent_fires_when_profile_match_recent():
    events = [_ev(match_key="profile", recency_days=14)]
    assert _has_recent_linkedin_event(
        events, match_keys={"profile"}, max_days=LINKEDIN_RECENCY_DAYS,
    ) is True


def test_linkedin_dm_recent_skips_old_post():
    events = [_ev(match_key="profile", recency_days=45)]
    assert _has_recent_linkedin_event(
        events, match_keys={"profile"}, max_days=LINKEDIN_RECENCY_DAYS,
    ) is False


def test_linkedin_dm_recent_skips_company_match():
    """match_key='domain' is the *company* signal, not the DM signal."""
    events = [_ev(match_key="domain", recency_days=10)]
    assert _has_recent_linkedin_event(
        events, match_keys={"profile"}, max_days=LINKEDIN_RECENCY_DAYS,
    ) is False


def test_linkedin_company_recent_fires_when_domain_match_recent():
    events = [_ev(match_key="domain", recency_days=10)]
    assert _has_recent_linkedin_event(
        events, match_keys={"domain", "name"}, max_days=LINKEDIN_RECENCY_DAYS,
    ) is True


def test_linkedin_company_recent_fires_when_name_match_recent():
    events = [_ev(match_key="name", recency_days=20)]
    assert _has_recent_linkedin_event(
        events, match_keys={"domain", "name"}, max_days=LINKEDIN_RECENCY_DAYS,
    ) is True


def test_linkedin_company_recent_skips_profile_match():
    """match_key='profile' is the DM signal, not the company signal."""
    events = [_ev(match_key="profile", recency_days=14)]
    assert _has_recent_linkedin_event(
        events, match_keys={"domain", "name"}, max_days=LINKEDIN_RECENCY_DAYS,
    ) is False


def test_both_signals_skip_non_linkedin_platform():
    """A profile match on twitter does NOT fire the LinkedIn-specific flag."""
    events = [_ev(platform="twitter", match_key="profile", recency_days=5)]
    assert _has_recent_linkedin_event(
        events, match_keys={"profile"}, max_days=LINKEDIN_RECENCY_DAYS,
    ) is False
    assert _has_recent_linkedin_event(
        events, match_keys={"domain", "name"}, max_days=LINKEDIN_RECENCY_DAYS,
    ) is False


def test_both_signals_skip_when_no_events():
    assert _has_recent_linkedin_event(
        [], match_keys={"profile"}, max_days=LINKEDIN_RECENCY_DAYS,
    ) is False
    assert _has_recent_linkedin_event(
        [], match_keys={"domain", "name"}, max_days=LINKEDIN_RECENCY_DAYS,
    ) is False


def test_helper_treats_missing_recency_as_old():
    """recency_days=None (unparseable timestamp) is treated as 'old' so we
    don't fire signals off undated content. Same conservative stance as
    score._has_recent_structural_signal."""
    events = [_ev(match_key="profile", recency_days=None)]
    assert _has_recent_linkedin_event(
        events, match_keys={"profile"}, max_days=LINKEDIN_RECENCY_DAYS,
    ) is False


def test_helper_boundary_recency_inclusive():
    """recency_days == max_days fires (<=, not <)."""
    events = [_ev(match_key="profile", recency_days=LINKEDIN_RECENCY_DAYS)]
    assert _has_recent_linkedin_event(
        events, match_keys={"profile"}, max_days=LINKEDIN_RECENCY_DAYS,
    ) is True


# --------------------------------------------------------------------------- #
# Integration test — exercise full TrigifyAdapter end-to-end                   #
# --------------------------------------------------------------------------- #


@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.setenv("TRIGIFY_API_KEY", "trig-test-key")
    from config.settings import get_settings
    get_settings.cache_clear()


def _mock_response(payload: dict):
    resp = MagicMock()
    resp.raise_for_status = MagicMock(return_value=None)
    resp.json = MagicMock(return_value=payload)
    resp.status_code = 200
    return resp


@pytest.mark.asyncio
async def test_full_adapter_emits_both_booleans_alongside_trigger_events(_env):
    """End-to-end: a recent profile-match LinkedIn event from Trigify should
    populate both `trigger_events` and `linkedin_dm_recent_post_match=True`
    in the same EnrichResult.data payload, while the company flag stays
    False (no domain/name match in this fixture)."""
    from datetime import datetime, timedelta, timezone
    recent_ts = (datetime.now(tz=timezone.utc) - timedelta(days=10)).isoformat()

    contact = {
        "contact_id": "c1",
        "linkedin_url": "https://linkedin.com/in/janedoe",
        "company_domain": "example.com",
        "company": "Example Corp",
        "trigify_search_ids": ["s1"],
    }

    payload = {
        "results": [
            {
                "id": "r1",
                "source": "linkedin",
                "author": {
                    "name": "Jane Doe",
                    "profile_url": "https://linkedin.com/in/janedoe",
                },
                "content": {"text": "We are hiring! Joining the team next month.", "url": "x"},
                "engagement": {"likes": 10, "comments": 5, "shares": 2},
                "published_at": recent_ts,
            }
        ],
        "has_more": False,
    }

    fake_http = MagicMock(spec=httpx.AsyncClient)
    fake_http.get = AsyncMock(return_value=_mock_response(payload))
    fake_http.aclose = AsyncMock(return_value=None)

    adapter = TrigifyAdapter(http_client=fake_http)
    result = await adapter.enrich(contact)

    assert result.ok is True
    assert result.reason == "behavioral_signals_found"
    # Trigger events still present (existing contract).
    assert len(result.data["trigger_events"]) == 1
    # New booleans populated.
    assert result.data["linkedin_dm_recent_post_match"] is True
    assert result.data["linkedin_company_recent_post"] is False


@pytest.mark.asyncio
async def test_full_adapter_emits_false_booleans_when_no_signals(_env):
    """No matched events → both booleans False, not absent."""
    contact = {
        "contact_id": "c1",
        "linkedin_url": "https://linkedin.com/in/janedoe",
        "company_domain": "example.com",
        "company": "Example Corp",
        "trigify_search_ids": ["s1"],
    }
    payload = {"results": [], "has_more": False}

    fake_http = MagicMock(spec=httpx.AsyncClient)
    fake_http.get = AsyncMock(return_value=_mock_response(payload))
    fake_http.aclose = AsyncMock(return_value=None)

    adapter = TrigifyAdapter(http_client=fake_http)
    result = await adapter.enrich(contact)

    assert result.ok is True
    assert result.reason == "no_signals_matched"
    assert result.data["linkedin_dm_recent_post_match"] is False
    assert result.data["linkedin_company_recent_post"] is False


