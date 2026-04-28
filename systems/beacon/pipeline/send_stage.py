"""Beacon send-stage orchestrator.

Plan 2 Phase 2 Task 2.2.3. Picks eligible contacts (already pre-filtered
to tier ∈ {A,B,C} + DND-clear + has draft by the storage backend),
gates each through:

  1. Per-contact cost ceiling (default 5c — Phase 4 will tighten)
  2. Autonomy level — queues for human review if 'suggest' / 'draft';
     sends if 'act_notify' / 'autonomous'
  3. Daily cap on chosen send_account (atomic increment)
  4. ESP adapter dispatch (Instantly v2)
  5. Persist outreach_send_log row + decision_log entry

NOT a gate: signal presence. Per `feedback_surround_sound_architecture`
(operator clarification 2026-04-27) signals affect SCORING + RANKING,
never send eligibility. No-signal contacts are sendable as a colder
list at lower priority within the same tier — they just have a
website-fallback icebreaker (tier-4 generation) instead of a
signal-driven hook.

The orchestrator is provider-agnostic via dependency injection:
ESPAdapter Protocol (Instantly today; Smartlead / PlusVibe later if
needed) + SendBackend Protocol (real Supabase impl is a follow-up).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Protocol

from systems.beacon.protocol import ESPAdapter


logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Constants                                                                     #
# --------------------------------------------------------------------------- #
DEFAULT_PER_CONTACT_COST_CEILING_CENTS = 5
SEND_ACTION_TYPE = "send_email"


# --------------------------------------------------------------------------- #
# Dataclasses — backend returns these                                           #
# --------------------------------------------------------------------------- #

@dataclass
class EligibleContact:
    """A contact ready for send. Backend pre-filters to tier ∈ {A,B,C} +
    DND-clear + has rendered draft + not already sent.

    ``has_signal`` is True if research_data has trigger_events or
    structural_signals — used by the backend for ranking (signal-having
    contacts go first within a tier), preserved here for decision_log
    context but NOT used by SendStage as a gate.
    """
    contact_id: str
    contact_email: str
    contact_first_name: str
    icp_tier: str                     # 'A' | 'B' | 'C'
    has_signal: bool
    draft_id: str
    draft_subject: str
    draft_body: str


@dataclass
class SendAccount:
    """A send account in the client's roster (subset of send_account row)."""
    id: str
    account_email: str
    provider: str                     # 'instantly' | 'smartlead' | ...
    esp_account_id: str | None
    daily_cap: int
    is_active: bool


# --------------------------------------------------------------------------- #
# Verdict + result                                                              #
# --------------------------------------------------------------------------- #

# Verdict values — one per contact processed.
# All values prefixed by category for easy grouping in decision_log queries.
VERDICT_SENT = "sent"
VERDICT_QUEUED_AUTONOMY = "queued:autonomy_suggest"
VERDICT_SKIPPED_COST_CEILING = "skipped:cost_ceiling"
VERDICT_FAILED_NO_ACCOUNT_ROOM = "failed:no_account_room"
VERDICT_FAILED_ADAPTER_ERROR = "failed:adapter_error"


@dataclass
class SendVerdict:
    """One contact's outcome from a single send-stage run."""
    contact_id: str
    verdict: str
    reason: str
    send_log_id: str | None = None
    esp_message_id: str | None = None
    account_id: str | None = None


@dataclass
class SendStageResult:
    """Aggregate result from one SendStage.run() call."""
    client_id: str
    sent_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    queued_count: int = 0
    verdicts: list[SendVerdict] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Backend protocols (DI surface)                                                #
# --------------------------------------------------------------------------- #

class SendBackend(Protocol):
    """Storage interface SendStage depends on. Real impl lives in
    `systems/beacon/storage/send_backend.py` (follow-up); tests use a
    FakeSendBackend that satisfies this Protocol."""

    async def fetch_eligible_contacts(
        self, client_id: str, *, limit: int | None = None,
    ) -> list[EligibleContact]:
        """Pre-filtered to tier in {A,B,C} + DND-clear + has rendered
        draft + not already sent. Ordered: signal-having first within
        the same tier."""
        ...

    async def fetch_active_send_accounts(
        self, client_id: str,
    ) -> list[SendAccount]:
        """Where is_active = TRUE."""
        ...

    async def get_account_sent_count_today(
        self, account_id: str, on_date: date,
    ) -> int:
        """Read send_caps_daily.sent_count for (account_id, on_date)."""
        ...

    async def increment_account_sent_count(
        self, account_id: str, on_date: date,
    ) -> int:
        """Atomic INSERT ... ON CONFLICT DO UPDATE SET sent_count = sent_count + 1.
        Returns the new count."""
        ...

    async def get_contact_total_cost_cents(
        self, contact_id: str,
    ) -> int:
        """Per-contact cost rollup for the cost-ceiling gate. v1: sum
        decision_log.context.cost_cents. Phase 4 ships a SQL view that
        replaces this with O(1) lookup."""
        ...

    async def persist_send_log(
        self,
        *,
        client_id: str,
        contact_id: str,
        draft_id: str,
        account_id: str,
        esp_message_id: str | None,
        status: str,
        error: str | None,
        cost_cents: int,
    ) -> str:
        """Insert outreach_send_log row. Returns the new id."""
        ...

    async def update_draft_status(
        self, draft_id: str, status: str,
    ) -> None:
        """Update outreach_drafts.status. Used to mark drafts as 'sent'
        or 'queued_for_review' as send proceeds."""
        ...


