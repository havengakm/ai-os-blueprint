from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from systems.scout.sources.clutch import ClutchAdapter, _parse_listing_page


FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _response(text: str):
    resp = MagicMock()
    resp.raise_for_status = MagicMock(return_value=None)
    resp.text = text
    return resp


def test_parse_listing_extracts_names_urls_locations():
    html = _load("clutch_shopify_page0.html")
    rows = _parse_listing_page(html)
    # 3 JSON-LD names + 3 href profile-URLs + 3 locality spans
    assert len(rows) == 3
    assert rows[0]["name"] == "FocusCFO"
    assert rows[0]["profile_url"] == "https://clutch.co/profile/focuscfo"
    assert rows[0]["location"] == "Columbus, OH"


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
    # 3 unique profiles on the first page. Second page fetch returns empty
    # in this test (AsyncMock reuses the same response), so let's assert 3.
    assert len(rows) >= 3
    assert rows[0].company == "FocusCFO"
    assert rows[0].source == "clutch:developers/shopify"
    assert rows[0].source_id == "focuscfo"
    assert rows[0].city == "Columbus"
    assert rows[0].state == "OH"
    assert rows[0].company_domain is None  # listing-page-only


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
async def test_clutch_adapter_builds_correct_url():
    mock_client = AsyncMock()
    mock_client.get.return_value = _response(_load("clutch_shopify_empty.html"))
    adapter = ClutchAdapter(
        category_path="developers/shopify",
        http_client=mock_client,
        throttle_seconds=0,
    )
    await adapter.pull(client_id="clymb", max_companies=10)
    first_call_url = mock_client.get.call_args_list[0].args[0]
    assert first_call_url == "https://clutch.co/developers/shopify?page=0"
