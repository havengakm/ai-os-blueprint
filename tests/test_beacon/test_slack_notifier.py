"""Tests for HttpxSlackNotifier."""
from __future__ import annotations

import httpx
import pytest

from systems.beacon.reply.slack_notifier import HttpxSlackNotifier


def _make_transport(captured: list[dict]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(
            {
                "method": request.method,
                "url": str(request.url),
                "json": (
                    None
                    if not request.content
                    else __import__("json").loads(request.content.decode())
                ),
            }
        )
        return httpx.Response(200, json={"ok": True})

    return httpx.MockTransport(handler)


async def test_notify_posts_text_payload_to_webhook_url():
    captured: list[dict] = []
    transport = _make_transport(captured)
    async with httpx.AsyncClient(transport=transport) as client:
        notifier = HttpxSlackNotifier(
            webhook_url="https://hooks.slack.com/services/ABC/DEF/xyz",
            http_client=client,
        )
        await notifier.notify("Escalation [manual_flag] esc_id=esc-1")

    assert len(captured) == 1
    call = captured[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://hooks.slack.com/services/ABC/DEF/xyz"
    assert call["json"] == {"text": "Escalation [manual_flag] esc_id=esc-1"}


async def test_notify_raises_on_non_2xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="oops")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        notifier = HttpxSlackNotifier(
            webhook_url="https://hooks.slack.com/x",
            http_client=client,
        )
        with pytest.raises(httpx.HTTPStatusError):
            await notifier.notify("test")
