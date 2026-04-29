"""AdapterFactory — builds per-client pull/identity/enrich orchestrators
from ``client_config.active_directories`` and env API keys (Task 16.6).

The daemon calls ``AdapterFactory`` once per client cycle. Unlike
``ScoutSystem.from_registry`` (which ships zero-adapter orchestrators as
no-op defaults), the daemon wires REAL adapters so nightly cycles do
real pulls / resolutions / enrichments.

Design rules:
- Unknown directory names → log warning, skip (do NOT raise). An
  operator misconfiguring ``active_directories`` should not take down
  the daemon; the warning surfaces the typo.
- Missing API keys → log warning, skip that adapter. Same reasoning:
  degraded cycle beats no cycle.
- Zero adapters for a stage is VALID — the stage runs, logs "no
  adapters configured", returns zero-count summary.

MVP support: apollo, clutch_agencies, trigify_discovery for pull;
apollo/hunter/claude_scraper for identity; zerobounce/trigify/
apollo_enrich/claude_web_triggers/claude_deep_research/claude_research
for enrich. Adapters outside this list are logged and skipped until
wired in a follow-up.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from systems.scout.enrich.apollo_enrich import ApolloEnrichAdapter
from systems.scout.enrich.claude_deep_research import ClaudeDeepResearchAdapter
from systems.scout.enrich.claude_research import ClaudeResearchAdapter
from systems.scout.enrich.claude_web_triggers import ClaudeWebTriggersAdapter
from systems.scout.enrich.orchestrator import EnrichOrchestrator
from systems.scout.enrich.trigify import TrigifyAdapter
from systems.scout.enrich.zerobounce import ZeroBounceAdapter
from systems.scout.identity.apollo_people import ApolloPeopleAdapter
from systems.scout.identity.claude_identity_scraper import ClaudeIdentityScraper
from systems.scout.identity.hunter_domain import HunterDomainAdapter
from systems.scout.identity.orchestrator import IdentityOrchestrator
from systems.scout.pipeline.pull import PullOrchestrator
from systems.scout.sources.apollo_company import ApolloCompanyAdapter
from systems.scout.sources.clutch import ClutchAdapter
from systems.scout.sources.trigify_discovery import TrigifyDiscoverySource

if TYPE_CHECKING:
    from aios.foundation.registry import SystemRegistry
    from config.settings import Settings
    from systems.scout.enrich.base import EnrichAdapter
    from systems.scout.identity.base import IdentityAdapter
    from systems.scout.sources.base import CompanySourceAdapter

logger = logging.getLogger(__name__)


# Default Clutch category when the operator lists "clutch_agencies" without
# a subcategory path. Mirrors the most common use case (digital-marketing).
_DEFAULT_CLUTCH_CATEGORY = "agencies/digital-marketing"


class AdapterFactory:
    """Builds per-client orchestrators from active_directories + env keys.

    Instantiated with a ``Settings`` instance (for API-key presence checks)
    and a ``SystemRegistry`` (for shared storage backends the adapters
    need — Trigify discovery storage for example).
    """

    def __init__(
        self,
        settings: "Settings",
        registry: "SystemRegistry",
    ) -> None:
        self._settings = settings
        self._registry = registry

    # ------------------------------------------------------------------ #
    # Pull                                                                 #
    # ------------------------------------------------------------------ #

    def build_pull_adapters(
        self, client_config: dict[str, Any],
    ) -> dict[str, "CompanySourceAdapter"]:
        """Build the source adapters named in ``active_directories``.

        Returns a ``dict[routing_key, adapter]`` where the routing_key is
        the EXACT name from ``active_directories`` — this is what the
        orchestrator dispatches on. The adapter's own ``.name`` may differ
        (e.g. ``ClutchAdapter`` self-reports as ``clutch:{category_path}``);
        keep the routing key separate so lookups don't drift.

        Unknown names are logged and skipped. Adapters requiring an API key
        that isn't set are also logged + skipped — the stage can still run
        with the remaining adapters.
        """
        active: list[str] = list(client_config.get("active_directories") or [])
        if not active:
            logger.info(
                "pull: active_directories empty for client — stage will no-op",
            )
            return {}

        adapters: dict[str, CompanySourceAdapter] = {}
        for name in active:
            adapter = self._build_pull_adapter(name)
            if adapter is not None:
                adapters[name] = adapter
        return adapters

    def _build_pull_adapter(self, name: str) -> "CompanySourceAdapter | None":
        if name == "apollo" or name == "apollo_company":
            if not self._settings.apollo_api_key:
                logger.warning(
                    "pull adapter %r requested but APOLLO_API_KEY is unset; skipping",
                    name,
                )
                return None
            return ApolloCompanyAdapter()

        if name == "clutch_agencies":
            # Backward-compat shorthand → default sub-category. Prefer the
            # explicit ``clutch:<category_path>`` form (below) for new wiring
            # so each client picks the sub-category that matches its ICP.
            return ClutchAdapter(category_path=_DEFAULT_CLUTCH_CATEGORY)

        if name.startswith("clutch:"):
            # Explicit Clutch sub-category routing. Format:
            # ``clutch:<category_path>`` (e.g. ``clutch:agencies/branding``,
            # ``clutch:developers/shopify``). The category_path is forwarded
            # verbatim to ClutchAdapter; tweak per-client by setting
            # ``client_config.active_directories`` accordingly.
            category_path = name.removeprefix("clutch:").strip("/")
            if not category_path:
                logger.warning(
                    "pull adapter %r has empty category after 'clutch:' "
                    "prefix; skipping", name,
                )
                return None
            return ClutchAdapter(category_path=category_path)

        if name == "trigify_discovery":
            if not self._settings.trigify_api_key:
                logger.warning(
                    "pull adapter %r requested but TRIGIFY_API_KEY is unset; skipping",
                    name,
                )
                return None
            return TrigifyDiscoverySource(
                storage=self._registry.trigify_discovery_storage,
            )

        logger.warning("pull adapter %r not wired; skipping", name)
        return None

    def build_pull_orchestrator(
        self, client_config: dict[str, Any],
    ) -> PullOrchestrator:
        """Assemble a PullOrchestrator with adapters + shared storage."""
        adapters = self.build_pull_adapters(client_config)
        return PullOrchestrator(
            adapters=adapters,
            storage=self._registry.pull_backend,
        )

    # ------------------------------------------------------------------ #
    # Cheap-resolve (Pattern C — fills domain/industry pre-score_v1)      #
    # ------------------------------------------------------------------ #

    def build_cheap_resolve_adapters(
        self, client_config: dict[str, Any],  # noqa: ARG002 — reserved for per-client overrides
    ) -> list[Any]:
        """Build the cheap-tier resolvers. Each resolver's ``applies_to``
        filter handles per-source eligibility, so we register every
        available resolver. Adding a new resolver = appending here.
        """
        from systems.scout.identity.clutch_profile_resolver import (
            ClutchProfileResolver,
        )

        return [ClutchProfileResolver()]

    # ------------------------------------------------------------------ #
    # Identity                                                             #
    # ------------------------------------------------------------------ #

    def build_identity_adapters(self) -> list["IdentityAdapter"]:
        """Build every identity adapter whose API key / env is available.

        Identity is a waterfall, not a per-client toggle — wiring is driven
        by "what keys does this deployment have?" rather than
        active_directories. The orchestrator itself handles tier order.
        """
        adapters: list[IdentityAdapter] = []
        if self._settings.apollo_api_key:
            adapters.append(ApolloPeopleAdapter())
        else:
            logger.warning(
                "identity: APOLLO_API_KEY unset; apollo_people adapter skipped",
            )
        if self._settings.hunter_api_key:
            adapters.append(HunterDomainAdapter())
        else:
            logger.warning(
                "identity: HUNTER_API_KEY unset; hunter_domain adapter skipped",
            )
        if self._settings.anthropic_api_key:
            adapters.append(ClaudeIdentityScraper())
        else:
            logger.warning(
                "identity: ANTHROPIC_API_KEY unset; claude_scraper adapter skipped",
            )
        return adapters

    def build_identity_orchestrator(
        self,
        client_config: dict[str, Any],  # noqa: ARG002 — reserved for per-client overrides
    ) -> IdentityOrchestrator:
        """Build an identity waterfall with whatever adapters are keyed."""
        return IdentityOrchestrator(
            adapters=self.build_identity_adapters(),
            decision_logger=self._registry.decision_logger,
        )

    # ------------------------------------------------------------------ #
    # Enrich                                                               #
    # ------------------------------------------------------------------ #

    def build_enrich_adapters(self) -> list["EnrichAdapter"]:
        """Build every enrich adapter whose API key / env is available."""
        adapters: list[EnrichAdapter] = []
        if self._settings.zerobounce_api_key:
            adapters.append(ZeroBounceAdapter())
        else:
            logger.warning(
                "enrich: ZEROBOUNCE_API_KEY unset; zerobounce adapter skipped",
            )
        if self._settings.trigify_api_key:
            adapters.append(TrigifyAdapter())
        else:
            logger.warning(
                "enrich: TRIGIFY_API_KEY unset; trigify adapter skipped",
            )
        if self._settings.apollo_api_key:
            adapters.append(ApolloEnrichAdapter())
        else:
            logger.warning(
                "enrich: APOLLO_API_KEY unset; apollo_enrich adapter skipped",
            )
        if self._settings.anthropic_api_key:
            adapters.append(ClaudeWebTriggersAdapter())
            adapters.append(ClaudeDeepResearchAdapter())
            adapters.append(ClaudeResearchAdapter())
        else:
            logger.warning(
                "enrich: ANTHROPIC_API_KEY unset; claude_* adapters skipped",
            )
        return adapters

    def build_enrich_orchestrator(
        self,
        client_config: dict[str, Any],  # noqa: ARG002 — reserved for per-client overrides
    ) -> EnrichOrchestrator:
        """Build an enrich fan-out orchestrator with the keyed adapters."""
        return EnrichOrchestrator(
            adapters=self.build_enrich_adapters(),
            budget_tracker=self._registry.budget_tracker,
            decision_logger=self._registry.decision_logger,
        )
