"""Tests for ZeroBounce email-verification adapter."""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from systems.scout.enrich.zerobounce import ZeroBounceAdapter
from systems.scout.enrich.base import EnrichResult


@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.setenv("ZEROBOUNCE_API_KEY", "zb-test-key")
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


def _zb_payload(
    status: str,
    sub_status: str = "",
    mx_found: bool = True,
    smtp_provider: str = "Gmail",
) -> dict:
    return {
        "address": "test@example.com",
        "status": status,
        "sub_status": sub_status,
        "mx_found": "true" if mx_found else "false",
        "smtp_provider": smtp_provider,
    }


@pytest.mark.asyncio
async def test_zerobounce_verifies_valid_email(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(_zb_payload("valid"))
    adapter = ZeroBounceAdapter(http_client=mock_client)
    result = await adapter.enrich({"contact_id": "c1", "email": "brad@focuscfo.com"})

    assert isinstance(result, EnrichResult)
    assert result.ok is True
    assert result.data["email_verified"] is True
    assert result.data["email_catch_all"] is False
    assert result.reason == "verified"
    assert result.cost_cents == 1
    assert result.adapter_name == "zerobounce"


@pytest.mark.asyncio
async def test_zerobounce_flags_catch_all(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(_zb_payload("catch-all"))
    adapter = ZeroBounceAdapter(http_client=mock_client)
    result = await adapter.enrich({"contact_id": "c2", "email": "ceo@largecorp.com"})

    assert result.ok is True
    assert result.data["email_verified"] is False
    assert result.data["email_catch_all"] is True
    assert result.reason == "catch_all_domain"
    assert result.cost_cents == 1


@pytest.mark.asyncio
async def test_zerobounce_flags_invalid(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        _zb_payload("invalid", sub_status="mailbox_not_found")
    )
    adapter = ZeroBounceAdapter(http_client=mock_client)
    result = await adapter.enrich({"contact_id": "c3", "email": "gone@example.com"})

    assert result.ok is True
    assert result.data["email_verified"] is False
    assert result.data["zerobounce_sub_status"] == "mailbox_not_found"
    assert result.reason == "unsafe:invalid"
    assert result.cost_cents == 1


@pytest.mark.asyncio
async def test_zerobounce_flags_unknown_as_indeterminate(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(_zb_payload("unknown"))
    adapter = ZeroBounceAdapter(http_client=mock_client)
    result = await adapter.enrich({"contact_id": "c4", "email": "maybe@domain.com"})

    assert result.ok is True
    assert result.reason == "indeterminate"
    assert result.cost_cents == 1


@pytest.mark.asyncio
async def test_zerobounce_returns_no_api_key_when_unset(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.delenv("ZEROBOUNCE_API_KEY", raising=False)
    from config.settings import get_settings
    get_settings.cache_clear()

    mock_client = AsyncMock()
    adapter = ZeroBounceAdapter(http_client=mock_client)
    result = await adapter.enrich({"contact_id": "c5", "email": "test@example.com"})

    assert result.ok is False
    assert result.reason == "no_api_key"
    assert result.cost_cents == 0
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_zerobounce_returns_no_email_when_blank(_env):
    mock_client = AsyncMock()
    adapter = ZeroBounceAdapter(http_client=mock_client)

    result_none = await adapter.enrich({"contact_id": "c6"})
    assert result_none.ok is False
    assert result_none.reason == "no_email"
    assert result_none.cost_cents == 0
    mock_client.get.assert_not_called()

    result_empty = await adapter.enrich({"contact_id": "c6", "email": ""})
    assert result_empty.ok is False
    assert result_empty.reason == "no_email"
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_zerobounce_dry_run_skips_api(_env):
    mock_client = AsyncMock()
    adapter = ZeroBounceAdapter(http_client=mock_client)
    result = await adapter.enrich(
        {"contact_id": "c7", "email": "real@company.com"},
        dry_run=True,
    )

    assert result.ok is True
    assert result.cost_cents == 0
    assert result.reason == "dry_run_skipped"
    assert result.data == {}
    assert result.adapter_name == "zerobounce"
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_zerobounce_raises_on_http_5xx(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response({}, status_code=503)
    adapter = ZeroBounceAdapter(http_client=mock_client)

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.enrich({"contact_id": "c8", "email": "test@example.com"})


@pytest.mark.asyncio
async def test_zerobounce_raises_on_network_timeout(_env):
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.TimeoutException("timed out")
    adapter = ZeroBounceAdapter(http_client=mock_client)

    with pytest.raises(httpx.TimeoutException):
        await adapter.enrich({"contact_id": "c9", "email": "test@example.com"})


@pytest.mark.asyncio
async def test_zerobounce_request_shape(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(_zb_payload("valid"))
    adapter = ZeroBounceAdapter(http_client=mock_client)
    await adapter.enrich({"contact_id": "c10", "email": "user@example.com"})

    mock_client.get.assert_called_once()
    call = mock_client.get.call_args
    url = call.args[0] if call.args else call.kwargs.get("url", "")
    params = call.kwargs.get("params", {})

    assert "/v2/validate" in url
    assert params.get("api_key") == "zb-test-key"
    assert params.get("email") == "user@example.com"


@pytest.mark.asyncio
async def test_zerobounce_captures_mx_and_smtp_in_data(_env):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(
        _zb_payload("valid", mx_found=True, smtp_provider="Gmail")
    )
    adapter = ZeroBounceAdapter(http_client=mock_client)
    result = await adapter.enrich({"contact_id": "c11", "email": "exec@gmail.com"})

    assert result.data["mx_found"] is True
    assert result.data["smtp_provider"] == "Gmail"
