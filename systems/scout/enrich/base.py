"""Enrich package base contract — adapter protocol + result dataclass.

Every enrichment adapter must implement EnrichAdapter and return EnrichResult.
Adapters NEVER raise on business-level failures (e.g. invalid email, no phone
found). They raise ONLY on infrastructure errors (network timeout, auth failure)
which the orchestrator catches and logs as a miss. A business-level miss returns
ok=False with a reason describing why, and cost_cents for whatever was spent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


# --------------------------------------------------------------------------- #
# Result                                                                        #
# --------------------------------------------------------------------------- #

@dataclass
class EnrichResult:
    """What an enrich adapter returns per contact call.

    IMPORTANT for callers: ``ok`` indicates the API call completed (or was
    deliberately skipped), NOT that the business outcome was positive. Always
    check ``reason`` before using ``data``. Example: a ZeroBounce call on an
    invalid email returns ``ok=True`` (call succeeded) but ``reason="unsafe:invalid"``
    — the email is NOT deliverable and ``data["email_verified"]`` is False.
    """

    adapter_name: str
    ok: bool                        # True if API call completed or was skipped cleanly
    data: dict[str, Any]            # adapter-specific output fields
    cost_cents: int                 # ACTUAL cost of this call. Always >= 0.
    reason: str                     # business disposition — check before using data
    raw_response: dict[str, Any] = field(default_factory=dict)  # audit trail


# --------------------------------------------------------------------------- #
# Protocol                                                                      #
# --------------------------------------------------------------------------- #

class EnrichAdapter(Protocol):
    """Protocol every enrichment adapter must implement."""

    name: str
    cost_cents_per_call: int        # static price reference for tier-budget pre-checks

    async def enrich(
        self,
        contact: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> EnrichResult:
        """Enrich a single contact.

        contact dict is expected to have at minimum:
            contact_id: str  — for logging
            email: str       — for email-based adapters

        Raises on infrastructure errors only (network, auth). Never raises
        on business-level misses.
        """
        ...
