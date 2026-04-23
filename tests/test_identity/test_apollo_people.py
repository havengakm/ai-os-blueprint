from unittest.mock import AsyncMock, MagicMock

import pytest

from systems.scout.identity.apollo_people import ApolloPeopleAdapter
from systems.scout.identity.base import IdentityResult, is_generic_email


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


def _mock_response(people: list[dict]):
    resp = MagicMock()
    resp.raise_for_status = MagicMock(return_value=None)
    resp.json = MagicMock(return_value={"people": people})
    return resp


def test_is_generic_email_flags_role_addresses():
    assert is_generic_email("info@foo.com")
    assert is_generic_email("contact@foo.com")
    assert is_generic_email("hello@foo.com")
    assert is_generic_email("sales@foo.com")
    assert is_generic_email("")
    assert is_generic_email(None)


def test_is_generic_email_allows_personal_addresses():
    assert not is_generic_email("brad@focuscfo.com")
    assert not is_generic_email("mike.mccracken@mccrackenalliance.com")
    assert not is_generic_email("j.smith@company.com")


@pytest.mark.asyncio
async def test_apollo_resolves_decision_maker(_env):
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_response([
        {
            "first_name": "Brad",
            "last_name": "Martyn",
            "title": "Founder & CEO",
            "email": "brad@focuscfo.com",
            "linkedin_url": "https://www.linkedin.com/in/bradmartyn",
        },
    ])
    adapter = ApolloPeopleAdapter(http_client=mock_client)
    result = await adapter.resolve(company="FocusCFO", company_domain="focuscfo.com")

    assert result is not None
    assert isinstance(result, IdentityResult)
    assert result.first_name == "Brad"
    assert result.last_name == "Martyn"
    assert result.title == "Founder & CEO"
    assert result.email == "brad@focuscfo.com"
    assert result.linkedin_url == "https://www.linkedin.com/in/bradmartyn"
    assert result.source == "apollo_people"
    assert 0.85 <= result.confidence <= 0.99


@pytest.mark.asyncio
async def test_apollo_skips_generic_emails(_env):
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_response([
        {"first_name": "Role", "last_name": "Mailbox", "email": "info@foo.com"},
        {"first_name": "Real", "last_name": "Person", "email": "real@foo.com", "title": "CEO"},
    ])
    adapter = ApolloPeopleAdapter(http_client=mock_client)
    result = await adapter.resolve(company="Foo", company_domain="foo.com")

    assert result is not None
    assert result.email == "real@foo.com"  # generic one skipped


@pytest.mark.asyncio
async def test_apollo_returns_none_when_only_generics_found(_env):
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_response([
        {"first_name": "A", "last_name": "B", "email": "info@foo.com"},
        {"first_name": "C", "last_name": "D", "email": "sales@foo.com"},
    ])
    adapter = ApolloPeopleAdapter(http_client=mock_client)
    result = await adapter.resolve(company="Foo", company_domain="foo.com")
    assert result is None


@pytest.mark.asyncio
async def test_apollo_returns_none_without_domain(_env):
    """Apollo People Search needs a domain to be useful; without one, skip."""
    mock_client = AsyncMock()
    adapter = ApolloPeopleAdapter(http_client=mock_client)
    result = await adapter.resolve(company="Foo", company_domain=None)
    assert result is None
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_apollo_returns_none_without_api_key(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.delenv("APOLLO_API_KEY", raising=False)
    from config.settings import get_settings
    get_settings.cache_clear()

    mock_client = AsyncMock()
    adapter = ApolloPeopleAdapter(http_client=mock_client)
    result = await adapter.resolve(company="Foo", company_domain="foo.com")
    assert result is None
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_apollo_handles_name_split_fallback(_env):
    """If only `name` is provided (not first_name/last_name), split it."""
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_response([
        {"name": "Jack Perkins", "email": "jack@cfohub.com", "title": "CEO"},
    ])
    adapter = ApolloPeopleAdapter(http_client=mock_client)
    result = await adapter.resolve(company="CFO Hub", company_domain="cfohub.com")
    assert result is not None
    assert result.first_name == "Jack"
    assert result.last_name == "Perkins"


@pytest.mark.asyncio
async def test_apollo_returns_none_when_people_list_empty(_env):
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_response([])
    adapter = ApolloPeopleAdapter(http_client=mock_client)
    result = await adapter.resolve(company="Foo", company_domain="foo.com")
    assert result is None


@pytest.mark.asyncio
async def test_apollo_payload_includes_seniority_filter(_env):
    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_response([])
    adapter = ApolloPeopleAdapter(http_client=mock_client)
    await adapter.resolve(company="Foo", company_domain="foo.com")

    call = mock_client.post.call_args
    payload = call.kwargs["json"]
    assert payload["q_organization_domains"] == "foo.com"
    assert "founder" in payload["person_seniorities"]
    assert "c_suite" in payload["person_seniorities"]
    assert "q_keywords" in payload  # title keywords passed
    headers = call.kwargs["headers"]
    assert headers["x-api-key"] == "apollo-test-key"
