"""Per-contact 5c hard ceiling gate.

Plan 2 Phase 4 Task 2.4.3. LLM-spending pipeline stages call this gate
BEFORE making a billable call. When the contact has accumulated >=
ceiling cents of spend, the gate returns ``halted=True`` and the
caller skips further enrichment + transitions
``contacts.status='cost_ceiling_hit'`` (via ``check_and_mark``).

Ceiling sources, in order of precedence:

  1. Explicit ``ceiling_cents`` argument to ``check()`` — used when the
     caller has already looked up the per-tier override from
     ``client_config.per_contact_cost_ceiling_cents`` JSONB.
  2. Constructor ``default_ceiling_cents`` (default 5c).

Status-transition wiring:

  - ``check()`` is pure read; no DB writes.
  - ``check_and_mark()`` calls
    ``status_backend.mark_contact_cost_ceiling_hit`` when the contact
    is halted. Requires status_backend configured at init time;
    calling check_and_mark without one is a programmer error.

Wiring of the gate into the EnrichOrchestrator + Composer is a
follow-up commit — this module ships the capability + tests; each
caller-side wire-in lands in a focused, individually-reviewed change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


DEFAULT_PER_CONTACT_CEILING_CENTS: int = 5


# --------------------------------------------------------------------------- #
# Result                                                                      #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CeilingVerdict:
    halted: bool
    spent_cents: int
    ceiling_cents: int
    reason: str


# --------------------------------------------------------------------------- #
# Protocols                                                                   #
# --------------------------------------------------------------------------- #


class CeilingCostBackend(Protocol):
    """Lookup interface for per-contact accumulated spend. The Beacon
    ``SupabaseSendBackend`` already implements this method (via the
    migration 020 ``get_contact_cost`` RPC), so it can be plugged in
    directly when wiring into Scout-side stages."""

    async def get_contact_total_cost_cents(self, contact_id: str) -> int: ...


class CeilingStatusBackend(Protocol):
    """Optional — only needed for ``check_and_mark``. Real impl lives at
    ``systems/scout/supabase_backends/`` (lands with the wiring commit)."""

    async def mark_contact_cost_ceiling_hit(
        self,
        contact_id: str,
        *,
        spent_cents: int,
        ceiling_cents: int,
    ) -> None: ...


# --------------------------------------------------------------------------- #
# Gate                                                                        #
# --------------------------------------------------------------------------- #


class PerContactCeiling:
    def __init__(
        self,
        *,
        cost_backend: CeilingCostBackend,
        status_backend: CeilingStatusBackend | None = None,
        default_ceiling_cents: int = DEFAULT_PER_CONTACT_CEILING_CENTS,
    ) -> None:
        self._cost = cost_backend
        self._status = status_backend
        self._default = default_ceiling_cents

    async def check(
        self,
        contact_id: str,
        *,
        ceiling_cents: int | None = None,
    ) -> CeilingVerdict:
        spent = await self._cost.get_contact_total_cost_cents(contact_id)
        ceiling = ceiling_cents if ceiling_cents is not None else self._default
        halted = spent >= ceiling
        return CeilingVerdict(
            halted=halted,
            spent_cents=spent,
            ceiling_cents=ceiling,
            reason="ceiling_hit" if halted else "ok",
        )

    async def check_and_mark(
        self,
        contact_id: str,
        *,
        ceiling_cents: int | None = None,
    ) -> CeilingVerdict:
        if self._status is None:
            raise RuntimeError(
                "PerContactCeiling.check_and_mark() requires a status_backend; "
                "construct with status_backend=... or call check() instead."
            )
        verdict = await self.check(contact_id, ceiling_cents=ceiling_cents)
        if verdict.halted:
            await self._status.mark_contact_cost_ceiling_hit(
                contact_id,
                spent_cents=verdict.spent_cents,
                ceiling_cents=verdict.ceiling_cents,
            )
        return verdict
