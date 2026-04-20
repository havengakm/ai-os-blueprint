"""Scout identity-lookup package — decision-maker resolution for company-level contacts."""
from systems.scout.identity.apollo_people import ApolloPeopleAdapter
from systems.scout.identity.base import (
    GENERIC_EMAIL_LOCAL_PARTS,
    IdentityAdapter,
    IdentityResult,
    is_generic_email,
)

__all__ = [
    "ApolloPeopleAdapter",
    "GENERIC_EMAIL_LOCAL_PARTS",
    "IdentityAdapter",
    "IdentityResult",
    "is_generic_email",
]
