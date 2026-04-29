"""Tests for ``aios/daemon/adapter_factory.py``."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

from aios.daemon.adapter_factory import AdapterFactory
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


def _build_settings(
    *,
    apollo: str = "",
    hunter: str = "",
    zerobounce: str = "",
    trigify: str = "",
    anthropic: str = "",
) -> MagicMock:
    """Minimal settings stand-in — only fields AdapterFactory reads."""
    s = MagicMock()
    s.apollo_api_key = apollo
    s.hunter_api_key = hunter
    s.zerobounce_api_key = zerobounce
    s.trigify_api_key = trigify
    s.anthropic_api_key = anthropic
    return s


def _build_registry() -> MagicMock:
    reg = MagicMock()
    # Only attributes the factory touches.
    reg.pull_backend = MagicMock()
    reg.identity_backend = MagicMock()
    reg.enrich_backend = MagicMock()
    reg.score_backend = MagicMock()
    reg.screen_backend = MagicMock()
    reg.composer_backend = MagicMock()
    reg.budget_tracker = MagicMock()
    reg.decision_logger = MagicMock()
    reg.trigify_discovery_storage = MagicMock()
    return reg


# ---------------------------------------------------------------------------
# Pull
# ---------------------------------------------------------------------------


def test_build_pull_adapters_apollo_with_key():
    factory = AdapterFactory(
        _build_settings(apollo="test-key"), _build_registry(),
    )
    adapters = factory.build_pull_adapters({"active_directories": ["apollo"]})
    assert list(adapters.keys()) == ["apollo"]
    assert isinstance(adapters["apollo"], ApolloCompanyAdapter)


def test_build_pull_adapters_apollo_without_key_skipped(caplog):
    factory = AdapterFactory(_build_settings(apollo=""), _build_registry())
    with caplog.at_level(logging.WARNING):
        adapters = factory.build_pull_adapters(
            {"active_directories": ["apollo"]}
        )
    assert adapters == {}
    assert any("APOLLO_API_KEY" in rec.getMessage() for rec in caplog.records)


def test_build_pull_adapters_clutch():
    factory = AdapterFactory(_build_settings(), _build_registry())
    adapters = factory.build_pull_adapters(
        {"active_directories": ["clutch_agencies"]}
    )
    assert list(adapters.keys()) == ["clutch_agencies"]
    assert isinstance(adapters["clutch_agencies"], ClutchAdapter)


def test_build_pull_adapters_trigify_discovery_with_key():
    factory = AdapterFactory(
        _build_settings(trigify="tkey"), _build_registry(),
    )
    adapters = factory.build_pull_adapters(
        {"active_directories": ["trigify_discovery"]}
    )
    assert list(adapters.keys()) == ["trigify_discovery"]
    assert isinstance(adapters["trigify_discovery"], TrigifyDiscoverySource)


def test_build_pull_adapters_unknown_name_skipped(caplog):
    factory = AdapterFactory(_build_settings(), _build_registry())
    with caplog.at_level(logging.WARNING):
        adapters = factory.build_pull_adapters(
            {"active_directories": ["totally_made_up"]}
        )
    assert adapters == {}
    assert any(
        "totally_made_up" in rec.getMessage() for rec in caplog.records
    )


def test_build_pull_adapters_empty_active_directories(caplog):
    factory = AdapterFactory(_build_settings(), _build_registry())
    with caplog.at_level(logging.INFO):
        adapters = factory.build_pull_adapters({"active_directories": []})
    assert adapters == {}


def test_build_pull_adapter_clutch_explicit_category():
    """clutch:<category_path> form lets a client pick a non-default sub-category."""
    factory = AdapterFactory(_build_settings(), _build_registry())
    adapters = factory.build_pull_adapters(
        {"active_directories": ["clutch:agencies/branding"]}
    )
    assert "clutch:agencies/branding" in adapters
    clutch = adapters["clutch:agencies/branding"]
    assert isinstance(clutch, ClutchAdapter)
    assert clutch.category_path == "agencies/branding"


def test_build_pull_adapters_clutch_routing_key_separate_from_adapter_name():
    """Regression: ``clutch_agencies`` is the routing key (matches
    ``client_config.active_directories``); the ClutchAdapter's own ``.name``
    self-reports as ``clutch:agencies/digital-marketing``. The two must not
    drift — orchestrator dispatches by routing key, not adapter name.
    Pre-fix bug: factory stored adapters in a list keyed by ``adapter.name``,
    so the orchestrator's lookup of the routing key always missed."""
    factory = AdapterFactory(_build_settings(), _build_registry())
    adapters = factory.build_pull_adapters(
        {"active_directories": ["clutch_agencies"]}
    )
    assert "clutch_agencies" in adapters
    clutch = adapters["clutch_agencies"]
    assert isinstance(clutch, ClutchAdapter)
    # The adapter's self-reported name differs from the routing key — that's
    # the whole point of this contract.
    assert clutch.name != "clutch_agencies"
    assert clutch.name.startswith("clutch:")


