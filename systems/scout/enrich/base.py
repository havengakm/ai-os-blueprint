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
    """What an enrich adapter returns per contact call."""

    adapter_name: str
    ok: bool                        # True if the API call completed successfully
    data: dict[str, Any]            # adapter-specific output fields
    cost_cents: int                 # ACTUAL cost of this call. Always >= 0.
    reason: str                     # human-readable disposition
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
