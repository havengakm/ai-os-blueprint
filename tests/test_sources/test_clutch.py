from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from systems.scout.sources.clutch import (
    ClutchAdapter,
    ClutchSuspiciousEmptyError,
    _parse_listing_page,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _response(text: str, status_code: int = 200):
    resp = MagicMock()
    if status_code >= 400:
        resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                f"HTTP {status_code}", request=MagicMock(), response=resp,
            )
        )
        resp.status_code = status_code
    else:
        resp.raise_for_status = MagicMock(return_value=None)
        resp.status_code = 200
    resp.text = text
    return resp


def test_parse_listing_extracts_rich_fields_per_block():
    """v2 parser: per-block extraction via Schema.org/LocalBusiness microdata
    + data-* attributes. Each provider listing card produces a dict with
    name, clutch_pid, profile_url, city, state, country, employees."""
    html = _load("clutch_shopify_page0.html")
    rows = _parse_listing_page(html)
    assert len(rows) == 3
    # First row: WebFX
    assert rows[0]["name"] == "WebFX"
    assert rows[0]["clutch_pid"] == "33049"
    assert rows[0]["profile_url"] == "https://clutch.co/profile/webfx"
    assert rows[0]["city"] == "Harrisburg"
    assert rows[0]["state"] == "PA"
    assert rows[0]["country"] == "US"
    assert rows[0]["employees"] == 999  # parsed from "250 - 999"
    # Second row: Disruptive Advertising
    assert rows[1]["name"] == "Disruptive Advertising"
    assert rows[1]["state"] == "UT"
    assert rows[1]["employees"] == 249  # parsed from "50 - 249"


def test_parse_listing_empty_page_returns_empty():
    html = _load("clutch_shopify_empty.html")
    assert _parse_listing_page(html) == []


@pytest.mark.asyncio
async def test_clutch_adapter_pulls_single_page():
    mock_client = AsyncMock()
    mock_client.get.return_value = _response(_load("clutch_shopify_page0.html"))
    adapter = ClutchAdapter(
        category_path="developers/shopify",
        http_client=mock_client,
        throttle_seconds=0,
    )
    rows = await adapter.pull(client_id="clymb", max_companies=10)
    # 3 unique provider blocks on the first page. Second page fetch returns
    # the same response (AsyncMock reuses it), so its 3 entries dedupe.
    assert len(rows) >= 3
    assert rows[0].company == "WebFX"
    assert rows[0].source == "clutch:developers/shopify"
    assert rows[0].source_id == "webfx"
    assert rows[0].city == "Harrisburg"
    assert rows[0].state == "PA"
    assert rows[0].geography == "US"
    assert rows[0].employees == 999  # parsed upper bound of "250 - 999"
    assert rows[0].company_domain is None  # listing-page-only
    assert rows[0].raw_data["clutch_pid"] == "33049"


@pytest.mark.asyncio
async def test_clutch_adapter_stops_on_empty_page():
    page0_html = _load("clutch_shopify_page0.html")
    empty_html = _load("clutch_shopify_empty.html")
    responses = [_response(page0_html), _response(empty_html)]

    async def _get(url):
        return responses.pop(0) if responses else _response(empty_html)

    mock_client = AsyncMock()
    mock_client.get.side_effect = _get
    adapter = ClutchAdapter(
        category_path="developers/shopify",
        http_client=mock_client,
        throttle_seconds=0,
    )
    rows = await adapter.pull(client_id="clymb", max_companies=50, max_pages=5)
    assert len(rows) == 3  # first page had 3; second was empty → stop
    assert mock_client.get.await_count == 2  # one fetch + one stop signal


@pytest.mark.asyncio
async def test_clutch_adapter_dedups_across_pages():
    # Same HTML returned for every page — adapter should dedup by slug
    page_html = _load("clutch_shopify_page0.html")
    mock_client = AsyncMock()
    mock_client.get.return_value = _response(page_html)
    adapter = ClutchAdapter(
        category_path="developers/shopify",
        http_client=mock_client,
        throttle_seconds=0,
    )
    rows = await adapter.pull(client_id="clymb", max_companies=50, max_pages=3)
    assert len(rows) == 3  # not 9 — deduped


@pytest.mark.asyncio
async def test_clutch_adapter_respects_max_companies():
    page_html = _load("clutch_shopify_page0.html")
    mock_client = AsyncMock()
    mock_client.get.return_value = _response(page_html)
    adapter = ClutchAdapter(
        category_path="developers/shopify",
        http_client=mock_client,
        throttle_seconds=0,
    )
    rows = await adapter.pull(client_id="clymb", max_companies=2)
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_clutch_adapter_dry_run_skips_http():
    mock_client = AsyncMock()
    adapter = ClutchAdapter(
        category_path="developers/shopify",
        http_client=mock_client,
        throttle_seconds=0,
    )
    rows = await adapter.pull(client_id="clymb", max_companies=10, dry_run=True)
    assert rows == []
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_clutch_adapter_name_includes_category():
    adapter = ClutchAdapter(category_path="agencies/digital-marketing", throttle_seconds=0)
    assert adapter.name == "clutch:agencies/digital-marketing"


