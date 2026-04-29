"""Smoke tests for ClutchProfileResolver + extractor."""
from __future__ import annotations

import pytest

from systems.scout.identity.clutch_profile_resolver import (
    ClutchProfileResolver,
    extract_company_domain_from_profile_html,
)


def test_extract_company_domain_strips_redirect_wrapper():
    """Clutch wraps website links in r.clutch.co/redirect?...&provider_website=<domain>&...
    Extractor returns the bare domain."""
    html = (
        '<a href="https://r.clutch.co/redirect?event=x'
        '&amp;provider_website=wantbranding.com&amp;u=http%3A%2F%2Fwww.wantbranding.com">'
        'Visit website</a>'
    )
    assert extract_company_domain_from_profile_html(html) == "wantbranding.com"


def test_extract_company_domain_normalises_protocol_and_www():
    html = 'provider_website=https%3A%2F%2Fwww.acme.com%2Fcontact'
    # urldecode → 'https://www.acme.com/contact' → strip protocol + www. + path → 'acme.com'
    assert extract_company_domain_from_profile_html(html) == "acme.com"


def test_extract_company_domain_returns_none_on_no_match():
    html = "<html><body>nothing useful here</body></html>"
    assert extract_company_domain_from_profile_html(html) is None


def test_resolver_applies_to_clutch_sourced_contacts():
    r = ClutchProfileResolver()
    assert r.applies_to({
        "source": "clutch:agencies/branding",
        "raw_data": {"profile_url": "https://clutch.co/profile/want"},
    }) is True
    # Wrong source
    assert r.applies_to({
        "source": "apollo_company",
        "raw_data": {"profile_url": "https://clutch.co/profile/want"},
    }) is False
    # Missing profile_url
    assert r.applies_to({
        "source": "clutch:agencies/branding",
        "raw_data": {},
    }) is False


@pytest.mark.asyncio
async def test_resolver_skips_when_domain_already_filled():
    """Idempotency — don't re-fetch if company_domain is set."""
    fetched = []

    async def fake_fetch(url: str) -> str:
        fetched.append(url)
        return "provider_website=acme.com"

    r = ClutchProfileResolver(html_fetcher=fake_fetch)
    delta = await r.resolve({
        "source": "clutch:agencies/branding",
        "company_domain": "acme.com",  # already set
        "raw_data": {"profile_url": "https://clutch.co/profile/acme"},
    })
    assert delta == {}
    assert fetched == []  # never called


@pytest.mark.asyncio
async def test_resolver_returns_domain_via_injected_fetcher():
    async def fake_fetch(url: str) -> str:
        assert url == "https://clutch.co/profile/acme"
        return (
            '<a href="https://r.clutch.co/redirect?'
            'provider_website=acme-co.com&amp;u=http%3A%2F%2Facme-co.com">'
            'Visit website</a>'
        )

    r = ClutchProfileResolver(html_fetcher=fake_fetch)
    delta = await r.resolve({
        "source": "clutch:agencies/branding",
        "company_domain": None,
        "raw_data": {"profile_url": "https://clutch.co/profile/acme"},
    })
    assert delta == {"company_domain": "acme-co.com"}
