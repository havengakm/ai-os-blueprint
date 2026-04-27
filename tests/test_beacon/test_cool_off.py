"""Plan 2 Phase 3 Task 2.3.4: CoolOffRuntime tests.

Two phases:

  enter_cool_off_for_idle — contacts with status='sent' whose most
    recent outreach_send_log.sent_at is >= idle_days ago AND no reply
    in outreach_reply transition to status='cooling_off' with
    cool_off_until = now + 90 days.

  re_enter_after_cool_off — contacts in status='cooling_off' whose
    cool_off_until has passed get sequence_round += 1 and status reset
    to 'ready' for a fresh send cycle. If the new round would exceed
    max_rounds (default 4), the contact is marked status='dead' with
    reason='max_rounds_reached' instead.

Both phases emit ``decision_type='reply_handling'`` decision_log
entries so the audit trail is preserved.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from systems.beacon.reply.cool_off import (
    CoolOffContactRef,
    CoolOffRuntime,
    DEFAULT_IDLE_DAYS,
    DEFAULT_MAX_ROUNDS,
)


# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #


@dataclass
class _FakeContactState:
    contact_id: str
    sequence_round: int
    status: str
    cool_off_until: datetime | None = None


class FakeCoolOffBackend:
    def __init__(
        self,
        idle: list[CoolOffContactRef] | None = None,
        ready: list[CoolOffContactRef] | None = None,
    ) -> None:
        self._idle = idle or []
        self._ready = ready or []
        self.cool_off_marks: list[dict] = []
        self.round_transitions: list[dict] = []
        self.dead_marks: list[dict] = []

    async def find_idle_contacts_for_cool_off(
        self, client_id: str, *, idle_days: int, now: datetime,
    ) -> list[CoolOffContactRef]:
        return list(self._idle)

    async def find_contacts_ready_to_re_enter(
        self, client_id: str, *, now: datetime,
    ) -> list[CoolOffContactRef]:
        return list(self._ready)

    async def mark_contact_cooling_off(
        self, contact_id: str, *, cool_off_until: datetime,
    ) -> None:
        self.cool_off_marks.append(
            {"contact_id": contact_id, "cool_off_until": cool_off_until}
        )

    async def transition_to_next_round(
        self, contact_id: str, *, new_round: int,
    ) -> None:
        self.round_transitions.append(
            {"contact_id": contact_id, "new_round": new_round}
        )

    async def mark_contact_dead(
        self, contact_id: str, *, reason: str,
    ) -> None:
        self.dead_marks.append(
            {"contact_id": contact_id, "reason": reason}
        )


class FakeDecisionLogger:
    def __init__(self) -> None:
        self.emits: list[dict] = []

    async def emit(self, **kwargs):
        self.emits.append(kwargs)


def _runtime(*, idle=None, ready=None, max_rounds=DEFAULT_MAX_ROUNDS):
    backend = FakeCoolOffBackend(idle=idle, ready=ready)
    logger = FakeDecisionLogger()
    return (
        CoolOffRuntime(
            backend=backend,
            decision_logger=logger,
            max_rounds=max_rounds,
        ),
        backend,
        logger,
    )


def _now() -> datetime:
    return datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# enter_cool_off_for_idle                                                     #
# --------------------------------------------------------------------------- #


async def test_enter_cool_off_for_idle_marks_contacts():
    idle = [
        CoolOffContactRef(contact_id="u1", sequence_round=1, client_id="c1"),
        CoolOffContactRef(contact_id="u2", sequence_round=1, client_id="c1"),
    ]
    runtime, backend, logger = _runtime(idle=idle)

    now = _now()
    result = await runtime.enter_cool_off_for_idle("c1", now=now)

    assert result.cooled_off_count == 2
    assert len(backend.cool_off_marks) == 2
    expected_until = now + timedelta(days=90)
    for mark in backend.cool_off_marks:
        assert mark["cool_off_until"] == expected_until


async def test_enter_cool_off_emits_decision_log():
    idle = [CoolOffContactRef(contact_id="u1", sequence_round=1, client_id="c1")]
    runtime, _, logger = _runtime(idle=idle)

    await runtime.enter_cool_off_for_idle("c1", now=_now())

    assert len(logger.emits) == 1
    emit = logger.emits[0]
    assert emit["decision_type"] == "reply_handling"
    assert emit["contact_id"] == "u1"
    assert emit["payload"]["transition"] == "entered_cool_off"
    assert emit["payload"]["sequence_round"] == 1


async def test_enter_cool_off_no_idle_contacts_is_noop():
    runtime, backend, logger = _runtime(idle=[])
    result = await runtime.enter_cool_off_for_idle("c1", now=_now())
    assert result.cooled_off_count == 0
    assert backend.cool_off_marks == []
    assert logger.emits == []


# --------------------------------------------------------------------------- #
# re_enter_after_cool_off                                                     #
# --------------------------------------------------------------------------- #


async def test_re_entry_increments_sequence_round_and_emits():
    ready = [
        CoolOffContactRef(contact_id="u1", sequence_round=1, client_id="c1"),
        CoolOffContactRef(contact_id="u2", sequence_round=2, client_id="c1"),
    ]
    runtime, backend, logger = _runtime(ready=ready)

    result = await runtime.re_enter_after_cool_off("c1", now=_now())

    assert result.re_entered_count == 2
    assert backend.round_transitions == [
        {"contact_id": "u1", "new_round": 2},
        {"contact_id": "u2", "new_round": 3},
    ]
    assert backend.dead_marks == []

    transitions = [
        e for e in logger.emits if e["payload"]["transition"] == "re_entered_round"
    ]
    assert len(transitions) == 2
    assert transitions[0]["payload"]["new_round"] == 2


async def test_re_entry_marks_dead_when_max_rounds_reached():
    """A contact at sequence_round=4 (default max) being re-entered would
    move to round 5, which exceeds the cap. Mark dead instead."""
    ready = [
        CoolOffContactRef(contact_id="u1", sequence_round=4, client_id="c1"),
    ]
    runtime, backend, logger = _runtime(ready=ready, max_rounds=4)

    result = await runtime.re_enter_after_cool_off("c1", now=_now())

    assert result.re_entered_count == 0
    assert result.marked_dead_count == 1
    assert backend.round_transitions == []
    assert backend.dead_marks == [
        {"contact_id": "u1", "reason": "max_rounds_reached"}
    ]
    dead_emits = [
        e for e in logger.emits if e["payload"]["transition"] == "marked_dead"
    ]
    assert len(dead_emits) == 1
    assert dead_emits[0]["payload"]["reason"] == "max_rounds_reached"


async def test_re_entry_no_ready_contacts_is_noop():
    runtime, backend, _ = _runtime(ready=[])
    result = await runtime.re_enter_after_cool_off("c1", now=_now())
    assert result.re_entered_count == 0
    assert result.marked_dead_count == 0
    assert backend.round_transitions == []
    assert backend.dead_marks == []


async def test_re_entry_with_custom_max_rounds():
    """Operator can shrink the cap to 2 — round=2 contact should die on
    re-entry instead of advancing to round 3."""
    ready = [
        CoolOffContactRef(contact_id="u1", sequence_round=2, client_id="c1"),
    ]
    runtime, backend, _ = _runtime(ready=ready, max_rounds=2)
    result = await runtime.re_enter_after_cool_off("c1", now=_now())
    assert result.marked_dead_count == 1
    assert backend.dead_marks[0]["contact_id"] == "u1"


# --------------------------------------------------------------------------- #
# run_cycle (both phases)                                                     #
# --------------------------------------------------------------------------- #


async def test_run_cycle_does_both_phases():
    idle = [CoolOffContactRef(contact_id="u-idle", sequence_round=1, client_id="c1")]
    ready = [CoolOffContactRef(contact_id="u-ready", sequence_round=2, client_id="c1")]
    runtime, backend, _ = _runtime(idle=idle, ready=ready)

    result = await runtime.run_cycle("c1", now=_now())

    assert result.cooled_off_count == 1
    assert result.re_entered_count == 1
    assert result.marked_dead_count == 0
    assert len(backend.cool_off_marks) == 1
    assert len(backend.round_transitions) == 1


# --------------------------------------------------------------------------- #
# Constants sanity                                                            #
# --------------------------------------------------------------------------- #


def test_default_idle_days_is_90():
    """Per feedback_surround_sound_architecture: 90-day cool-off."""
    assert DEFAULT_IDLE_DAYS == 90


def test_default_max_rounds_is_4():
    """Per feedback_surround_sound_architecture: 'Max 3-4 rounds before dead'."""
    assert DEFAULT_MAX_ROUNDS == 4
