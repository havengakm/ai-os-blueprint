"""Cool-off + round-based re-entry runtime.

Plan 2 Phase 3 Task 2.3.4. Per
``feedback_surround_sound_architecture``: contacts who don't reply
within a sequence enter 90-day cool-off, then re-enter as round 2 (or
3, or 4) with a different opening / hook / offer.

Two phases, runnable independently or together via ``run_cycle``:

  enter_cool_off_for_idle:
    Find contacts whose last send is ``idle_days`` ago AND no reply
    received. Mark status='cooling_off' + cool_off_until = now+90d.

  re_enter_after_cool_off:
    Find contacts in status='cooling_off' whose cool_off_until has
    passed. For each, sequence_round += 1 + status='ready' (back into
    the queue). When the new round would exceed ``max_rounds``,
    transition to status='dead' with reason='max_rounds_reached'
    instead.

Both phases emit ``decision_type='reply_handling'`` decision_log
entries with a ``transition`` field (``entered_cool_off`` /
``re_entered_round`` / ``marked_dead``) so the audit trail is queryable.

Variant-pool selection by sequence_round (round 2+ uses different
copy than round 1) is composer-side and lives in Plan 2 Phase 5
follow-up — a stub here would couple this runtime to the composer
unnecessarily.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

import structlog


log = structlog.get_logger(__name__)


# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #


# Cool-off duration before contact re-enters the queue.
DEFAULT_COOL_OFF_DAYS: int = 90

# Sequence completed without a reply this many days ago → eligible for cool-off.
# Equal to cool-off duration by default — together they describe a 180-day
# "no contact" window before round 2 attempt.
DEFAULT_IDLE_DAYS: int = 90

# Max sequence rounds before the contact is permanently archived.
# Per ``feedback_surround_sound_architecture``: 3-4 rounds. Default 4.
DEFAULT_MAX_ROUNDS: int = 4


# --------------------------------------------------------------------------- #
# Types                                                                        #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CoolOffContactRef:
    """Minimal projection of a contact needed for the cool-off transitions.
    Backend returns these from the find_* methods."""

    contact_id: str
    sequence_round: int
    client_id: str


@dataclass
class CoolOffEnterResult:
    cooled_off_count: int = 0


@dataclass
class CoolOffReEnterResult:
    re_entered_count: int = 0
    marked_dead_count: int = 0


@dataclass
class CoolOffCycleResult:
    cooled_off_count: int = 0
    re_entered_count: int = 0
    marked_dead_count: int = 0


# --------------------------------------------------------------------------- #
# Protocols                                                                    #
# --------------------------------------------------------------------------- #


class CoolOffBackend(Protocol):
    async def find_idle_contacts_for_cool_off(
        self, client_id: str, *, idle_days: int, now: datetime,
    ) -> list[CoolOffContactRef]:
        """Return contacts whose most recent outreach_send_log.sent_at is
        >= ``idle_days`` ago AND no outreach_reply received AND
        status='sent' (sequence finished). Excludes contacts already in
        cooling_off / dead / dnd / unsubscribed."""
        ...

    async def find_contacts_ready_to_re_enter(
        self, client_id: str, *, now: datetime,
    ) -> list[CoolOffContactRef]:
        """Return contacts in status='cooling_off' with cool_off_until <= now."""
        ...

    async def mark_contact_cooling_off(
        self, contact_id: str, *, cool_off_until: datetime,
    ) -> None:
        """Set status='cooling_off' + cool_off_until."""
        ...

    async def transition_to_next_round(
        self, contact_id: str, *, new_round: int,
    ) -> None:
        """Set sequence_round=new_round + status='ready' + cool_off_until=NULL."""
        ...

    async def mark_contact_dead(
        self, contact_id: str, *, reason: str,
    ) -> None:
        """Set status='dead' + record reason in raw_data."""
        ...


class DecisionLogger(Protocol):
    async def emit(
        self,
        *,
        client_id: str,
        decision_type: str,
        contact_id: str,
        payload: dict,
    ) -> None: ...


# --------------------------------------------------------------------------- #
# Runtime                                                                      #
# --------------------------------------------------------------------------- #


class CoolOffRuntime:
    def __init__(
        self,
        *,
        backend: CoolOffBackend,
        decision_logger: DecisionLogger,
        idle_days: int = DEFAULT_IDLE_DAYS,
        cool_off_days: int = DEFAULT_COOL_OFF_DAYS,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
    ) -> None:
        self._backend = backend
        self._logger = decision_logger
        self._idle_days = idle_days
        self._cool_off_days = cool_off_days
        self._max_rounds = max_rounds

    # ----- Phase A: enter cool-off ----------------------------------------- #

    async def enter_cool_off_for_idle(
        self, client_id: str, *, now: datetime,
    ) -> CoolOffEnterResult:
        idle_contacts = await self._backend.find_idle_contacts_for_cool_off(
            client_id, idle_days=self._idle_days, now=now,
        )
        cool_off_until = now + timedelta(days=self._cool_off_days)
        result = CoolOffEnterResult()

        for ref in idle_contacts:
            await self._backend.mark_contact_cooling_off(
                ref.contact_id, cool_off_until=cool_off_until,
            )
            await self._logger.emit(
                client_id=ref.client_id,
                decision_type="reply_handling",
                contact_id=ref.contact_id,
                payload={
                    "transition": "entered_cool_off",
                    "sequence_round": ref.sequence_round,
                    "cool_off_until": cool_off_until.isoformat(),
                },
            )
            result.cooled_off_count += 1

        return result

    # ----- Phase B: re-enter after cool-off -------------------------------- #

    async def re_enter_after_cool_off(
        self, client_id: str, *, now: datetime,
    ) -> CoolOffReEnterResult:
        ready_contacts = await self._backend.find_contacts_ready_to_re_enter(
            client_id, now=now,
        )
        result = CoolOffReEnterResult()

        for ref in ready_contacts:
            new_round = ref.sequence_round + 1
            if new_round > self._max_rounds:
                await self._backend.mark_contact_dead(
                    ref.contact_id, reason="max_rounds_reached",
                )
                await self._logger.emit(
                    client_id=ref.client_id,
                    decision_type="reply_handling",
                    contact_id=ref.contact_id,
                    payload={
                        "transition": "marked_dead",
                        "reason": "max_rounds_reached",
                        "final_round": ref.sequence_round,
                    },
                )
                result.marked_dead_count += 1
                continue

            await self._backend.transition_to_next_round(
                ref.contact_id, new_round=new_round,
            )
            await self._logger.emit(
                client_id=ref.client_id,
                decision_type="reply_handling",
                contact_id=ref.contact_id,
                payload={
                    "transition": "re_entered_round",
                    "previous_round": ref.sequence_round,
                    "new_round": new_round,
                },
            )
            result.re_entered_count += 1

        return result

    # ----- Combined cycle -------------------------------------------------- #

    async def run_cycle(
        self, client_id: str, *, now: datetime,
    ) -> CoolOffCycleResult:
        """One cycle = re-entries first (frees up the queue), then new
        cool-off entries. Order matters only for accounting; both phases
        are independent at the contact level."""
        re_entry = await self.re_enter_after_cool_off(client_id, now=now)
        enter = await self.enter_cool_off_for_idle(client_id, now=now)
        return CoolOffCycleResult(
            cooled_off_count=enter.cooled_off_count,
            re_entered_count=re_entry.re_entered_count,
            marked_dead_count=re_entry.marked_dead_count,
        )
