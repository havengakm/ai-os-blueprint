"""Tests for Trigify behavioral-signal adapter."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from systems.scout.enrich.trigify import TrigifyAdapter
from systems.scout.enrich.base import EnrichResult


# --------------------------------------------------------------------------- #
# Fixtures                                                                      #
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


def _mock_response(payload: dict, status_code: int = 200):
    resp = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=MagicMock(status_code=status_code),
        )
    else:
        resp.raise_for_status = MagicMock(return_value=None)
    resp.json = MagicMock(return_value=payload)
    resp.status_code = status_code
    return resp


def _trigify_result(
    result_id: str = "r1",
    source: str = "linkedin",
    profile_url: str | None = None,
    text: str = "Some post content here",
    content_url: str | None = None,
    likes: int = 10,
    comments: int = 5,
    shares: int = 2,
    published_at: str | None = None,
) -> dict:
    return {
        "id": result_id,
        "source": source,
        "author": {
            "name": "Test Author",
            "username": "testauthor",
            "profile_url": profile_url,
            "followers": 1000,
            "avatar": None,
        },
        "content": {
            "text": text,
            "url": content_url,
            "media": [],
        },
        "engagement": {
            "likes": likes,
            "comments": comments,
            "shares": shares,
        },
        "published_at": published_at,
        "collected_at": "2026-04-20T10:00:00Z",
    }


def _page_response(results: list[dict], has_more: bool = False) -> dict:
    return {
        "results": results,
        "has_more": has_more,
        "next_cursor": None,
        "total_count": len(results),
    }


# --------------------------------------------------------------------------- #
# Tests                                                                         #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_trigify_matches_by_linkedin_profile(_env):
    """Profile URL match (strongest) sets match_key='profile'."""
    contact = {
        "contact_id": "c1",
        "linkedin_url": "https://linkedin.com/in/janedoe",
        "company_domain": "example.com",
        "company": "Example Corp",
        "trigify_search_ids": ["s1"],
    }
    result_item = _trigify_result(
        result_id="r1",
        source="linkedin",
        profile_url="https://linkedin.com/in/janedoe",
        text="Jane posted about growth hacking",
    )
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(_page_response([result_item]))

    adapter = TrigifyAdapter(http_client=mock_client)
    result = await adapter.enrich(contact)

    assert isinstance(result, EnrichResult)
    assert result.ok is True
    assert result.cost_cents == 0
    assert result.reason == "behavioral_signals_found"
    assert result.adapter_name == "trigify"
    assert len(result.data["trigger_events"]) == 1
    ev = result.data["trigger_events"][0]
    assert ev["match_key"] == "profile"
    assert ev["source"] == "trigify_linkedin"
    assert ev["platform"] == "linkedin"
    assert result.data["matched_count"] == 1
    assert result.data["monitors_queried"] == ["s1"]
    assert result.data["total_results_scanned"] == 1


@pytest.mark.asyncio
async def test_trigify_matches_by_company_domain(_env):
    """Domain substring in content.text sets match_key='domain'."""
    contact = {
        "contact_id": "c2",
        "linkedin_url": None,
        "company_domain": "acmecorp.com",
        "company": "Acme Corp",
        "trigify_search_ids": ["s1"],
    }
    result_item = _trigify_result(
        result_id="r2",
        profile_url=None,
        text="Big announcement from acmecorp.com leadership team",
    )
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(_page_response([result_item]))

    adapter = TrigifyAdapter(http_client=mock_client)
    result = await adapter.enrich(contact)

    assert result.ok is True
    assert result.cost_cents == 0
    assert len(result.data["trigger_events"]) == 1
    assert result.data["trigger_events"][0]["match_key"] == "domain"


@pytest.mark.asyncio
async def test_trigify_matches_by_company_name(_env):
    """Company name substring match (length >= 4) sets match_key='name'."""
    contact = {
        "contact_id": "c3",
        "linkedin_url": None,
        "company_domain": None,
        "company": "WidgetWorks",
        "trigify_search_ids": ["s1"],
    }
    result_item = _trigify_result(
        result_id="r3",
        profile_url=None,
        text="WidgetWorks just launched a new product line",
    )
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(_page_response([result_item]))

    adapter = TrigifyAdapter(http_client=mock_client)
    result = await adapter.enrich(contact)

    assert result.ok is True
    assert len(result.data["trigger_events"]) == 1
    assert result.data["trigger_events"][0]["match_key"] == "name"


@pytest.mark.asyncio
async def test_trigify_short_company_name_not_matched(_env):
    """Company name shorter than 4 chars does not trigger name match."""
    contact = {
        "contact_id": "c3b",
        "linkedin_url": None,
        "company_domain": None,
        "company": "AB",
        "trigify_search_ids": ["s1"],
    }
    result_item = _trigify_result(
        result_id="r3b",
        profile_url=None,
        text="AB is a common letter combo that appears everywhere",
    )
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(_page_response([result_item]))

    adapter = TrigifyAdapter(http_client=mock_client)
    result = await adapter.enrich(contact)

    assert result.ok is True
    assert result.reason == "no_signals_matched"
    assert result.data["trigger_events"] == []


@pytest.mark.asyncio
async def test_trigify_no_match(_env):
    """Result with no matching keys returns ok=True, reason='no_signals_matched'."""
    contact = {
        "contact_id": "c4",
        "linkedin_url": "https://linkedin.com/in/johndoe",
        "company_domain": "johncorp.com",
        "company": "John Corp",
        "trigify_search_ids": ["s1"],
    }
    result_item = _trigify_result(
        result_id="r4",
        profile_url="https://linkedin.com/in/somebodyelse",
        text="Unrelated post about something completely different",
    )
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(_page_response([result_item]))

    adapter = TrigifyAdapter(http_client=mock_client)
    result = await adapter.enrich(contact)

    assert result.ok is True
    assert result.cost_cents == 0
    assert result.reason == "no_signals_matched"
    assert result.data["trigger_events"] == []
    assert result.data["matched_count"] == 0
    assert result.data["total_results_scanned"] == 1


@pytest.mark.asyncio
async def test_trigify_aggregates_across_multiple_monitors(_env):
    """Three search_ids each returning one match → 3 events, all monitor ids present."""
    contact = {
        "contact_id": "c5",
        "linkedin_url": "https://linkedin.com/in/jane",
        "company_domain": "jane.io",
        "company": "JaneCo",
        "trigify_search_ids": ["s1", "s2", "s3"],
    }
    def _make_result(rid: str) -> dict:
        return _trigify_result(
            result_id=rid,
            profile_url="https://linkedin.com/in/jane",
            text=f"Signal from monitor {rid}",
        )

    mock_client = AsyncMock()
    mock_client.get.side_effect = [
        _mock_response(_page_response([_make_result("r_s1")])),
        _mock_response(_page_response([_make_result("r_s2")])),
        _mock_response(_page_response([_make_result("r_s3")])),
    ]

    adapter = TrigifyAdapter(http_client=mock_client)
    result = await adapter.enrich(contact)

    assert result.ok is True
    assert len(result.data["trigger_events"]) == 3
    assert result.data["monitors_queried"] == ["s1", "s2", "s3"]
    assert result.data["total_results_scanned"] == 3
    assert result.data["matched_count"] == 3
    assert mock_client.get.call_count == 3


@pytest.mark.asyncio
async def test_trigify_deduplicates_by_result_id(_env):
    """Same result id appearing in two monitor responses is deduplicated."""
    contact = {
        "contact_id": "c6",
        "linkedin_url": "https://linkedin.com/in/jane",
        "company_domain": "jane.io",
        "company": "JaneCo",
        "trigify_search_ids": ["s1", "s2"],
    }
    shared_result = _trigify_result(
        result_id="SAME_ID",
        profile_url="https://linkedin.com/in/jane",
    )
    mock_client = AsyncMock()
    mock_client.get.side_effect = [
        _mock_response(_page_response([shared_result])),
        _mock_response(_page_response([shared_result])),
    ]

    adapter = TrigifyAdapter(http_client=mock_client)
    result = await adapter.enrich(contact)

    assert result.ok is True
    assert len(result.data["trigger_events"]) == 1
    assert result.data["total_results_scanned"] == 2


@pytest.mark.asyncio
async def test_trigify_caps_at_20_events_sorted_by_engagement(_env):
    """30 matched results → capped at 20, sorted highest engagement-sum first."""
    contact = {
        "contact_id": "c7",
        "linkedin_url": "https://linkedin.com/in/jane",
        "company_domain": None,
        "company": "",
        "trigify_search_ids": ["s1"],
    }
    # Build 30 results; engagement_sum = likes + comments + shares
    # Give them varying engagement so we can check sort order
    results = [
        _trigify_result(
            result_id=f"r{i}",
            profile_url="https://linkedin.com/in/jane",
            likes=i * 10,
            comments=i * 2,
            shares=i,
        )
        for i in range(1, 31)  # i=1..30; engagement_sum = 13*i
    ]
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(_page_response(results))

    adapter = TrigifyAdapter(http_client=mock_client)
    result = await adapter.enrich(contact)

    events = result.data["trigger_events"]
    assert len(events) == 20
    # Highest engagement first: i=30 → sum=390, i=29 → 377, ...
    sums = [
        (e["engagement"]["likes"] or 0) +
        (e["engagement"]["comments"] or 0) +
        (e["engagement"]["shares"] or 0)
        for e in events
    ]
    assert sums == sorted(sums, reverse=True)
    assert sums[0] == 30 * 13  # top result is i=30


@pytest.mark.asyncio
async def test_trigify_returns_no_api_key_when_unset(monkeypatch):
    """No TRIGIFY_API_KEY → ok=False, reason='no_api_key', no network call."""
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.delenv("TRIGIFY_API_KEY", raising=False)
    from config.settings import get_settings
    get_settings.cache_clear()

    mock_client = AsyncMock()
    adapter = TrigifyAdapter(http_client=mock_client)
    result = await adapter.enrich({
        "contact_id": "c8",
        "linkedin_url": "https://linkedin.com/in/jane",
        "trigify_search_ids": ["s1"],
    })

    assert result.ok is False
    assert result.reason == "no_api_key"
    assert result.cost_cents == 0
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_trigify_returns_no_monitors_configured(_env):
    """Missing or empty trigify_search_ids → ok=False, reason='no_monitors_configured'."""
    mock_client = AsyncMock()
    adapter = TrigifyAdapter(http_client=mock_client)

    # Missing key
    result_missing = await adapter.enrich({
        "contact_id": "c9",
        "linkedin_url": "https://linkedin.com/in/jane",
    })
    assert result_missing.ok is False
    assert result_missing.reason == "no_monitors_configured"
    assert result_missing.cost_cents == 0
    mock_client.get.assert_not_called()

    # Empty list
    result_empty = await adapter.enrich({
        "contact_id": "c9",
        "linkedin_url": "https://linkedin.com/in/jane",
        "trigify_search_ids": [],
    })
    assert result_empty.ok is False
    assert result_empty.reason == "no_monitors_configured"
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_trigify_returns_no_match_keys(_env):
    """No linkedin_url, company_domain, or company → ok=False, reason='no_match_keys'."""
    mock_client = AsyncMock()
    adapter = TrigifyAdapter(http_client=mock_client)

    result = await adapter.enrich({
        "contact_id": "c10",
        "linkedin_url": None,
        "company_domain": None,
        "company": "",
        "trigify_search_ids": ["s1"],
    })

    assert result.ok is False
    assert result.reason == "no_match_keys"
    assert result.cost_cents == 0
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_trigify_dry_run_skips_api(_env):
    """dry_run=True → ok=True, cost_cents=0, reason='dry_run_skipped', no network."""
    mock_client = AsyncMock()
    adapter = TrigifyAdapter(http_client=mock_client)

    result = await adapter.enrich(
        {
            "contact_id": "c11",
            "linkedin_url": "https://linkedin.com/in/jane",
            "trigify_search_ids": ["s1"],
        },
        dry_run=True,
    )

    assert result.ok is True
    assert result.cost_cents == 0
    assert result.reason == "dry_run_skipped"
    assert result.adapter_name == "trigify"
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_trigify_raises_on_http_5xx(_env):
    """503 from API propagates as httpx.HTTPStatusError (no retry)."""
    contact = {
        "contact_id": "c12",
        "linkedin_url": "https://linkedin.com/in/jane",
        "trigify_search_ids": ["s1"],
    }
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response({}, status_code=503)

    adapter = TrigifyAdapter(http_client=mock_client)

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.enrich(contact)


@pytest.mark.asyncio
async def test_trigify_raises_on_rate_limit(_env):
    """429 rate-limit propagates — orchestrator handles backoff."""
    contact = {
        "contact_id": "c13",
        "linkedin_url": "https://linkedin.com/in/jane",
        "trigify_search_ids": ["s1"],
    }
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response({}, status_code=429)

    adapter = TrigifyAdapter(http_client=mock_client)

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.enrich(contact)


@pytest.mark.asyncio
async def test_trigify_computes_recency_days(_env):
    """published_at 10 days before 2026-04-21 → recency_days ≈ 10."""
    contact = {
        "contact_id": "c14",
        "linkedin_url": "https://linkedin.com/in/jane",
        "company_domain": None,
        "company": "",
        "trigify_search_ids": ["s1"],
    }
    result_item = _trigify_result(
        result_id="r14",
        profile_url="https://linkedin.com/in/jane",
        published_at="2026-04-11T12:00:00Z",
    )
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(_page_response([result_item]))

    adapter = TrigifyAdapter(http_client=mock_client)
    result = await adapter.enrich(contact)

    assert result.ok is True
    ev = result.data["trigger_events"][0]
    # currentDate is 2026-04-20; published 2026-04-11 → 9 days ago.
    # Accept 8–11 to allow for clock variance in test environments.
    assert ev["recency_days"] is not None
    assert 8 <= ev["recency_days"] <= 11


@pytest.mark.asyncio
async def test_trigify_null_published_at_gives_none_recency(_env):
    """published_at=None → recency_days=None in trigger event."""
    contact = {
        "contact_id": "c15",
        "linkedin_url": "https://linkedin.com/in/jane",
        "company_domain": None,
        "company": "",
        "trigify_search_ids": ["s1"],
    }
    result_item = _trigify_result(
        result_id="r15",
        profile_url="https://linkedin.com/in/jane",
        published_at=None,
    )
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(_page_response([result_item]))

    adapter = TrigifyAdapter(http_client=mock_client)
    result = await adapter.enrich(contact)

    assert result.ok is True
    ev = result.data["trigger_events"][0]
    assert ev["recency_days"] is None
