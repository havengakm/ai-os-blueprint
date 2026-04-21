"""Identity-lookup orchestrator — waterfall dispatch across identity adapters.

First-hit-wins across (apollo_people → hunter_domain → claude_scraper).
Returns OrchestratorResult with the resolved IdentityResult (or None) plus
an audit trail of which adapters were called.

This is NOT a pipeline stage — no BaseSystem, no foundation loading.
That happens in Task 9.5e. This class is a pure dispatcher.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from os.foundation.decision_logger import DecisionLogger
    from systems.scout.identity.base import IdentityAdapter, IdentityResult


@dataclass
class OrchestratorResult:
    """What the orchestrator returns per (company, domain) call."""

    identity: IdentityResult | None         # None when all adapters miss
    source: str | None                      # winning adapter name, or None
    sources_attempted: list[str]            # flattened from every IdentityResult that ran
    archived: bool                          # True iff identity is None


class IdentityOrchestrator:
    """Waterfall dispatch across identity adapters. First-hit-wins."""

    DEFAULT_ORDER: tuple[str, ...] = ("apollo_people", "hunter_domain", "claude_scraper")

    def __init__(
        self,
        adapters: list[IdentityAdapter],
        decision_logger: DecisionLogger | None = None,
        order: tuple[str, ...] | None = None,
    ) -> None:
        """
        adapters: list of IdentityAdapter instances. Any subset is allowed; adapters
                  not named in `order` are skipped.
        decision_logger: if provided, logs one entry per adapter call + one on archive.
        order: adapter names in dispatch order. Defaults to DEFAULT_ORDER.
        """
        self._decision_logger = decision_logger
        effective_order = order if order is not None else self.DEFAULT_ORDER

        # Build an ordered list of adapters that match the dispatch order.
        # Adapters in `order` but absent from the list are silently skipped.
        adapter_by_name = {a.name: a for a in adapters}
        self._ordered_adapters: list[IdentityAdapter] = [
            adapter_by_name[name]
            for name in effective_order
            if name in adapter_by_name
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def resolve(
        self,
        client_id: str,
        company: str,
        company_domain: str | None = None,
        **adapter_kwargs: Any,
    ) -> OrchestratorResult:
        """Dispatch adapters in order. First non-None IdentityResult wins.

        Always returns OrchestratorResult. Never raises on adapter failures.
        adapter_kwargs are forwarded to each adapter's resolve() call.
        """
        sources_attempted: list[str] = []
        adapters_called: list[str] = []

        for adapter in self._ordered_adapters:
            result = await self._call_adapter(
                adapter=adapter,
                client_id=client_id,
                company=company,
                company_domain=company_domain,
                adapter_kwargs=adapter_kwargs,
            )
            adapters_called.append(adapter.name)

            if result is not None:
                # Aggregate sources from this winning adapter
                sources_attempted.extend(result.sources_attempted)
                return OrchestratorResult(
                    identity=result,
                    source=adapter.name,
                    sources_attempted=sources_attempted,
                    archived=False,
                )

        # All adapters returned None (or there were none to call)
        await self._log_archive(
            client_id=client_id,
            company=company,
            company_domain=company_domain,
            sources_attempted=sources_attempted,
            adapters_called=adapters_called,
        )
        return OrchestratorResult(
            identity=None,
            source=None,
            sources_attempted=sources_attempted,
            archived=True,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call_adapter(
        self,
        adapter: IdentityAdapter,
        client_id: str,
        company: str,
        company_domain: str | None,
        adapter_kwargs: dict[str, Any],
    ) -> IdentityResult | None:
        """Call a single adapter, log the outcome, return result or None on exception."""
        result: IdentityResult | None = None
        reasoning: str

        try:
            result = await adapter.resolve(company, company_domain=company_domain, **adapter_kwargs)
            hit = result is not None
            reasoning = (
                f"Adapter {adapter.name} {'resolved' if hit else 'returned None'} "
                f"for company={company}, domain={company_domain}"
            )
        except Exception as exc:
            hit = False
            reasoning = (
                f"Adapter {adapter.name} raised: {type(exc).__name__}: {exc}"
            )[:500]

        await self._log_adapter_call(
            client_id=client_id,
            adapter_name=adapter.name,
            hit=hit,
            result=result,
            company=company,
            company_domain=company_domain,
            reasoning=reasoning,
        )
        return result

    async def _log_adapter_call(
        self,
        client_id: str,
        adapter_name: str,
        hit: bool,
        result: IdentityResult | None,
        company: str,
        company_domain: str | None,
        reasoning: str,
    ) -> None:
        if self._decision_logger is None:
            return
        outcome_label = "hit" if hit else "miss"
        try:
            await self._decision_logger.log_decision(
                client_id=client_id,
                decision_type="identity_lookup",
                decision=f"identity_lookup:{adapter_name}:{outcome_label}",
                reasoning=reasoning,
                context={
                    "company": company,
                    "company_domain": company_domain,
                    "adapter": adapter_name,
                    "hit": hit,
                    "confidence": result.confidence if result else None,
                },
                source="system",
                confidence=result.confidence if result else None,
            )
        except Exception:
            pass  # logging must never break the waterfall

    async def _log_archive(
        self,
        client_id: str,
        company: str,
        company_domain: str | None,
        sources_attempted: list[str],
        adapters_called: list[str],
    ) -> None:
        if self._decision_logger is None:
            return
        try:
            await self._decision_logger.log_decision(
                client_id=client_id,
                decision_type="identity_lookup",
                decision="identity_lookup:archive_no_decision_maker",
                reasoning=(
                    "All identity adapters returned None; contact cannot be outreached "
                    "without a resolved decision-maker"
                ),
                context={
                    "company": company,
                    "company_domain": company_domain,
                    "sources_attempted": sources_attempted,
                    "adapters_called": adapters_called,
                },
                source="system",
                confidence=None,
            )
        except Exception:
            pass
