"""Shared dataclasses returned by ESP adapters.

Provider-agnostic shape. Adapter implementations (InstantlyAdapter,
FakeInstantly, future SmartleadAdapter) all return these types so the
Beacon orchestrator can swap providers without code changes downstream.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class Reply:
    """One inbound reply ingested from the ESP.

    Returned by ``ESPAdapter.fetch_replies_since(...)``. The Beacon Phase 3
    classifier reads ``body`` + ``subject`` to assign the
    ``outreach_reply.classification`` value.
    """

    esp_message_id: str            # this reply's own message ID at the ESP
    replied_to_message_id: str | None  # the message this is in response to (correlates to outreach_send_log.esp_message_id)
    from_email: str
    subject: str | None
    body: str
    received_at: datetime
    raw: dict[str, Any] = field(default_factory=dict)  # full ESP webhook payload


@dataclass
class SendStats:
    """Per-account / per-day send + delivery metrics.

    Returned by ``ESPAdapter.get_send_stats(...)``. Used by the Phase 4
    coverage dashboard + Phase 5 Optimizer's per-account ROI analysis.
    """

    esp_account_id: str
    on_date: date
    sent_count: int
    bounced_count: int
    replied_count: int
    open_rate: float | None  # 0.0-1.0; None if open tracking is disabled
