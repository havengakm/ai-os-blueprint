"""HttpxSlackNotifier — POSTs Slack incoming-webhook messages.

Conforms to ``systems.beacon.reply.escalation.SlackNotifier``.

Slack incoming webhooks accept a simple ``{"text": "..."}`` JSON body.
This impl is deliberately minimal: no blocks, no attachments, no
emoji-formatted templates. The escalation runtime composes the
message; this notifier is just a transport.

Production wiring lives in ``api/deps.py``: when
``settings.slack_webhook_url`` is set, a notifier instance is
constructed; when unset, the EscalationRuntime is initialised with
``slack_notifier=None`` and skips the Slack path entirely (per the
"no-op gracefully if Slack webhook URL unset" acceptance from
Plan 2 Task 2.3.3).
"""
from __future__ import annotations

import httpx


class HttpxSlackNotifier:
    def __init__(
        self,
        *,
        webhook_url: str,
        http_client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        if not webhook_url:
            raise ValueError(
                "webhook_url is required; pass slack_notifier=None to disable"
            )
        self._webhook_url = webhook_url
        self._http_client = http_client
        self._provided_client = http_client is not None
        self._timeout = timeout_seconds

    async def notify(self, message: str) -> None:
        client = self._http_client
        owned = False
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout)
            owned = True
        try:
            resp = await client.post(self._webhook_url, json={"text": message})
            resp.raise_for_status()
        finally:
            if owned:
                await client.aclose()
