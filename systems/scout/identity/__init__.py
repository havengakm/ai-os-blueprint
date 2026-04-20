"""Scout identity-lookup package — decision-maker resolution for company-level contacts."""
from systems.scout.identity.apollo_people import ApolloPeopleAdapter
from systems.scout.identity.base import (
    GENERIC_EMAIL_LOCAL_PARTS,
    IdentityAdapter,
    IdentityResult,
    is_generic_email,
)
from systems.scout.identity.claude_identity_scraper import ClaudeIdentityScraper
from systems.scout.identity.hunter_domain import HunterDomainAdapter

__all__ = [
    "ApolloPeopleAdapter",
    "ClaudeIdentityScraper",
    "GENERIC_EMAIL_LOCAL_PARTS",
    "HunterDomainAdapter",
    "IdentityAdapter",
    "IdentityResult",
    "is_generic_email",
]
