"""Tests for Apollo Organization Enrichment adapter."""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from systems.scout.enrich.apollo_enrich import ApolloEnrichAdapter
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
    monkeypatch.setenv("APOLLO_API_KEY", "apollo-test-key")
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


def _apollo_org_payload(
    name: str = "Acme Corp",
    primary_domain: str = "acme.com",
    industry: str = "Software",
    employees: int = 120,
    revenue: int = 15_000_000,
    founded_year: int = 2014,
    short_description: str = "We build things.",
    linkedin_url: str = "https://www.linkedin.com/company/acme",
    technologies: list[str] | None = None,
    keywords: list[str] | None = None,
) -> dict:
    return {
        "organization": {
            "name": name,
            "website_url": f"https://{primary_domain}",
            "primary_domain": primary_domain,
            "industry": industry,
            "keywords": keywords if keywords is not None else ["saas", "b2b"],
            "estimated_num_employees": employees,
            "annual_revenue": revenue,
            "city": "Austin",
            "state": "TX",
            "country": "United States",
            "short_description": short_description,
            "founded_year": founded_year,
            "linkedin_url": linkedin_url,
            "twitter_url": "https://twitter.com/acme",
            "technologies": technologies if technologies is not None else ["aws", "python"],
        }
    }


# --------------------------------------------------------------------------- #
# Skip paths                                                                    #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_apollo_enrich_dry_run_skips_api(_env):
    """dry_run=True → ok=True, cost_cents=0, reason='dry_run_skipped', no network."""
    mock_client = AsyncMock()
    adapter = ApolloEnrichAdapter(http_client=mock_client)
    result = await adapter.enrich(
        {"contact_id": "c1", "company_domain": "acme.com"},
        dry_run=True,
    )

    assert isinstance(result, EnrichResult)
    assert result.ok is True
    assert result.cost_cents == 0
    assert result.reason == "dry_run_skipped"
    assert result.data == {}
    assert result.adapter_name == "apollo_enrich"
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_apollo_enrich_returns_no_api_key_when_unset(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.delenv("APOLLO_API_KEY", raising=False)
    from config.settings import get_settings
    get_settings.cache_clear()

    mock_client = AsyncMock()
    adapter = ApolloEnrichAdapter(http_client=mock_client)
    result = await adapter.enrich({"contact_id": "c2", "company_domain": "acme.com"})

    assert result.ok is False
    assert result.reason == "no_api_key"
    assert result.cost_cents == 0
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_apollo_enrich_returns_no_company_domain_when_missing(_env):
    mock_client = AsyncMock()
    adapter = ApolloEnrichAdapter(http_client=mock_client)

    result_none = await adapter.enrich({"contact_id": "c3"})
    assert result_none.ok is False
    assert result_none.reason == "no_company_domain"
    assert result_none.cost_cents == 0
    mock_client.get.assert_not_called()

    result_blank = await adapter.enrich({"contact_id": "c3", "company_domain": "   "})
    assert result_blank.ok is False
    assert result_blank.reason == "no_company_domain"
    assert result_blank.cost_cents == 0
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_apollo_enrich_skips_when_already_complete(_env):
    """If contact already has revenue + employees + industry + founded_year, skip."""
    # Mock would blow up if called — `.get` returns an AsyncMock coroutine-like
    # object whose `.raise_for_status()` is untyped; we assert it's never called.
    mock_client = AsyncMock()
    mock_client.get.side_effect = AssertionError("Should not have called Apollo")
    adapter = ApolloEnrichAdapter(http_client=mock_client)

    result = await adapter.enrich({
        "contact_id": "c4",
        "company_domain": "acme.com",
        "revenue_usd": 15_000_000,
        "employees": 120,
        "industry": "Software",
        "founded_year": 2014,
    })

    assert result.ok is True
    assert result.reason == "already_complete"
    assert result.cost_cents == 0
    assert result.data == {}
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_apollo_enrich_calls_api_when_any_core_field_missing(_env):
    """Partial data (missing founded_year) → still calls Apollo."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(_apollo_org_payload())
    adapter = ApolloEnrichAdapter(http_client=mock_client)

    result = await adapter.enrich({
        "contact_id": "c5",
        "company_domain": "acme.com",
        "revenue_usd": 15_000_000,
        "employees": 120,
        "industry": "Software",
        # founded_year missing → still enrich
    })

    assert result.reason == "enriched"
    assert result.cost_cents == 1
    mock_client.get.assert_called_once()


# --------------------------------------------------------------------------- #
# Success paths                                                                 #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_apollo_enrich_successful_fill(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(_apollo_org_payload())
    adapter = ApolloEnrichAdapter(http_client=mock_client)

    result = await adapter.enrich({"contact_id": "c6", "company_domain": "acme.com"})

    assert isinstance(result, EnrichResult)
    assert result.ok is True
    assert result.reason == "enriched"
    assert result.cost_cents == 1
    assert result.adapter_name == "apollo_enrich"
    assert result.data["company_revenue_usd"] == 15_000_000
    assert result.data["company_employees"] == 120
    assert result.data["company_industry"] == "Software"
    assert result.data["company_founded_year"] == 2014
    assert result.data["company_short_description"] == "We build things."
    assert result.data["company_linkedin_url"] == "https://www.linkedin.com/company/acme"
    assert result.data["company_technologies"] == ["aws", "python"]
    assert result.data["company_keywords"] == ["saas", "b2b"]
    # raw_response preserved for audit
    assert result.raw_response["organization"]["name"] == "Acme Corp"


@pytest.mark.asyncio
async def test_apollo_enrich_no_match_when_org_empty(_env):
    """Apollo returns no organization → ok=True, reason='no_match', cost_cents=1."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response({"organization": None})
    adapter = ApolloEnrichAdapter(http_client=mock_client)

    result = await adapter.enrich({"contact_id": "c7", "company_domain": "unknown.io"})

    assert result.ok is True
    assert result.reason == "no_match"
    assert result.cost_cents == 1  # credit was spent
    assert result.data == {}


@pytest.mark.asyncio
async def test_apollo_enrich_request_shape(_env):
    """Verify URL, headers, and params sent to Apollo."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(_apollo_org_payload())
    adapter = ApolloEnrichAdapter(http_client=mock_client)

    # Pass a URL-form domain to confirm normalisation happens before send.
    await adapter.enrich({"contact_id": "c8", "company_domain": "https://www.acme.com/"})

    mock_client.get.assert_called_once()
    call = mock_client.get.call_args
    url = call.args[0] if call.args else call.kwargs.get("url", "")
    params = call.kwargs.get("params", {})
    headers = call.kwargs.get("headers", {})

    assert url == "https://api.apollo.io/v1/organizations/enrich"
    assert params.get("domain") == "acme.com"     # normalised, no scheme/www
    assert headers.get("x-api-key") == "apollo-test-key"
    assert headers.get("Content-Type") == "application/json"


@pytest.mark.asyncio
async def test_apollo_enrich_omits_fields_apollo_doesnt_return(_env):
    """Apollo org with missing optional fields → data only includes what it returned."""
    sparse_payload = {
        "organization": {
            "name": "Sparse Co",
            "primary_domain": "sparse.co",
            "industry": "Consulting",
            # no employees, revenue, founded_year, linkedin, tech, keywords
        }
    }
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(sparse_payload)
    adapter = ApolloEnrichAdapter(http_client=mock_client)

    result = await adapter.enrich({"contact_id": "c9", "company_domain": "sparse.co"})

    assert result.reason == "enriched"
    assert result.cost_cents == 1
    assert result.data == {"company_industry": "Consulting"}


# --------------------------------------------------------------------------- #
# Error propagation                                                             #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_apollo_enrich_raises_on_http_5xx(_env):
    """500 propagates as httpx.HTTPStatusError (no retry, no swallow)."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response({}, status_code=500)
    adapter = ApolloEnrichAdapter(http_client=mock_client)

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.enrich({"contact_id": "c10", "company_domain": "acme.com"})


@pytest.mark.asyncio
async def test_apollo_enrich_raises_on_network_timeout(_env):
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.TimeoutException("timed out")
    adapter = ApolloEnrichAdapter(http_client=mock_client)

    with pytest.raises(httpx.TimeoutException):
        await adapter.enrich({"contact_id": "c11", "company_domain": "acme.com"})
