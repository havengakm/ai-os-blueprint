"""Beacon — the email send + reply agent.

Plan 2 Phase 2 onwards. Wraps the chosen ESP (Instantly v2 API) and turns
``outreach_drafts`` rows into actual sends, then ingests replies via webhook
+ classifies them.

Public exports:
  - ``ESPAdapter`` Protocol — every ESP backend implements this.
  - ``Reply`` / ``SendStats`` — adapter return types.
  - ``InstantlyAdapter`` — production backend (httpx + Instantly v2 API).
  - ``FakeInstantly`` — in-memory backend for tests.
"""
from __future__ import annotations

from systems.beacon.protocol import ESPAdapter
from systems.beacon.storage.fake_instantly import FakeInstantly
from systems.beacon.storage.instantly_adapter import InstantlyAdapter
from systems.beacon.types import Reply, SendStats

__all__ = [
    "ESPAdapter",
    "FakeInstantly",
    "InstantlyAdapter",
    "Reply",
    "SendStats",
]
