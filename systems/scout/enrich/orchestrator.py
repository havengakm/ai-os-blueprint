"""Enrich orchestrator — tier-gated fan-out dispatch across enrichment adapters.

Unlike the identity orchestrator (waterfall / first-hit-wins), the enrich
orchestrator fans out: for a given tier, it runs ALL the appropriate adapters
in a defined order, merges their results, and returns every result.

Tier order matters: signal adapters (Trigify + Claude web-search triggers)
run BEFORE heavy research (Claude deep research) so the research extraction
prompt has trigger context available. See backlog item 31 in
`docs/superpowers/plans/follow-ups-plan1.md` for the scope decision.

This is NOT a pipeline stage — no BaseSystem, no foundation loading. That
lives in Task 12d (`EnrichStage`). This class is a pure dispatcher with
tier-budget accounting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Protocol

from systems.scout.enrich.base import EnrichAdapter, EnrichResult

if TYPE_CHECKING:
    from os.foundation.decision_logger import DecisionLogger


# --------------------------------------------------------------------------- #
# Tier → ordered adapter list                                                   #
# --------------------------------------------------------------------------- #
#
# Order within a tier matters: signal adapters (trigify, claude_web_triggers)
# run BEFORE heavy research (claude_deep_research) so the research extraction
# prompt has trigger context available.
#
# claude_research (light-touch) is the tier-D fallback. It is NOT used when
# deep research runs (tiers A/B).
TIER_ADAPTERS: dict[str, list[str]] = {
    "A": ["zerobounce", "trigify", "claude_web_triggers", "apollo_enrich", "claude_deep_research"],
    "B": ["zerobounce", "trigify", "claude_web_triggers", "apollo_enrich", "claude_deep_research"],
    "C": ["zerobounce", "trigify", "claude_research"],
    "D": ["zerobounce", "claude_research"],
}

# Final decision-type label for the enrich stage. Added to the
# decision_log.decision_type CHECK constraint by
# scripts/sql/005_foundation_completion.sql (Task 12.5).
_DECISION_TYPE: Final[str] = "enrich_contact"


# --------------------------------------------------------------------------- #
# Budget tracker protocol                                                       #
# --------------------------------------------------------------------------- #

class BudgetTracker(Protocol):
    """Tier-budget accounting. Orchestrator consults before each adapter call.

    Zero or negative remaining means exhausted — orchestrator auto-pauses the
    remaining adapters for that (client_id, tier) pair. Positive means at
    least one more call is allowed.
    """

    async def remaining_cents(self, client_id: str, tier: str) -> int:
        """Return remaining cents of budget for this (client_id, tier).

        Zero or negative means exhausted — orchestrator will auto-pause.
        Positive means at-least-one-call allowed.
        """
        ...

    async def record_spend(self, client_id: str, tier: str, cents: int) -> None:
        """Debit `cents` from the tier budget.

        Called AFTER each completed adapter call. Not called when the adapter
        raised an exception (budget is not debited for infra failures).
        """
        ...


# --------------------------------------------------------------------------- #
# Result                                                                        #
# --------------------------------------------------------------------------- #

@dataclass
class EnrichOrchestratorResult:
    """What the orchestrator returns per (contact, tier) call."""

    contact_id: str
    tier: str
    adapter_results: dict[str, EnrichResult] = field(default_factory=dict)
    # Only adapters that actually ran and returned a result are in adapter_results.
    skipped: dict[str, str] = field(default_factory=dict)
    # adapter_name -> reason ("tier_gate" | "unknown_tier" | "not_supplied"
    # | "budget_exhausted" | "budget_tracker_error:{ExceptionType}"
    # | "adapter_error:{ExceptionType}")
    total_cost_cents: int = 0
    budget_exhausted: bool = False
    # True if we auto-paused before completing the tier's adapter list.


# --------------------------------------------------------------------------- #
# Orchestrator                                                                  #
# --------------------------------------------------------------------------- #

class EnrichOrchestrator:
    """Tier-gated fan-out dispatch across enrichment adapters.

    For a given (client_id, tier, contact), runs every adapter that matches
    the tier in the defined order. Consults the budget tracker before each
    call and auto-pauses when the tier's budget is exhausted.
    """

    def __init__(
        self,
        adapters: list[EnrichAdapter],
        budget_tracker: BudgetTracker,
        decision_logger: "DecisionLogger | None" = None,
        tier_adapters: dict[str, list[str]] | None = None,
    ) -> None:
        """
        adapters: list of EnrichAdapter instances. Any subset is allowed;
                  adapters named in `tier_adapters` but not supplied are
                  skipped silently (the stage layer should surface config
                  mismatches).
        budget_tracker: consulted before each adapter call; debited after.
        decision_logger: if provided, logs one entry per adapter call plus
                         one per auto-pause event.
        tier_adapters: override for tests; defaults to module-level TIER_ADAPTERS.
        """
        self._adapters: dict[str, EnrichAdapter] = {a.name: a for a in adapters}
        self._budget_tracker = budget_tracker
        self._decision_logger = decision_logger
        self._tier_adapters = tier_adapters if tier_adapters is not None else TIER_ADAPTERS

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def enrich_contact(
        self,
        client_id: str,
        contact: dict[str, Any],
        tier: str,
        *,
        dry_run: bool = False,
    ) -> EnrichOrchestratorResult:
        """Run all adapters that match `tier` on `contact`, in tier order.

        Always returns an EnrichOrchestratorResult. Never propagates an
        adapter exception — every adapter gets its own try/except and the
        fan-out continues.
        """
        contact_id = str(contact.get("contact_id", "<unknown>"))

        # --- unknown-tier guard ------------------------------------------
        if tier not in self._tier_adapters:
            skipped = {name: "unknown_tier" for name in self._adapters}
            await self._log_unknown_tier(
                client_id=client_id,
                contact_id=contact_id,
                tier=tier,
            )
            return EnrichOrchestratorResult(
                contact_id=contact_id,
                tier=tier,
                adapter_results={},
                skipped=skipped,
                total_cost_cents=0,
                budget_exhausted=False,
            )

        # --- build tier-ordered adapter list -----------------------------
        tier_names = self._tier_adapters[tier]
        result = EnrichOrchestratorResult(
            contact_id=contact_id,
            tier=tier,
            adapter_results={},
            skipped={},
            total_cost_cents=0,
            budget_exhausted=False,
        )

        # Adapters named in tier_adapters[tier] but not supplied to the
        # orchestrator are marked "not_supplied" with no log entry — this
        # is a config mismatch the stage layer should surface.
        for name in tier_names:
            if name not in self._adapters:
                result.skipped[name] = "not_supplied"

        budget_stop_logged = False
        # Set on first tracker error within this call; subsequent skipped
        # adapters get the same bucketed reason for consistency.
        tracker_error_type: str | None = None

        for name in tier_names:
            if name not in self._adapters:
                continue

            adapter = self._adapters[name]

            # --- budget check ----------------------------------------
            #
            # We consult the budget BEFORE every call, including zero-cost
            # adapters. This is intentional:
            #
            # - For a paid adapter (cost >= 1), `remaining < cost` triggers
            #   auto-pause. A budget of 0 stops all paid adapters.
            # - For a zero-cost adapter (cost == 0, e.g. Trigify),
            #   `remaining < 0` is the trigger. Budget of 0 still allows
            #   the zero-cost adapter to run (0 < 0 is False). This keeps
            #   free signal-gathering going even when paid budget is
            #   exhausted — desirable behaviour for continuous signal
            #   capture.
            if result.budget_exhausted:
                # Already auto-paused on a prior adapter; skip remainder.
                # Bucket skip reason by whichever path tripped us.
                if tracker_error_type is not None:
                    result.skipped[name] = f"budget_tracker_error:{tracker_error_type}"
                else:
                    result.skipped[name] = "budget_exhausted"
                continue

            try:
                remaining = await self._budget_tracker.remaining_cents(client_id, tier)
                tracker_failed = False
            except Exception as exc:
                # A budget-tracker failure should NOT silently pass adapters
                # through. Treat as budget-exhausted (fail safe) but surface
                # the tracker error separately in skip reason + log entry.
                remaining = -1
                tracker_failed = True
                tracker_error_type = type(exc).__name__

            if remaining < adapter.cost_cents_per_call:
                if tracker_failed:
                    skip_reason = f"budget_tracker_error:{tracker_error_type}"
                else:
                    skip_reason = "budget_exhausted"
                result.skipped[name] = skip_reason
                result.budget_exhausted = True
                if not budget_stop_logged:
                    await self._log_budget_exhausted(
                        client_id=client_id,
                        contact_id=contact_id,
                        tier=tier,
                        adapter_name=name,
                        remaining=remaining,
                        tracker_error_type=tracker_error_type if tracker_failed else None,
                    )
                    budget_stop_logged = True
                continue

            # --- adapter call ----------------------------------------
            adapter_result, error_reason = await self._call_adapter(
                adapter=adapter,
                contact=contact,
                dry_run=dry_run,
            )

            if adapter_result is None:
                # Adapter raised. Record as skipped with adapter_error reason,
                # do NOT debit budget, log, continue to next adapter.
                result.skipped[name] = error_reason or "adapter_error:Exception"
                await self._log_adapter_error(
                    client_id=client_id,
                    contact_id=contact_id,
                    tier=tier,
                    adapter_name=name,
                    reason=error_reason or "adapter_error:Exception",
                    dry_run=dry_run,
                )
                continue

            # Success — record result, tally cost, debit budget (if > 0).
            result.adapter_results[name] = adapter_result
            result.total_cost_cents += adapter_result.cost_cents

            if adapter_result.cost_cents > 0:
                try:
                    await self._budget_tracker.record_spend(
                        client_id, tier, adapter_result.cost_cents
                    )
                except Exception:
                    # Accounting failure must not break the fan-out.
                    pass

            await self._log_adapter_call(
                client_id=client_id,
                contact_id=contact_id,
                tier=tier,
                adapter_name=name,
                adapter_result=adapter_result,
                dry_run=dry_run,
            )

        return result

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    async def _call_adapter(
        self,
        adapter: EnrichAdapter,
        contact: dict[str, Any],
        dry_run: bool,
    ) -> tuple[EnrichResult | None, str | None]:
        """Call a single adapter. Return (result, None) on success or
        (None, "adapter_error:{ExceptionType}") on failure.

        Never re-raises.
        """
        try:
            result = await adapter.enrich(contact, dry_run=dry_run)
            return result, None
        except Exception as exc:
            reason = f"adapter_error:{type(exc).__name__}"
            return None, reason

    async def _log_adapter_call(
        self,
        client_id: str,
        contact_id: str,
        tier: str,
        adapter_name: str,
        adapter_result: EnrichResult,
        dry_run: bool,
    ) -> None:
        if self._decision_logger is None:
            return
        try:
            await self._decision_logger.log_decision(
                client_id=client_id,
                decision_type=_DECISION_TYPE,
                decision=f"enrich_contact:{adapter_name}:{adapter_result.reason}",
                reasoning=(
                    f"Adapter {adapter_name} ran for contact_id={contact_id} tier={tier}: "
                    f"ok={adapter_result.ok} reason={adapter_result.reason} "
                    f"cost_cents={adapter_result.cost_cents}"
                ),
                context={
                    "contact_id": contact_id,
                    "adapter_name": adapter_name,
                    "tier": tier,
                    "ok": adapter_result.ok,
                    "reason": adapter_result.reason,
                    "cost_cents": adapter_result.cost_cents,
                    "dry_run": dry_run,
                },
                source="system",
                confidence=None,
            )
        except Exception:
            pass  # logging must never break the fan-out

    async def _log_adapter_error(
        self,
        client_id: str,
        contact_id: str,
        tier: str,
        adapter_name: str,
        reason: str,
        dry_run: bool,
    ) -> None:
        if self._decision_logger is None:
            return
        try:
            await self._decision_logger.log_decision(
                client_id=client_id,
                decision_type=_DECISION_TYPE,
                decision=f"enrich_contact:{adapter_name}:{reason}",
                reasoning=(
                    f"Adapter {adapter_name} raised for contact_id={contact_id} tier={tier}: {reason}"
                ),
                context={
                    "contact_id": contact_id,
                    "adapter_name": adapter_name,
                    "tier": tier,
                    "ok": False,
                    "reason": reason,
                    "cost_cents": 0,
                    "dry_run": dry_run,
                },
                source="system",
                confidence=None,
            )
        except Exception:
            pass  # logging must never break the fan-out

    async def _log_budget_exhausted(
        self,
        client_id: str,
        contact_id: str,
        tier: str,
        adapter_name: str,
        remaining: int,
        tracker_error_type: str | None = None,
    ) -> None:
        """Log a single budget-stop entry per (contact, tier) — the
        orchestrator emits this at most once per enrich_contact() call, on
        the FIRST adapter skipped for budget reasons. Remaining adapters
        are marked skipped but not re-logged.

        When `tracker_error_type` is truthy, the entry records a
        budget_tracker_error instead of a plain budget_exhausted, so that
        operator dashboards can distinguish legitimate budget depletion
        from an outage of the budget service."""
        if self._decision_logger is None:
            return
        if tracker_error_type:
            decision = f"enrich_contact:{adapter_name}:budget_tracker_error"
            reasoning = (
                f"Budget tracker raised {tracker_error_type} during "
                f"remaining_cents check; failing safe as budget-exhausted. "
                f"Tier {tier} adapter {adapter_name} and remainder auto-paused."
            )
            context = {
                "contact_id": contact_id,
                "tier": tier,
                "first_skipped_adapter": adapter_name,
                "remaining_cents": remaining,
                "tracker_error_type": tracker_error_type,
            }
        else:
            decision = f"enrich_contact:{tier}:budget_exhausted"
            reasoning = (
                f"Tier {tier} budget exhausted before adapter {adapter_name}; "
                f"remaining={remaining}c. Remaining tier adapters auto-paused."
            )
            context = {
                "contact_id": contact_id,
                "tier": tier,
                "first_skipped_adapter": adapter_name,
                "remaining_cents": remaining,
            }
        try:
            await self._decision_logger.log_decision(
                client_id=client_id,
                decision_type=_DECISION_TYPE,
                decision=decision,
                reasoning=reasoning,
                context=context,
                source="system",
                confidence=None,
            )
        except Exception:
            pass  # logging must never break the fan-out

    async def _log_unknown_tier(
        self,
        client_id: str,
        contact_id: str,
        tier: str,
    ) -> None:
        if self._decision_logger is None:
            return
        try:
            await self._decision_logger.log_decision(
                client_id=client_id,
                decision_type=_DECISION_TYPE,
                decision="enrich_contact:unknown_tier",
                reasoning=(
                    f"Tier {tier!r} is not in the orchestrator's tier_adapters map; "
                    f"all adapters skipped. This should have been caught by the stage layer."
                ),
                context={
                    "contact_id": contact_id,
                    "tier": tier,
                },
                source="system",
                confidence=None,
            )
        except Exception:
            pass  # logging must never break the fan-out