def test_build_pull_orchestrator_returns_real_orchestrator():
    factory = AdapterFactory(
        _build_settings(apollo="k"), _build_registry(),
    )
    orch = factory.build_pull_orchestrator(
        {"active_directories": ["apollo"]}
    )
    assert isinstance(orch, PullOrchestrator)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_build_identity_adapters_all_keys_present():
    factory = AdapterFactory(
        _build_settings(apollo="a", hunter="h", anthropic="an"),
        _build_registry(),
    )
    adapters = factory.build_identity_adapters()
    types = {type(a) for a in adapters}
    assert ApolloPeopleAdapter in types
    assert HunterDomainAdapter in types
    assert ClaudeIdentityScraper in types


def test_build_identity_adapters_missing_keys_logged_and_skipped(caplog):
    factory = AdapterFactory(
        _build_settings(apollo="", hunter="", anthropic=""),
        _build_registry(),
    )
    with caplog.at_level(logging.WARNING):
        adapters = factory.build_identity_adapters()
    assert adapters == []
    messages = " ".join(rec.getMessage() for rec in caplog.records)
    assert "APOLLO_API_KEY" in messages
    assert "HUNTER_API_KEY" in messages
    assert "ANTHROPIC_API_KEY" in messages


def test_build_identity_orchestrator_returns_real_orchestrator():
    factory = AdapterFactory(
        _build_settings(apollo="a"), _build_registry(),
    )
    orch = factory.build_identity_orchestrator({})
    assert isinstance(orch, IdentityOrchestrator)


# ---------------------------------------------------------------------------
# Enrich
# ---------------------------------------------------------------------------


def test_build_enrich_adapters_all_keys_present():
    factory = AdapterFactory(
        _build_settings(
            apollo="a", zerobounce="z", trigify="t", anthropic="an",
        ),
        _build_registry(),
    )
    adapters = factory.build_enrich_adapters()
    types = {type(a) for a in adapters}
    expected = {
        ZeroBounceAdapter,
        TrigifyAdapter,
        ApolloEnrichAdapter,
        ClaudeWebTriggersAdapter,
        ClaudeDeepResearchAdapter,
        ClaudeResearchAdapter,
    }
    assert expected.issubset(types)


def test_build_enrich_adapters_missing_keys_skipped(caplog):
    factory = AdapterFactory(
        _build_settings(zerobounce="z"),  # only zerobounce keyed
        _build_registry(),
    )
    with caplog.at_level(logging.WARNING):
        adapters = factory.build_enrich_adapters()
    types = {type(a) for a in adapters}
    # Only zerobounce made it in; others logged as missing.
    assert ZeroBounceAdapter in types
    assert TrigifyAdapter not in types
    assert ApolloEnrichAdapter not in types
    assert ClaudeDeepResearchAdapter not in types


def test_build_enrich_orchestrator_returns_real_orchestrator():
    factory = AdapterFactory(
        _build_settings(zerobounce="z"), _build_registry(),
    )
    orch = factory.build_enrich_orchestrator({})
    assert isinstance(orch, EnrichOrchestrator)
