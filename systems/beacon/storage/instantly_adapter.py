"""Instantly v2 API adapter.

Production ``ESPAdapter`` backend. Wraps Instantly's REST API; tests use
the in-memory ``FakeInstantly`` instead to avoid network + auth.

Endpoints (validated 2026-04-27 against ``developer.instantly.ai/llms.txt``):
  - ``POST /api/v2/leads/bulk`` — add leads (1000 per request)
  - ``POST /api/v2/campaigns/:id/pause`` (account-scoped pause is via the
    account API; the campaign pause is what's API-exposed today —
    account-pause endpoint is undocumented and stubbed for now)
  - ``GET /api/v2/emails`` — pull replies + emails (rate-limited 20 req/min)
  - Stats endpoint — Instantly exposes campaign analytics; per-account
    daily stats require aggregating ``GET /api/v2/emails`` results

Auth: ``Authorization: Bearer <api_key>`` header. Key lives in
``settings.instantly_api_key``.

Cost: $0 per API call (Instantly's API is included in the Growth plan
flat fee). The adapter's ``cost_cents_per_call`` is therefore 0; the
operational cost is the monthly Instantly subscription, not per-send.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import httpx

from systems.beacon.types import Reply, SendStats


logger = logging.getLogger(__name__)


INSTANTLY_BASE_URL = "https://api.instantly.ai"
DEFAULT_TIMEOUT = 30.0


class InstantlyAdapter:
    """Instantly v2 API client. ``name='instantly'``."""

    name: str = "instantly"

    def __init__(
        self,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
        base_url: str = INSTANTLY_BASE_URL,
    ) -> None:
        if not api_key:
            raise ValueError("instantly_api_key must be set")
        self._api_key = api_key
        self._http_client = http_client
        self._base_url = base_url
        self._client_provided = http_client is not None

    async def _client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=DEFAULT_TIMEOUT,
            )
        return self._http_client

    async def aclose(self) -> None:
        """Close the lazily-created httpx client. Idempotent.

        Tests that inject their own client are responsible for closing it.
        """
        if self._http_client is not None and not self._client_provided:
            try:
                await self._http_client.aclose()
            finally:
                self._http_client = None

    # ------------------------------------------------------------------ #
    # Adapter surface (ESPAdapter Protocol)                                #
    # ------------------------------------------------------------------ #

    async def add_lead_to_campaign(
        self,
        *,
        campaign_id: str,
        contact_email: str,
        contact_first_name: str,
        custom_subject: str,
        custom_body: str,
    ) -> str:
        """POST /api/v2/leads/bulk with a single-lead array.

        Per-lead custom fields ``custom_subject`` + ``custom_body`` are
        passed via the ``payload`` dict; the campaign template references
        them as ``{{custom_subject}}`` / ``{{custom_body}}`` merge fields.
        """
        client = await self._client()
        response = await client.post(
            "/api/v2/leads/bulk",
            json={
                "campaign_id": campaign_id,
                "leads": [
                    {
                        "email": contact_email,
                        "first_name": contact_first_name,
                        "payload": {
                            "custom_subject": custom_subject,
                            "custom_body": custom_body,
                        },
                    }
                ],
            },
        )
        response.raise_for_status()
        body = response.json()
        # Instantly returns ``{"leads": [{"id": "...", ...}]}``. We use the
        # lead id as the tracking handle persisted to outreach_send_log.
        leads = body.get("leads") or []
        if not leads:
            raise RuntimeError(
                f"Instantly add_lead returned empty leads array for "
                f"campaign={campaign_id}, email={contact_email}: {body!r}"
            )
        return str(leads[0]["id"])

    async def pause_account(
        self,
        *,
        esp_account_id: str,
        reason: str,
    ) -> None:
        """Pause sending from a specific email account.

        The Instantly v2 API account-pause endpoint isn't surfaced in the
        public llms.txt index (2026-04-27). Operator can pause manually
        via the UI in the meantime. This method is a stub returning
        cleanly so the orchestrator's auto-pause-on-bounce-spike feature
        (Phase 3+) can be wired without breaking on import.

        TODO: implement when Instantly exposes the account-pause REST
        endpoint OR when operator confirms a workable workaround
        (e.g. setting daily_cap to 0 via the campaign settings API).
        """
        logger.warning(
            "instantly.pause_account stubbed: esp_account_id=%s reason=%s. "
            "Operator must pause manually via Instantly UI until the v2 "
            "API exposes an account-pause endpoint.",
            esp_account_id, reason,
        )

    async def fetch_replies_since(
        self,
        *,
        since: datetime,
        limit: int = 100,
    ) -> list[Reply]:
        """GET /api/v2/emails with a received-after filter.

        Instantly's ``/api/v2/emails`` returns campaign emails + replies
        + manually sent. We filter to replies only (``email_type='reply'``
        per their API convention). Newest first, capped at ``limit``.
        """
        # Normalise to UTC ISO 8601 — Instantly expects ``YYYY-MM-DDTHH:MM:SSZ``.
        since_utc = since.astimezone(timezone.utc) if since.tzinfo else since.replace(tzinfo=timezone.utc)
        since_iso = since_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        client = await self._client()
        response = await client.get(
            "/api/v2/emails",
            params={
                "email_type": "reply",
                "received_after": since_iso,
                "limit": min(limit, 100),  # Instantly caps page size
            },
        )
        response.raise_for_status()
        body = response.json()
        items = body.get("items") or body.get("emails") or []

        replies: list[Reply] = []
        for item in items:
            received_str = item.get("received_at") or item.get("date")
            try:
                received_at = datetime.fromisoformat(received_str.replace("Z", "+00:00")) if received_str else datetime.now(timezone.utc)
            except (AttributeError, ValueError):
                received_at = datetime.now(timezone.utc)

            replies.append(
                Reply(
                    esp_message_id=str(item.get("id") or ""),
                    replied_to_message_id=item.get("reply_to_message_id") or item.get("in_reply_to"),
                    from_email=str(item.get("from_email") or item.get("from") or ""),
                    subject=item.get("subject"),
                    body=str(item.get("body") or item.get("text") or ""),
                    received_at=received_at,
                    raw=item,
                )
            )
        # Defensive sort — caller should be able to assume newest first.
        replies.sort(key=lambda r: r.received_at, reverse=True)
        return replies

    async def get_send_stats(
        self,
        *,
        esp_account_id: str,
        on_date: date,
    ) -> SendStats:
        """Per-account / per-day rollup.

        Instantly's v2 API exposes per-CAMPAIGN analytics directly but
        per-ACCOUNT-per-DAY stats require aggregating ``/api/v2/emails``
        results. v1 of this method does the aggregation; future work can
        switch to a dedicated stats endpoint if Instantly ships one.
        """
        client = await self._client()
        # Pull all emails sent from this account on the given date.
        date_iso = on_date.isoformat()  # YYYY-MM-DD
        response = await client.get(
            "/api/v2/emails",
            params={
                "from_account_id": esp_account_id,
                "sent_date": date_iso,
                "limit": 100,
            },
        )
        response.raise_for_status()
        body = response.json()
        items = body.get("items") or body.get("emails") or []

        sent = sum(1 for i in items if i.get("status") in ("sent", "delivered"))
        bounced = sum(1 for i in items if i.get("status") == "bounced")
        replied = sum(1 for i in items if i.get("had_reply") is True)
        opens = [i.get("opened_at") for i in items if i.get("opened_at")]
        open_rate = (len(opens) / sent) if sent > 0 else None

        return SendStats(
            esp_account_id=esp_account_id,
            on_date=on_date,
            sent_count=sent,
            bounced_count=bounced,
            replied_count=replied,
            open_rate=open_rate,
        )
