"""Identity-lookup contract — decision-maker resolution for a company.

Per Amendment 2 of the 2026-04-20 lead-sourcing decision: Task 9 (sources)
produces company-level contacts with null person fields; Task 9.5 fills
them via a waterfall of purpose-built people APIs.

Rejection criteria (enforced at adapter level, not orchestrator):
- Generic emails (info@, contact@, hello@, sales@, team@, admin@) must NOT
  be returned as the primary email — adapter returns None in that case
- Blank or 'Unknown' names must NOT be returned
- Missing title is acceptable (set title=None); never invent one
"""
from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


GENERIC_EMAIL_LOCAL_PARTS = frozenset({
    "info", "contact", "hello", "sales", "team", "admin", "support",
    "help", "hi", "enquiries", "inquiries", "office", "mail", "marketing",
})


def is_generic_email(email: str | None) -> bool:
    """True if the email's local-part matches a generic/role mailbox."""
    if not email or "@" not in email:
        return True  # no email = not usable for cold outreach
    local = email.split("@", 1)[0].strip().lower()
    return local in GENERIC_EMAIL_LOCAL_PARTS


class IdentityResult(BaseModel):
    """Resolved decision-maker for a company."""

    first_name: str
    last_name: str
    title: str | None = None
    email: str                     # work email — never info@/contact@/etc
    linkedin_url: str | None = None
    source: str                    # adapter key: 'apollo_people' | 'hunter_domain' | 'claude_scraper'
    confidence: float              # 0..1
    sources_attempted: list[str] = []  # URLs or API endpoints hit


class IdentityAdapter(Protocol):
    """Protocol every identity-lookup adapter must implement."""

    name: str  # 'apollo_people' | 'hunter_domain' | 'claude_scraper'

    async def resolve(
        self,
        company: str,
        company_domain: str | None = None,
        **kwargs: Any,
    ) -> IdentityResult | None:
        """Attempt to resolve a decision-maker for the given company.

        Returns None if:
        - No candidate found
        - Only generic emails found (info@, contact@, etc.)
        - Data is ambiguous / low-confidence
        Adapter MUST NOT fabricate names or emails.
        """
        ...
