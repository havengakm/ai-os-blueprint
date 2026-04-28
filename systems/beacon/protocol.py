"""ESP adapter protocol.

Every ESP backend (Instantly today, Smartlead / PlusVibe.ai later if
needed) implements this Protocol. The Beacon orchestrator (Phase 2 Task
2.2.3) depends on this contract, not on concrete adapters.

The four methods come from the Plan 2 Phase 2 Task 2.2.2 spec:
  1. ``add_lead_to_campaign`` — inject a personalised lead into an
     existing ESP campaign. Returns the ESP-side identifier we'll
     persist as ``outreach_send_log.esp_message_id``.
  2. ``pause_account`` — pause sending from a specific email account
     (used when bounce-rate spikes etc.).
  3. ``fetch_replies_since`` — pull recent replies for the Beacon Phase 3
     classifier.
  4. ``get_send_stats`` — per-account / per-day rollup for Phase 4
     coverage + Phase 5 ROI analysis.

Adapter signatures use ESP-side identifiers (campaign_id,
esp_account_id). The orchestrator handles AIOS-to-ESP mapping using the
``send_account.esp_account_id`` column.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from systems.beacon.types import Reply, SendStats


class ESPAdapter(Protocol):
    """Protocol every ESP backend must implement."""

    name: str  # e.g. "instantly" or "smartlead"

    async def add_lead_to_campaign(
        self,
        *,
        campaign_id: str,
        contact_email: str,
        contact_first_name: str,
        custom_subject: str,
        custom_body: str,
    ) -> str:
        """Inject one personalised lead into an existing ESP campaign.

        Per-lead merge fields (subject + body) are passed through the
        ESP's custom-fields mechanism so the campaign's templated
        message references ``{{custom_subject}}`` / ``{{custom_body}}``.

        Returns the ESP-side identifier that ``outreach_send_log`` will
        persist as ``esp_message_id`` for webhook correlation.

        Raises on infrastructure errors (network, auth, ESP 5xx).
        Returns normally for business-level rejections (ESP 4xx like
        invalid email — the orchestrator marks the send as ``failed``).
        """
        ...

    async def pause_account(
        self,
        *,
        esp_account_id: str,
        reason: str,
    ) -> None:
        """Pause sending from a specific email account at the ESP.

        Reason is a free-text string for operator-facing notes (will
        appear in ``send_account.notes`` after the pause is persisted).
        """
        ...

    async def fetch_replies_since(
        self,
        *,
        since: datetime,
        limit: int = 100,
    ) -> list[Reply]:
        """Pull replies received after ``since`` (UTC). Newest first.

        For Instantly: paginated GET against ``/api/v2/emails`` with a
        received-after filter. Rate-limited to 20 req/min — the adapter
        does NOT internally retry / spread; that's the Phase 3 reply-
        ingest worker's responsibility.
        """
        ...

    async def get_send_stats(
        self,
        *,
        esp_account_id: str,
        on_date: date,
    ) -> SendStats:
        """Return sent / bounced / replied counts for one account on
        one calendar date. Used by the coverage dashboard and Optimizer
        weekly review.
        """
        ...
