"""Tests for the production InstantlyAdapter (httpx + Instantly v2 API).

Uses ``httpx.MockTransport`` so we exercise the real adapter's URL
construction + payload shape + response parsing without making network
calls. No real Instantly API key needed.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import httpx
import pytest

from systems.beacon import InstantlyAdapter
from systems.beacon.types import Reply, SendStats


def _client_with_handler(handler):
    """Build an httpx.AsyncClient wired to a MockTransport handler."""
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(
        base_url="https://api.instantly.ai",
        transport=transport,
        headers={"Authorization": "Bearer test-key"},
    )


def test_init_rejects_empty_api_key():
    with pytest.raises(ValueError, match="instantly_api_key must be set"):
        InstantlyAdapter(api_key="")


def test_adapter_name_is_instantly():
    adapter = InstantlyAdapter(api_key="test-key")
    assert adapter.name == "instantly"


@pytest.mark.asyncio
async def test_add_lead_to_campaign_posts_correct_payload_and_returns_lead_id():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={"leads": [{"id": "esp-lead-abc-123", "email": "a@x.com"}]},
        )

    client = _client_with_handler(handler)
    adapter = InstantlyAdapter(api_key="test-key", http_client=client)

    lead_id = await adapter.add_lead_to_campaign(
        campaign_id="camp-X",
        contact_email="alice@example.com",
        contact_first_name="Alice",
        custom_subject="thoughts Alice?",
        custom_body="Saw your work.",
    )

    assert lead_id == "esp-lead-abc-123"
    assert captured["url"] == "https://api.instantly.ai/api/v2/leads/bulk"
    assert captured["body"]["campaign_id"] == "camp-X"
    assert len(captured["body"]["leads"]) == 1
    lead = captured["body"]["leads"][0]
    assert lead["email"] == "alice@example.com"
    assert lead["first_name"] == "Alice"
    assert lead["payload"]["custom_subject"] == "thoughts Alice?"
    assert lead["payload"]["custom_body"] == "Saw your work."

    await client.aclose()


@pytest.mark.asyncio
async def test_add_lead_to_campaign_raises_on_empty_leads_response():
    """If Instantly returns 200 but with an empty leads array, bubble a clear error."""
    def handler(request):
        return httpx.Response(200, json={"leads": []})

    client = _client_with_handler(handler)
    adapter = InstantlyAdapter(api_key="test-key", http_client=client)

    with pytest.raises(RuntimeError, match="empty leads array"):
        await adapter.add_lead_to_campaign(
            campaign_id="c", contact_email="e@x.com", contact_first_name="E",
            custom_subject="s", custom_body="b",
        )

    await client.aclose()


@pytest.mark.asyncio
async def test_add_lead_to_campaign_raises_on_4xx():
    def handler(request):
        return httpx.Response(400, json={"error": "invalid email"})

    client = _client_with_handler(handler)
    adapter = InstantlyAdapter(api_key="test-key", http_client=client)

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.add_lead_to_campaign(
            campaign_id="c", contact_email="bogus", contact_first_name="X",
            custom_subject="s", custom_body="b",
        )

    await client.aclose()


@pytest.mark.asyncio
async def test_pause_account_is_a_stub_that_logs_and_returns():
    """Instantly v2 API doesn't expose a documented account-pause endpoint
    in the public index (2026-04-27). pause_account is a stub that warns
    and returns. Test locks that behaviour."""
    adapter = InstantlyAdapter(api_key="test-key")
    # Should not raise + should not require an http client.
    result = await adapter.pause_account(
        esp_account_id="acct-A", reason="bounce-spike",
    )
    assert result is None


@pytest.mark.asyncio
async def test_fetch_replies_since_parses_response_into_reply_dataclasses():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "msg-001",
                        "reply_to_message_id": "msg-orig-A",
                        "from_email": "alice@acmecorp.com",
                        "subject": "Re: thoughts",
                        "body": "Yes interested",
                        "received_at": "2026-04-27T11:30:00Z",
                    },
                    {
                        "id": "msg-002",
                        "reply_to_message_id": "msg-orig-B",
                        "from_email": "bob@example.com",
                        "subject": "Re: thoughts",
                        "body": "Not now",
                        "received_at": "2026-04-27T10:45:00Z",
                    },
                ]
            },
        )

    client = _client_with_handler(handler)
    adapter = InstantlyAdapter(api_key="test-key", http_client=client)

    since = datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    replies = await adapter.fetch_replies_since(since=since)

    assert "received_after=2026-04-27T10%3A00%3A00Z" in captured["url"] or \
           captured["params"].get("received_after") == "2026-04-27T10:00:00Z"
    assert captured["params"]["email_type"] == "reply"

    assert len(replies) == 2
    # Newest first
    assert replies[0].esp_message_id == "msg-001"
    assert replies[0].from_email == "alice@acmecorp.com"
    assert replies[0].body == "Yes interested"
    assert replies[0].replied_to_message_id == "msg-orig-A"
    assert replies[0].received_at.year == 2026
    assert replies[1].esp_message_id == "msg-002"

    await client.aclose()


@pytest.mark.asyncio
async def test_fetch_replies_since_handles_empty_result():
    def handler(request):
        return httpx.Response(200, json={"items": []})

    client = _client_with_handler(handler)
    adapter = InstantlyAdapter(api_key="test-key", http_client=client)

    since = datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    replies = await adapter.fetch_replies_since(since=since)
    assert replies == []

    await client.aclose()


@pytest.mark.asyncio
async def test_get_send_stats_aggregates_from_emails_endpoint():
    def handler(request):
        # One sent + one bounced + one replied + one opened-without-reply
        return httpx.Response(
            200,
            json={
                "items": [
                    {"status": "sent", "had_reply": False},
                    {"status": "delivered", "had_reply": True, "opened_at": "2026-04-27T11:00:00Z"},
                    {"status": "bounced", "had_reply": False},
                    {"status": "sent", "had_reply": False, "opened_at": "2026-04-27T11:30:00Z"},
                ]
            },
        )

    client = _client_with_handler(handler)
    adapter = InstantlyAdapter(api_key="test-key", http_client=client)

    stats = await adapter.get_send_stats(
        esp_account_id="acct-A", on_date=date(2026, 4, 27),
    )

    assert isinstance(stats, SendStats)
    assert stats.esp_account_id == "acct-A"
    assert stats.on_date == date(2026, 4, 27)
    assert stats.sent_count == 3   # 2x sent + 1x delivered
    assert stats.bounced_count == 1
    assert stats.replied_count == 1
    # 2 of 3 sent emails were opened → 2/3.
    assert stats.open_rate is not None
    assert stats.open_rate == pytest.approx(2 / 3)

    await client.aclose()


@pytest.mark.asyncio
async def test_get_send_stats_returns_none_open_rate_when_zero_sends():
    def handler(request):
        return httpx.Response(200, json={"items": []})

    client = _client_with_handler(handler)
    adapter = InstantlyAdapter(api_key="test-key", http_client=client)

    stats = await adapter.get_send_stats(
        esp_account_id="acct-empty", on_date=date(2026, 4, 27),
    )
    assert stats.sent_count == 0
    assert stats.open_rate is None

    await client.aclose()


@pytest.mark.asyncio
async def test_aclose_idempotent_on_lazy_client():
    """aclose() should not raise on a fresh adapter that never made a call."""
    adapter = InstantlyAdapter(api_key="test-key")
    await adapter.aclose()
    await adapter.aclose()  # second call is a no-op


@pytest.mark.asyncio
async def test_aclose_does_not_close_injected_client():
    """If tests inject their own client, the adapter must not close it."""
    client = _client_with_handler(lambda r: httpx.Response(200, json={"leads": [{"id": "x"}]}))
    adapter = InstantlyAdapter(api_key="test-key", http_client=client)
    await adapter.aclose()
    # Client is still usable
    response = await client.post("/api/v2/leads/bulk", json={})
    assert response.status_code == 200
    await client.aclose()