@pytest.mark.asyncio
async def test_clutch_retries_on_429_then_succeeds():
    """Plan 2 Task 2.0.5 (Plan 1 follow-up item 10): adapter must retry
    transient 429 with backoff instead of aborting the entire pull.
    Locks the resilience contract before the first live Clutch run."""
    page0 = _load("clutch_shopify_page0.html")
    empty = _load("clutch_shopify_empty.html")
    responses = [_response("", status_code=429), _response(page0)]

    async def _get(url):
        # After the 429+200 retry pair, fall through to empty for page 1+
        # so the loop terminates cleanly.
        return responses.pop(0) if responses else _response(empty)

    mock_client = AsyncMock()
    mock_client.get.side_effect = _get
    adapter = ClutchAdapter(
        category_path="developers/shopify",
        http_client=mock_client,
        throttle_seconds=0,
        retry_backoff_seconds=0,  # speed up the test
    )
    rows = await adapter.pull(client_id="clymb", max_companies=50, max_pages=2)
    assert len(rows) == 3  # page0 yielded 3 after retry; page1 stopped clean
    # 1 retry on page 0 + 1 success on page 0 + 1 empty-stop on page 1 = 3
    assert mock_client.get.await_count == 3


@pytest.mark.asyncio
async def test_clutch_retries_on_503_then_succeeds():
    """Same pattern as 429 but for transient 503 (server overload)."""
    page0 = _load("clutch_shopify_page0.html")
    empty = _load("clutch_shopify_empty.html")
    responses = [_response("", status_code=503), _response(page0)]

    async def _get(url):
        return responses.pop(0) if responses else _response(empty)

    mock_client = AsyncMock()
    mock_client.get.side_effect = _get
    adapter = ClutchAdapter(
        category_path="developers/shopify",
        http_client=mock_client,
        throttle_seconds=0,
        retry_backoff_seconds=0,
    )
    rows = await adapter.pull(client_id="clymb", max_companies=50, max_pages=2)
    assert len(rows) == 3
    assert mock_client.get.await_count == 3


@pytest.mark.asyncio
async def test_clutch_raises_after_retries_exhausted():
    """If 429 persists across all retries, adapter raises rather than
    silently returning empty results (which could masquerade as a clean
    end-of-listings signal in decision_log)."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _response("", status_code=429)
    adapter = ClutchAdapter(
        category_path="developers/shopify",
        http_client=mock_client,
        throttle_seconds=0,
        retry_backoff_seconds=0,
        max_retries=2,  # tight budget for the test
    )
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.pull(client_id="clymb", max_companies=10, max_pages=2)


@pytest.mark.asyncio
async def test_clutch_suspicious_empty_first_page_raises():
    """Plan 2 Task 2.0.5 (Plan 1 follow-up item 9): a 200 OK page 0 that
    yields 0 parsed entries is suspicious — could be a CAPTCHA interstitial,
    soft-block page, or layout change masquerading as a clean empty page.
    Adapter raises so the pull stage can log it as `scout.source.empty_first_page`
    instead of silently treating it as a successful empty pull."""
    empty_html = _load("clutch_shopify_empty.html")
    mock_client = AsyncMock()
    mock_client.get.return_value = _response(empty_html)
    adapter = ClutchAdapter(
        category_path="developers/shopify",
        http_client=mock_client,
        throttle_seconds=0,
    )
    with pytest.raises(ClutchSuspiciousEmptyError):
        await adapter.pull(client_id="clymb", max_companies=50, max_pages=5)


@pytest.mark.asyncio
async def test_clutch_adapter_builds_correct_url():
    # Use a non-empty fixture so page 0 doesn't trigger the suspicious-empty
    # raise (Plan 2 Task 2.0.5). The test only checks URL construction.
    mock_client = AsyncMock()
    mock_client.get.return_value = _response(_load("clutch_shopify_page0.html"))
    adapter = ClutchAdapter(
        category_path="developers/shopify",
        http_client=mock_client,
        throttle_seconds=0,
    )
    await adapter.pull(client_id="clymb", max_companies=3)
    first_call_url = mock_client.get.call_args_list[0].args[0]
    assert first_call_url == "https://clutch.co/developers/shopify?page=0"
