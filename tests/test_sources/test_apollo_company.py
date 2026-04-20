from unittest.mock import AsyncMock, MagicMock

import pytest

from systems.scout.sources.apollo_company import ApolloCompanyAdapter


@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.setenv("APOLLO_API_KEY", "apollo-test-key")
    from config.settings import get_settings
    get_settings.cache_clear()


def _mock_response(organizations: list[dict], total_pages: int = 1):
    resp = MagicMock()
    resp.raise_for_status = MagicMock(return_value=None)
    resp.json = MagicMock(return_value={
        "organizations": organizations,
        "pagination": {"total_entries": len(organizations), "page": 1, "per_page": 25, "total_pages": total_pages},
    })
    return resp


@pytest.mark.asyncio
async def test_apollo_returns_company_contacts(_env):
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_response([
        {
            "id": "org-1",
            "name": "FocusCFO",
            "website_url": "https://focuscfo.com",
            "primary_domain": "focuscfo.com",
            "industry": "Fractional CFO",
            "estimated_num_employees": 15,
            "annual_revenue": 3_000_000,
            "city": "Columbus",
            "state": "Ohio",
            "country": "United States",
        },
    ])
    adapter = ApolloCompanyAdapter(http_client=mock_client)
    rows = await adapter.pull(client_id="clymb", max_companies=10, keywords=["fractional CFO"])
    assert len(rows) == 1
    assert rows[0].company == "FocusCFO"
    assert rows[0].company_domain == "focuscfo.com"
    assert rows[0].employees == 15
    assert rows[0].revenue_usd == 3_000_000
    assert rows[0].source == "apollo_company"
    assert rows[0].source_id == "org-1"


@pytest.mark.asyncio
async def test_apollo_respects_max_companies(_env):
    mock_client = AsyncMock()
    # Return 5 orgs per page
    orgs = [
        {"id": f"org-{i}", "name": f"Co{i}", "primary_domain": f"co{i}.com"}
        for i in range(5)
    ]
    mock_client.post.return_value = _mock_response(orgs, total_pages=5)
    adapter = ApolloCompanyAdapter(http_client=mock_client)
    rows = await adapter.pull(client_id="clymb", max_companies=3)
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_apollo_dry_run_does_not_call_api(_env):
    mock_client = AsyncMock()
    adapter = ApolloCompanyAdapter(http_client=mock_client)
    rows = await adapter.pull(client_id="clymb", max_companies=10, dry_run=True)
    assert rows == []
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_apollo_missing_api_key_returns_empty(monkeypatch):
    # Set required env minus Apollo key
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.delenv("APOLLO_API_KEY", raising=False)
    from config.settings import get_settings
    get_settings.cache_clear()

    mock_client = AsyncMock()
    adapter = ApolloCompanyAdapter(http_client=mock_client)
    rows = await adapter.pull(client_id="clymb", max_companies=10)
    assert rows == []
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_apollo_skips_orgs_without_name(_env):
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_response([
        {"id": "nameless", "primary_domain": "nameless.com"},
        {"id": "valid", "name": "ValidCo", "primary_domain": "validco.com"},
    ])
    adapter = ApolloCompanyAdapter(http_client=mock_client)
    rows = await adapter.pull(client_id="clymb", max_companies=10)
    assert len(rows) == 1
    assert rows[0].company == "ValidCo"


@pytest.mark.asyncio
async def test_apollo_passes_icp_filters(_env):
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_response([])
    adapter = ApolloCompanyAdapter(http_client=mock_client)
    await adapter.pull(
        client_id="clymb",
        max_companies=10,
        keywords=["fractional CFO", "outsourced CFO"],
        employee_ranges=["10,50", "51,200"],
        locations=["United States"],
    )
    call = mock_client.post.call_args
    payload = call.kwargs["json"]
    assert payload["q_organization_keyword_tags"] == ["fractional CFO", "outsourced CFO"]
    assert payload["organization_num_employees_ranges"] == ["10,50", "51,200"]
    assert payload["organization_locations"] == ["United States"]