class DecisionLogger(Protocol):
    """Decision-log emit. Same shape used across Scout stages."""

    async def log_decision(
        self,
        client_id: str,
        *,
        decision_type: str,
        decision: str,
        reasoning: str,
        context: dict[str, Any],
        source: str,
        confidence: float | None = None,
    ) -> str:
        ...


class AutonomyGate(Protocol):
    """Autonomy-level lookup per (client, action_type)."""

    async def get_level(
        self, client_id: str, action_type: str,
    ) -> str:
        """Returns 'suggest' | 'draft' | 'act_notify' | 'autonomous'."""
        ...


# --------------------------------------------------------------------------- #
# Send stage                                                                    #
# --------------------------------------------------------------------------- #

class SendStage:
    """Orchestrates one send cycle for one client."""

    def __init__(
        self,
        *,
        adapter: ESPAdapter,
        backend: SendBackend,
        decision_logger: DecisionLogger,
        autonomy_gate: AutonomyGate,
        instantly_campaign_id: str,
        per_contact_cost_ceiling_cents: int = DEFAULT_PER_CONTACT_COST_CEILING_CENTS,
    ) -> None:
        self._adapter = adapter
        self._backend = backend
        self._decision_logger = decision_logger
        self._autonomy_gate = autonomy_gate
        self._campaign_id = instantly_campaign_id
        self._cost_ceiling = per_contact_cost_ceiling_cents

    async def run(
        self,
        client_id: str,
        *,
        dry_run: bool = False,
        limit: int | None = None,
    ) -> SendStageResult:
        """Run one send cycle for this client.

        Returns a SendStageResult with per-contact verdicts. dry_run skips
        adapter calls + DB writes but still emits decision_log entries
        (matching Scout's pattern).
        """
        result = SendStageResult(client_id=client_id)
        today = datetime.now(timezone.utc).date()

        contacts = await self._backend.fetch_eligible_contacts(
            client_id, limit=limit,
        )
        if not contacts:
            return result

        accounts = await self._backend.fetch_active_send_accounts(client_id)

        # Build per-account remaining-cap map. Only consulted in non-dry-run
        # paths but we read upfront so dry-run reports the same picture.
        account_caps: dict[str, int] = {}
        for acct in accounts:
            sent_today = await self._backend.get_account_sent_count_today(
                acct.id, today,
            )
            account_caps[acct.id] = max(0, acct.daily_cap - sent_today)

        autonomy = await self._autonomy_gate.get_level(client_id, SEND_ACTION_TYPE)

        for contact in contacts:
            verdict = await self._send_one(
                client_id=client_id,
                contact=contact,
                accounts=accounts,
                account_caps=account_caps,
                autonomy=autonomy,
                today=today,
                dry_run=dry_run,
            )
            result.verdicts.append(verdict)
            if verdict.verdict == VERDICT_SENT:
                result.sent_count += 1
            elif verdict.verdict.startswith("queued"):
                result.queued_count += 1
            elif verdict.verdict.startswith("skipped"):
                result.skipped_count += 1
            elif verdict.verdict.startswith("failed"):
                result.failed_count += 1

        return result

    async def _send_one(
        self,
        *,
        client_id: str,
        contact: EligibleContact,
        accounts: list[SendAccount],
        account_caps: dict[str, int],
        autonomy: str,
        today: date,
        dry_run: bool,
    ) -> SendVerdict:
        # Gate 1: per-contact cost ceiling. Cheap check before any send work.
        contact_cost = await self._backend.get_contact_total_cost_cents(
            contact.contact_id,
        )
        if contact_cost >= self._cost_ceiling:
            verdict = SendVerdict(
                contact_id=contact.contact_id,
                verdict=VERDICT_SKIPPED_COST_CEILING,
                reason=(
                    f"per-contact cost {contact_cost}c >= "
                    f"{self._cost_ceiling}c ceiling"
                ),
            )
            await self._emit_decision(client_id, contact, verdict, dry_run=dry_run)
            return verdict

        # Gate 2: autonomy. 'suggest' / 'draft' → queue for human review.
        if autonomy in ("suggest", "draft"):
            verdict = SendVerdict(
                contact_id=contact.contact_id,
                verdict=VERDICT_QUEUED_AUTONOMY,
                reason=f"autonomy_level={autonomy} — queued for human review",
            )
            if not dry_run:
                await self._backend.update_draft_status(
                    contact.draft_id, "queued_for_review",
                )
            await self._emit_decision(client_id, contact, verdict, dry_run=dry_run)
            return verdict

        # Gate 3: pick a send_account with cap room. First-fit on the
        # accounts list as ordered by the backend.
        chosen: SendAccount | None = None
        for acct in accounts:
            if account_caps.get(acct.id, 0) > 0:
                chosen = acct
                break

        if chosen is None:
            verdict = SendVerdict(
                contact_id=contact.contact_id,
                verdict=VERDICT_FAILED_NO_ACCOUNT_ROOM,
                reason="no active account has remaining daily cap",
            )
            await self._emit_decision(client_id, contact, verdict, dry_run=dry_run)
            return verdict

        # Reserve the cap slot in the local map (real DB increment happens
        # only on a successful adapter call below).
        account_caps[chosen.id] -= 1

        if dry_run:
            verdict = SendVerdict(
                contact_id=contact.contact_id,
                verdict=VERDICT_SENT,
                reason=f"dry_run — would have sent via {chosen.account_email}",
                account_id=chosen.id,
            )
            await self._emit_decision(client_id, contact, verdict, dry_run=True)
            return verdict

        # Adapter dispatch.
        try:
            esp_msg_id = await self._adapter.add_lead_to_campaign(
                campaign_id=self._campaign_id,
                contact_email=contact.contact_email,
                contact_first_name=contact.contact_first_name,
                custom_subject=contact.draft_subject,
                custom_body=contact.draft_body,
            )
        except Exception as exc:  # noqa: BLE001 — bubble all to verdict
            verdict = SendVerdict(
                contact_id=contact.contact_id,
                verdict=VERDICT_FAILED_ADAPTER_ERROR,
                reason=f"adapter raised {type(exc).__name__}: {exc}",
                account_id=chosen.id,
            )
            send_log_id = await self._backend.persist_send_log(
                client_id=client_id,
                contact_id=contact.contact_id,
                draft_id=contact.draft_id,
                account_id=chosen.id,
                esp_message_id=None,
                status="failed",
                error=verdict.reason,
                cost_cents=0,
            )
            verdict.send_log_id = send_log_id
            # Restore the cap reservation since the send didn't actually go.
            account_caps[chosen.id] += 1
            await self._emit_decision(client_id, contact, verdict, dry_run=False)
            return verdict

        # Success path: persist + atomic increment + draft status update.
        send_log_id = await self._backend.persist_send_log(
            client_id=client_id,
            contact_id=contact.contact_id,
            draft_id=contact.draft_id,
            account_id=chosen.id,
            esp_message_id=esp_msg_id,
            status="accepted",
            error=None,
            cost_cents=0,
        )
        await self._backend.increment_account_sent_count(chosen.id, today)
        await self._backend.update_draft_status(contact.draft_id, "sent")

        verdict = SendVerdict(
            contact_id=contact.contact_id,
            verdict=VERDICT_SENT,
            reason=f"sent via {chosen.account_email}",
            send_log_id=send_log_id,
            esp_message_id=esp_msg_id,
            account_id=chosen.id,
        )
        await self._emit_decision(client_id, contact, verdict, dry_run=False)
        return verdict

    async def _emit_decision(
        self,
        client_id: str,
        contact: EligibleContact,
        verdict: SendVerdict,
        *,
        dry_run: bool,
    ) -> None:
        await self._decision_logger.log_decision(
            client_id=client_id,
            decision_type="send_attempt",
            decision=f"send_attempt:{contact.contact_id}:{verdict.verdict}",
            reasoning=verdict.reason,
            context={
                "contact_id": contact.contact_id,
                "draft_id": contact.draft_id,
                "icp_tier": contact.icp_tier,
                "has_signal": contact.has_signal,
                "verdict": verdict.verdict,
                "send_log_id": verdict.send_log_id,
                "esp_message_id": verdict.esp_message_id,
                "account_id": verdict.account_id,
                "dry_run": dry_run,
            },
            source="system",
            confidence=None,
        )
