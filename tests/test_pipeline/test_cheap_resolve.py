"""Smoke tests for CheapResolveStage."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from systems.scout.pipeline.cheap_resolve import (
    CheapResolveStage,
    ContactRow,
)


def _row(
    contact_id: str = "c1",
    *,
    company: str = "Acme",
    source: str = "clutch:agencies/branding",
    company_domain: str | None = None,
) -> ContactRow:
    return ContactRow(
        contact_id=contact_id,
        company=company,
        source=source,
        company_domain=company_domain,
        industry=None,
        raw_data={"profile_url": f"https://clutch.co/profile/{contact_id}"},
    )


def _build_storage(rows: list[ContactRow]) -> MagicMock:
    storage = MagicMock()
    storage.get_unresolved_contacts = AsyncMock(return_value=rows)
    storage.update_contact_company_data = AsyncMock(return_value=None)
    storage.log_decision = AsyncMock(return_value=None)
    return storage


def _build_resolver(name: str, delta_per_call: dict[str, Any]) -> MagicMock:
    r = MagicMock()
    r.name = name
    r.applies_to = MagicMock(return_value=True)
    r.resolve = AsyncMock(return_value=delta_per_call)
    return r


@pytest.mark.asyncio
async def test_stage_fills_domain_and_persists():
    storage = _build_storage([_row("c1")])
    resolver = _build_resolver(
        "clutch_profile", {"company_domain": "acme.com"},
    )
    stage = CheapResolveStage(adapters=[resolver], storage=storage)

    result = await stage.run("client-x")

    assert result.total_eligible == 1
    assert result.total_updated == 1
    assert result.by_resolver == {"clutch_profile": 1}
    storage.update_contact_company_data.assert_awaited_once_with(
        "client-x", "c1", company_domain="acme.com", industry=None,
    )
    # Stage summary always emitted.
    summary_calls = [
        c for c in storage.log_decision.await_args_list
        if c.kwargs.get("decision") == "cheap_resolve_stage_summary"
    ]
    assert len(summary_calls) == 1


@pytest.mark.asyncio
async def test_stage_dry_run_does_not_persist():
    storage = _build_storage([_row("c1")])
    resolver = _build_resolver(
        "clutch_profile", {"company_domain": "acme.com"},
    )
    stage = CheapResolveStage(adapters=[resolver], storage=storage)

    result = await stage.run("client-x", dry_run=True)

    assert result.total_updated == 1  # would-be update tallied
    storage.update_contact_company_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_stage_skips_when_resolver_returns_empty():
    storage = _build_storage([_row("c1")])
    resolver = _build_resolver("clutch_profile", {})
    stage = CheapResolveStage(adapters=[resolver], storage=storage)

    result = await stage.run("client-x")

    assert result.total_skipped == 1
    assert result.total_updated == 0
    storage.update_contact_company_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_stage_skips_resolver_via_applies_to_filter():
    """Resolver.applies_to(contact)=False → resolver.resolve never called."""
    storage = _build_storage([_row("c1", source="apollo_company")])
    resolver = _build_resolver(
        "clutch_profile", {"company_domain": "acme.com"},
    )
    resolver.applies_to = MagicMock(return_value=False)
    stage = CheapResolveStage(adapters=[resolver], storage=storage)

    await stage.run("client-x")

    resolver.resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_stage_first_resolver_wins_per_field():
    """Two resolvers fill the same field — first wins."""
    storage = _build_storage([_row("c1")])
    r1 = _build_resolver("first", {"company_domain": "first.com"})
    r2 = _build_resolver("second", {"company_domain": "second.com"})
    stage = CheapResolveStage(adapters=[r1, r2], storage=storage)

    await stage.run("client-x")

    storage.update_contact_company_data.assert_awaited_once_with(
        "client-x", "c1", company_domain="first.com", industry=None,
    )
