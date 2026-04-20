from unittest.mock import AsyncMock, MagicMock

import pytest

from systems.scout.identity.hunter_domain import HunterDomainAdapter
from systems.scout.identity.base import IdentityResult


@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.setenv("HUNTER_API_KEY", "hunter-test-key")
    from config.settings import get_settings
    get_settings.cache_clear()


def _mock_response(emails: list[dict]):
    resp = MagicMock()
    resp.raise_for_status = MagicMock(return_value=None)
    resp.json = MagicMock(return_value={"data": {"domain": "example.com", "emails": emails}})
    return resp


@pytest.mark.asyncio
async def test_hunter_resolves_decision_maker(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response([
        {
            "value": "jack@cfohub.com",
            "first_name": "Jack",
            "last_name": "Perkins",
            "position": "CEO",
            "seniority": "executive",
            "linkedin": "https://www.linkedin.com/in/jackperkins",
            "confidence": 95,
        },
    ])
    adapter = HunterDomainAdapter(http_client=mock_client)
    result = await adapter.resolve(company="CFO Hub", company_domain="cfohub.com")

    assert result is not None
    assert isinstance(result, IdentityResult)
    assert result.first_name == "Jack"
    assert result.last_name == "Perkins"
    assert result.title == "CEO"
    assert result.email == "jack@cfohub.com"
    assert result.linkedin_url == "https://www.linkedin.com/in/jackperkins"
    assert result.source == "hunter_domain"
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_hunter_picks_highest_seniority(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response([
        {"value": "rep@foo.com", "first_name": "Alice", "last_name": "Rep", "position": "Sales Representative", "confidence": 90},
        {"value": "ceo@foo.com", "first_name": "Bob", "last_name": "Boss", "position": "CEO", "confidence": 80},
        {"value": "mgr@foo.com", "first_name": "Carol", "last_name": "Manager", "position": "Manager", "confidence": 85},
    ])
    adapter = HunterDomainAdapter(http_client=mock_client)
    result = await adapter.resolve(company="Foo Inc", company_domain="foo.com")

    assert result is not None
    assert result.email == "ceo@foo.com"
    assert result.first_name == "Bob"


@pytest.mark.asyncio
async def test_hunter_skips_generic_emails(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response([
        {"value": "info@foo.com", "first_name": "Role", "last_name": "Box", "position": "CEO", "confidence": 99},
        {"value": "real@foo.com", "first_name": "Real", "last_name": "Person", "position": "Founder", "confidence": 80},
    ])
    adapter = HunterDomainAdapter(http_client=mock_client)
    result = await adapter.resolve(company="Foo Inc", company_domain="foo.com")

    assert result is not None
    assert result.email == "real@foo.com"


@pytest.mark.asyncio
async def test_hunter_returns_none_when_only_generics(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response([
        {"value": "info@foo.com", "first_name": "A", "last_name": "B", "position": "CEO", "confidence": 90},
        {"value": "sales@foo.com", "first_name": "C", "last_name": "D", "position": "Founder", "confidence": 85},
    ])
    adapter = HunterDomainAdapter(http_client=mock_client)
    result = await adapter.resolve(company="Foo Inc", company_domain="foo.com")
    assert result is None


@pytest.mark.asyncio
async def test_hunter_returns_none_when_no_seniority_match(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response([
        {"value": "alice@foo.com", "first_name": "Alice", "last_name": "Smith", "position": "Sales Representative", "confidence": 90},
        {"value": "bob@foo.com", "first_name": "Bob", "last_name": "Jones", "position": "Software Engineer", "confidence": 85},
    ])
    adapter = HunterDomainAdapter(http_client=mock_client)
    result = await adapter.resolve(company="Foo Inc", company_domain="foo.com")
    assert result is None


@pytest.mark.asyncio
async def test_hunter_returns_none_without_domain(_env):
    mock_client = AsyncMock()
    adapter = HunterDomainAdapter(http_client=mock_client)
    result = await adapter.resolve(company="Foo Inc", company_domain=None)
    assert result is None
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_hunter_returns_none_without_api_key(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.delenv("HUNTER_API_KEY", raising=False)
    from config.settings import get_settings
    get_settings.cache_clear()

    mock_client = AsyncMock()
    adapter = HunterDomainAdapter(http_client=mock_client)
    result = await adapter.resolve(company="Foo Inc", company_domain="foo.com")
    assert result is None
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_hunter_normalises_confidence(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response([
        {"value": "jack@cfohub.com", "first_name": "Jack", "last_name": "Perkins", "position": "CEO", "confidence": 95},
    ])
    adapter = HunterDomainAdapter(http_client=mock_client)
    result = await adapter.resolve(company="CFO Hub", company_domain="cfohub.com")

    assert result is not None
    assert result.confidence == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_hunter_skips_blank_names(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response([
        {"value": "ceo@foo.com", "first_name": "", "last_name": "", "position": "CEO", "confidence": 90},
        {"value": "founder@foo.com", "first_name": "Real", "last_name": "Person", "position": "Founder", "confidence": 80},
    ])
    adapter = HunterDomainAdapter(http_client=mock_client)
    result = await adapter.resolve(company="Foo Inc", company_domain="foo.com")

    assert result is not None
    assert result.email == "founder@foo.com"


@pytest.mark.asyncio
async def test_hunter_request_shape(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response([])
    adapter = HunterDomainAdapter(http_client=mock_client)
    await adapter.resolve(company="Foo Inc", company_domain="foo.com")

    mock_client.get.assert_called_once()
    call = mock_client.get.call_args
    # URL is the first positional arg
    url = call.args[0] if call.args else call.kwargs.get("url")
    assert "api.hunter.io" in url
    # api_key must be in query params, not headers
    params = call.kwargs.get("params", {})
    assert params.get("api_key") == "hunter-test-key"
    assert params.get("domain") == "foo.com"
