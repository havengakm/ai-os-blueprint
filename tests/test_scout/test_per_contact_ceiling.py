"""Plan 2 Phase 4 Task 2.4.3: PerContactCeiling tests.

Per-contact spend gate that LLM-spending stages call BEFORE making a
billable call. When the contact has already accumulated >= ceiling
cents of spend, the gate returns ``halted=True`` and the caller skips
further enrichment for that contact + transitions
``contacts.status='cost_ceiling_hit'``.

Default ceiling is 5c; can be overridden per-call (e.g. from
``client_config.per_contact_cost_ceiling_cents`` JSONB).
"""
from __future__ import annotations

import pytest

from systems.scout.budget.per_contact_ceiling import (
    CeilingVerdict,
    DEFAULT_PER_CONTACT_CEILING_CENTS,
    PerContactCeiling,
)


# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #


class FakeCostBackend:
    def __init__(self, costs: dict[str, int] | None = None) -> None:
        self._costs = costs or {}

    async def get_contact_total_cost_cents(self, contact_id: str) -> int:
        return self._costs.get(contact_id, 0)


class FakeStatusBackend:
    def __init__(self) -> None:
        self.marked: list[dict] = []

    async def mark_contact_cost_ceiling_hit(
        self, contact_id: str, *, spent_cents: int, ceiling_cents: int,
    ) -> None:
        self.marked.append(
            {
                "contact_id": contact_id,
                "spent_cents": spent_cents,
                "ceiling_cents": ceiling_cents,
            }
        )


# --------------------------------------------------------------------------- #
# Constants sanity                                                            #
# --------------------------------------------------------------------------- #


def test_default_ceiling_is_5_cents():
    """Per CLAUDE.md cost discipline + Plan 2 doc: 5c per-contact ceiling."""
    assert DEFAULT_PER_CONTACT_CEILING_CENTS == 5


# --------------------------------------------------------------------------- #
# .check() — pure read, no side effects                                       #
# --------------------------------------------------------------------------- #


async def test_check_passes_when_spent_below_ceiling():
    cost = FakeCostBackend(costs={"u1": 2})
    ceiling = PerContactCeiling(cost_backend=cost)

    v = await ceiling.check("u1")

    assert isinstance(v, CeilingVerdict)
    assert v.halted is False
    assert v.spent_cents == 2
    assert v.ceiling_cents == 5
    assert v.reason == "ok"


async def test_check_halts_when_spent_at_ceiling():
    """At-ceiling is halt: 5c spent and ceiling 5c → next call would
    push over, so halt now."""
    cost = FakeCostBackend(costs={"u1": 5})
    ceiling = PerContactCeiling(cost_backend=cost)

    v = await ceiling.check("u1")
    assert v.halted is True
    assert v.spent_cents == 5
    assert v.reason == "ceiling_hit"


async def test_check_halts_when_spent_exceeds_ceiling():
    cost = FakeCostBackend(costs={"u1": 8})
    ceiling = PerContactCeiling(cost_backend=cost)

    v = await ceiling.check("u1")
    assert v.halted is True
    assert v.spent_cents == 8


async def test_check_passes_when_no_spend_history():
    cost = FakeCostBackend(costs={})
    ceiling = PerContactCeiling(cost_backend=cost)

    v = await ceiling.check("u-fresh")
    assert v.halted is False
    assert v.spent_cents == 0


async def test_check_uses_per_call_override_for_ceiling():
    """Caller can pass a ceiling_cents arg to override the default —
    used when client_config.per_contact_cost_ceiling_cents has a
    per-tier override."""
    cost = FakeCostBackend(costs={"u1": 7})
    ceiling = PerContactCeiling(cost_backend=cost, default_ceiling_cents=5)

    # u1 has 7c spent; default ceiling 5c → halted.
    v_default = await ceiling.check("u1")
    assert v_default.halted is True

    # Override to 10c for this call → not halted.
    v_override = await ceiling.check("u1", ceiling_cents=10)
    assert v_override.halted is False
    assert v_override.ceiling_cents == 10


async def test_check_with_zero_ceiling_always_halts():
    """ceiling_cents=0 means 'no further LLM spend allowed' — halts
    even on a fresh contact. Edge case for operator-driven freezes."""
    cost = FakeCostBackend(costs={"u1": 0})
    ceiling = PerContactCeiling(cost_backend=cost)

    v = await ceiling.check("u1", ceiling_cents=0)
    assert v.halted is True
    assert v.spent_cents == 0
    assert v.ceiling_cents == 0


async def test_check_does_not_mark_status():
    """check() is pure read — doesn't transition contact status. The
    caller decides whether to call check_and_mark()."""
    cost = FakeCostBackend(costs={"u1": 99})
    status = FakeStatusBackend()
    ceiling = PerContactCeiling(cost_backend=cost, status_backend=status)

    await ceiling.check("u1")
    assert status.marked == []


# --------------------------------------------------------------------------- #
# .check_and_mark() — read + status transition on halt                        #
# --------------------------------------------------------------------------- #


async def test_check_and_mark_transitions_status_when_halted():
    cost = FakeCostBackend(costs={"u1": 7})
    status = FakeStatusBackend()
    ceiling = PerContactCeiling(cost_backend=cost, status_backend=status)

    v = await ceiling.check_and_mark("u1")
    assert v.halted is True
    assert status.marked == [
        {"contact_id": "u1", "spent_cents": 7, "ceiling_cents": 5}
    ]


async def test_check_and_mark_does_not_transition_when_passing():
    cost = FakeCostBackend(costs={"u1": 2})
    status = FakeStatusBackend()
    ceiling = PerContactCeiling(cost_backend=cost, status_backend=status)

    v = await ceiling.check_and_mark("u1")
    assert v.halted is False
    assert status.marked == []


async def test_check_and_mark_without_status_backend_raises():
    """check_and_mark requires a status_backend; calling it without
    one configured is a programmer error, not a runtime fall-through."""
    cost = FakeCostBackend(costs={"u1": 7})
    ceiling = PerContactCeiling(cost_backend=cost)  # no status_backend

    with pytest.raises(RuntimeError) as exc:
        await ceiling.check_and_mark("u1")
    assert "status_backend" in str(exc.value)
