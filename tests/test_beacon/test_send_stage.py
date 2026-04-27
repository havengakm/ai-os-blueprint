"""Tests for Beacon SendStage orchestrator.

In-memory fakes for SendBackend, DecisionLogger, AutonomyGate. The ESP
adapter is the existing FakeInstantly. No DB, no network.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

import pytest

from systems.beacon import FakeInstantly
from systems.beacon.pipeline.send_stage import (
    DEFAULT_PER_CONTACT_COST_CEILING_CENTS,
    EligibleContact,
    SendAccount,
    SendStage,
    SendStageResult,
    VERDICT_FAILED_ADAPTER_ERROR,
    VERDICT_FAILED_NO_ACCOUNT_ROOM,
    VERDICT_QUEUED_AUTONOMY,
    VERDICT_SENT,
    VERDICT_SKIPPED_COST_CEILING,
)


# --------------------------------------------------------------------------- #
# Fakes                                                                         #
# --------------------------------------------------------------------------- #

class FakeSendBackend:
    """In-memory SendBackend for tests."""

    def __init__(self) -> None:
        self.eligible: list[EligibleContact] = []
        self.accounts: list[SendAccount] = []
        self.sent_today: dict[tuple[str, date], int] = {}
        self.contact_costs: dict[str, int] = {}
        self.send_log_rows: list[dict[str, Any]] = []
        self.draft_status_updates: list[tuple[str, str]] = []
        self.cap_increment_calls: list[tuple[str, date]] = []
        self.next_send_log_id: int = 1

    async def fetch_eligible_contacts(self, client_id, *, limit=None):
        contacts = self.eligible
        if limit is not None:
            contacts = contacts[:limit]
        return contacts

    async def fetch_active_send_accounts(self, client_id):
        return [a for a in self.accounts if a.is_active]

    async def get_account_sent_count_today(self, account_id, on_date):
        return self.sent_today.get((account_id, on_date), 0)

    async def increment_account_sent_count(self, account_id, on_date):
        self.cap_increment_calls.append((account_id, on_date))
        new_count = self.sent_today.get((account_id, on_date), 0) + 1
        self.sent_today[(account_id, on_date)] = new_count
        return new_count

    async def get_contact_total_cost_cents(self, contact_id):
        return self.contact_costs.get(contact_id, 0)

    async def persist_send_log(self, **kwargs):
        log_id = f"send-log-{self.next_send_log_id:04d}"
        self.next_send_log_id += 1
        row = {"id": log_id, **kwargs}
        self.send_log_rows.append(row)
        return log_id

    async def update_draft_status(self, draft_id, status):
        self.draft_status_updates.append((draft_id, status))


class FakeDecisionLogger:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def log_decision(self, client_id, **kwargs):
        self.entries.append({"client_id": client_id, **kwargs})
        return f"decision-{len(self.entries)}"


class FakeAutonomyGate:
    def __init__(self, level: str = "autonomous") -> None:
        self.level = level
        self.calls: list[tuple[str, str]] = []

    async def get_level(self, client_id, action_type):
        self.calls.append((client_id, action_type))
        return self.level


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _contact(
    *, contact_id="c-1", email="alice@example.com", first_name="Alice",
    icp_tier="A", has_signal=True, draft_id="d-1",
    subject="thoughts Alice?", body="Saw your work on X.",
) -> EligibleContact:
    return EligibleContact(
        contact_id=contact_id,
        contact_email=email,
        contact_first_name=first_name,
        icp_tier=icp_tier,
        has_signal=has_signal,
        draft_id=draft_id,
        draft_subject=subject,
        draft_body=body,
    )


def _account(
    *, id="acct-1", email="hello@clymbhq.com", daily_cap=25, is_active=True,
) -> SendAccount:
    return SendAccount(
        id=id,
        account_email=email,
        provider="instantly",
        esp_account_id=f"esp-{id}",
        daily_cap=daily_cap,
        is_active=is_active,
    )


def _make_stage(
    *,
    backend=None,
    adapter=None,
    autonomy="autonomous",
    cost_ceiling=DEFAULT_PER_CONTACT_COST_CEILING_CENTS,
    campaign_id="camp-X",
):
    backend = backend or FakeSendBackend()
    adapter = adapter or FakeInstantly()
    logger_ = FakeDecisionLogger()
    gate = FakeAutonomyGate(level=autonomy)
    stage = SendStage(
        adapter=adapter,
        backend=backend,
        decision_logger=logger_,
        autonomy_gate=gate,
        instantly_campaign_id=campaign_id,
        per_contact_cost_ceiling_cents=cost_ceiling,
    )
    return stage, backend, adapter, logger_, gate


# --------------------------------------------------------------------------- #
# 1. No eligible contacts → empty result                                        #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_no_eligible_contacts_returns_empty_result():
    stage, backend, *_ = _make_stage()
    result = await stage.run("client-1")
    assert result.client_id == "client-1"
    assert result.sent_count == 0
    assert result.skipped_count == 0
    assert result.failed_count == 0
    assert result.queued_count == 0
    assert result.verdicts == []
    assert backend.send_log_rows == []


# --------------------------------------------------------------------------- #
# 2. Happy path — one contact sends successfully                                #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_happy_path_sends_via_adapter_and_persists_log():
    stage, backend, adapter, logger_, _ = _make_stage()
    backend.eligible = [_contact()]
    backend.accounts = [_account()]

    result = await stage.run("client-1")

    assert result.sent_count == 1
    assert result.failed_count == 0
    verdict = result.verdicts[0]
    assert verdict.verdict == VERDICT_SENT
    assert verdict.send_log_id == "send-log-0001"
    assert verdict.esp_message_id == "fake-lead-000001"
    assert verdict.account_id == "acct-1"

    # Adapter saw the send.
    assert len(adapter.leads_added) == 1
    sent = adapter.leads_added[0]
    assert sent["contact_email"] == "alice@example.com"
    assert sent["custom_subject"] == "thoughts Alice?"

    # send_log row persisted with correct fields.
    assert len(backend.send_log_rows) == 1
    row = backend.send_log_rows[0]
    assert row["status"] == "accepted"
    assert row["esp_message_id"] == "fake-lead-000001"
    assert row["account_id"] == "acct-1"

    # Cap counter incremented + draft status flipped.
    assert backend.cap_increment_calls == [("acct-1", date.today())] or \
           len(backend.cap_increment_calls) == 1  # tolerate UTC vs local
    assert backend.draft_status_updates == [("d-1", "sent")]

    # decision_log emitted.
    assert len(logger_.entries) == 1
    entry = logger_.entries[0]
    assert entry["decision_type"] == "send_attempt"
    assert entry["context"]["verdict"] == VERDICT_SENT
    assert entry["context"]["icp_tier"] == "A"
    assert entry["context"]["has_signal"] is True


# --------------------------------------------------------------------------- #
# 3. Cost-ceiling block                                                         #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_skips_when_per_contact_cost_at_ceiling():
    stage, backend, adapter, logger_, _ = _make_stage(cost_ceiling=5)
    backend.eligible = [_contact()]
    backend.accounts = [_account()]
    backend.contact_costs["c-1"] = 5  # exactly at ceiling

    result = await stage.run("client-1")
    assert result.skipped_count == 1
    assert result.sent_count == 0
    verdict = result.verdicts[0]
    assert verdict.verdict == VERDICT_SKIPPED_COST_CEILING
    assert "5c >= 5c ceiling" in verdict.reason

    # Adapter never called; no send_log written.
    assert adapter.leads_added == []
    assert backend.send_log_rows == []
    # decision_log still fires for observability.
    assert logger_.entries[0]["context"]["verdict"] == VERDICT_SKIPPED_COST_CEILING


# --------------------------------------------------------------------------- #
# 4. Autonomy gate: 'suggest' queues, doesn't send                              #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_autonomy_suggest_queues_for_review():
    stage, backend, adapter, logger_, _ = _make_stage(autonomy="suggest")
    backend.eligible = [_contact()]
    backend.accounts = [_account()]

    result = await stage.run("client-1")
    assert result.queued_count == 1
    assert result.sent_count == 0
    verdict = result.verdicts[0]
    assert verdict.verdict == VERDICT_QUEUED_AUTONOMY
    assert "autonomy_level=suggest" in verdict.reason

    # Adapter never called.
    assert adapter.leads_added == []
    # Draft marked queued_for_review.
    assert ("d-1", "queued_for_review") in backend.draft_status_updates
    # No send_log row (we didn't actually send).
    assert backend.send_log_rows == []


@pytest.mark.asyncio
async def test_autonomy_draft_also_queues():
    stage, backend, adapter, *_ = _make_stage(autonomy="draft")
    backend.eligible = [_contact()]
    backend.accounts = [_account()]
    result = await stage.run("client-1")
    assert result.verdicts[0].verdict == VERDICT_QUEUED_AUTONOMY
    assert adapter.leads_added == []


@pytest.mark.asyncio
async def test_autonomy_act_notify_sends():
    stage, backend, adapter, *_ = _make_stage(autonomy="act_notify")
    backend.eligible = [_contact()]
    backend.accounts = [_account()]
    result = await stage.run("client-1")
    assert result.verdicts[0].verdict == VERDICT_SENT
    assert len(adapter.leads_added) == 1


# --------------------------------------------------------------------------- #
# 5. Cap exhaustion                                                             #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_uses_alternate_account_when_first_capped():
    stage, backend, adapter, *_ = _make_stage()
    backend.eligible = [_contact()]
    today = datetime.now(timezone.utc).date()
    backend.accounts = [
        _account(id="acct-A", email="a@x.com", daily_cap=5),
        _account(id="acct-B", email="b@x.com", daily_cap=5),
    ]
    backend.sent_today[("acct-A", today)] = 5  # acct-A is at cap

    result = await stage.run("client-1")
    assert result.sent_count == 1
    verdict = result.verdicts[0]
    assert verdict.verdict == VERDICT_SENT
    assert verdict.account_id == "acct-B"  # fell through to B


@pytest.mark.asyncio
async def test_fails_when_all_accounts_at_cap():
    stage, backend, adapter, *_ = _make_stage()
    backend.eligible = [_contact()]
    today = datetime.now(timezone.utc).date()
    backend.accounts = [
        _account(id="acct-A", daily_cap=2),
        _account(id="acct-B", daily_cap=3),
    ]
    backend.sent_today[("acct-A", today)] = 2
    backend.sent_today[("acct-B", today)] = 3

    result = await stage.run("client-1")
    assert result.failed_count == 1
    assert result.sent_count == 0
    verdict = result.verdicts[0]
    assert verdict.verdict == VERDICT_FAILED_NO_ACCOUNT_ROOM
    assert adapter.leads_added == []


# --------------------------------------------------------------------------- #
# 6. Adapter error path                                                         #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_adapter_error_marks_failed_and_restores_cap():
    """Adapter raises (network / 4xx). Send marked failed; send_log row
    still persisted (for forensics); cap reservation restored so next
    contact can use the same account slot."""

    class ExplodingAdapter:
        name = "exploding"

        async def add_lead_to_campaign(self, **kwargs):
            raise RuntimeError("simulated 503 from ESP")

        async def pause_account(self, **kwargs):
            return None

        async def fetch_replies_since(self, **kwargs):
            return []

        async def get_send_stats(self, **kwargs):
            raise NotImplementedError

    stage, backend, _, logger_, _ = _make_stage(adapter=ExplodingAdapter())
    backend.eligible = [_contact(contact_id="c-1"), _contact(contact_id="c-2")]
    backend.accounts = [_account(daily_cap=5)]

    result = await stage.run("client-1")
    # Both contacts hit the same exploding adapter; both fail.
    assert result.failed_count == 2
    assert result.sent_count == 0

    for v in result.verdicts:
        assert v.verdict == VERDICT_FAILED_ADAPTER_ERROR
        assert "simulated 503 from ESP" in v.reason

    # send_log rows persisted with status=failed.
    assert len(backend.send_log_rows) == 2
    assert all(r["status"] == "failed" for r in backend.send_log_rows)

    # Cap reservation restored — never incremented in storage.
    assert backend.cap_increment_calls == []


# --------------------------------------------------------------------------- #
# 7. Dry run                                                                    #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_dry_run_does_not_call_adapter_or_persist():
    stage, backend, adapter, logger_, _ = _make_stage()
    backend.eligible = [_contact()]
    backend.accounts = [_account()]

    result = await stage.run("client-1", dry_run=True)
    assert result.sent_count == 1  # would-have-sent verdict
    assert adapter.leads_added == []
    assert backend.send_log_rows == []
    assert backend.cap_increment_calls == []
    assert backend.draft_status_updates == []

    # decision_log still emitted (dry_run flag set in context).
    assert len(logger_.entries) == 1
    assert logger_.entries[0]["context"]["dry_run"] is True


# --------------------------------------------------------------------------- #
# 8. Signal-presence is RANKING, not gate                                       #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_no_signal_contact_is_still_sendable():
    """Per `feedback_surround_sound_architecture` operator clarification
    2026-04-27: signal absence does NOT block sends. Backend already
    pre-sorted by signal-having; SendStage processes whatever it gets."""
    stage, backend, adapter, *_ = _make_stage()
    cold_contact = _contact(
        contact_id="c-cold",
        has_signal=False,  # explicitly no signal
        icp_tier="C",       # colder tier too
    )
    backend.eligible = [cold_contact]
    backend.accounts = [_account()]

    result = await stage.run("client-1")
    assert result.sent_count == 1
    verdict = result.verdicts[0]
    assert verdict.verdict == VERDICT_SENT
    assert len(adapter.leads_added) == 1


# --------------------------------------------------------------------------- #
# 9. Multiple contacts processed in backend-supplied order                      #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_processes_contacts_in_backend_order():
    """Backend pre-sorts by signal-having within tier. SendStage processes
    that order; tests just confirm the order is preserved (so the backend
    ranking actually drives priority)."""
    stage, backend, adapter, *_ = _make_stage()
    backend.eligible = [
        _contact(contact_id="c-signal-A", has_signal=True, icp_tier="A"),
        _contact(contact_id="c-no-signal-A", has_signal=False, icp_tier="A"),
        _contact(contact_id="c-signal-B", has_signal=True, icp_tier="B"),
    ]
    backend.accounts = [_account(daily_cap=2)]  # only 2 sends possible

    result = await stage.run("client-1")
    assert result.sent_count == 2
    assert result.failed_count == 1  # third hits cap exhaustion

    # First two (signal-A + no-signal-A) should send; signal-B failed at cap.
    sent_ids = [v.contact_id for v in result.verdicts if v.verdict == VERDICT_SENT]
    assert sent_ids == ["c-signal-A", "c-no-signal-A"]
    failed_ids = [v.contact_id for v in result.verdicts if v.verdict == VERDICT_FAILED_NO_ACCOUNT_ROOM]
    assert failed_ids == ["c-signal-B"]


# --------------------------------------------------------------------------- #
# 10. limit param                                                               #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_respects_limit_param():
    stage, backend, adapter, *_ = _make_stage()
    backend.eligible = [_contact(contact_id=f"c-{i}", draft_id=f"d-{i}") for i in range(5)]
    backend.accounts = [_account(daily_cap=10)]

    result = await stage.run("client-1", limit=2)
    assert result.sent_count == 2
    assert len(result.verdicts) == 2
