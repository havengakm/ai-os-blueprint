"""Claude Haiku research adapter — light-touch pain inference.

Passes a small prompt to Claude Haiku that asks it to infer the most likely
business pain + intent signals based on its prior knowledge of the company,
its industry, and size. Does NOT scrape the web or make external HTTP calls
beyond the Anthropic API.

Live-signal fields are hardcoded False by design:
  - activity_positive      — requires live webhook/CRM activity data (Plan 2)
  - funding_event_last_180d — requires live news/funding research (future heavy adapter)
  - recent_hiring           — requires live job-board scraping (future heavy adapter)

MONEY PATH: every completed API call costs real money. Rules:
  - No retries — billed call, retries multiply charges.
  - dry_run must NEVER reach the API.
  - Parse failures still record cost_cents (we were billed regardless).
  - Infrastructure errors propagate — orchestrator handles accounting.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from anthropic import AsyncAnthropic

from systems.scout.enrich.base import EnrichResult


logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 400  # caps worst-case cost; ~200 output tokens expected

VALID_PAIN_CATEGORIES = frozenset(
    {"pipeline", "delivery", "retention", "positioning", "pricing", "team", "tooling", "other"}
)

_SYSTEM_PROMPT = (
    "You are a B2B research analyst. Given limited metadata about a small business, "
    "infer the single most likely revenue-blocking pain this business has. Return strict JSON."
)

_USER_TEMPLATE = """\
Company: {company}
Domain: {domain}
Industry: {industry}
Size: {employees} employees
Contact title: {title}

Based on this metadata and your knowledge of similar businesses in this industry and size, identify the most likely revenue-blocking pain this company has.

Return STRICT JSON with this shape — no prose, no code fences:

{{
  "pain_match": "one-line description of the pain, max 120 chars",
  "pain_category": "pipeline" | "delivery" | "retention" | "positioning" | "pricing" | "team" | "tooling" | "other",
  "confidence": 0.0 to 1.0,
  "reasoning": "one sentence justification, max 200 chars"
}}

Rules:
- If the metadata is insufficient to make a confident inference, set confidence below 0.5 and pick the safest category (usually "pipeline" for small service businesses).
- Never invent specifics like funding rounds or hiring sprees — those require live research.
- Keep pain_match specific to THIS business, not generic industry boilerplate.\
"""

_PARSE_FAILED_DATA: dict[str, Any] = {
    "pain_match": None,
    "pain_category": "other",
    "activity_positive": False,
    "funding_event_last_180d": False,
    "recent_hiring": False,
    "confidence": 0.0,
    "reasoning": "",
}


class ClaudeResearchAdapter:
    """Light-touch research via Claude Haiku. Infers business pain +
    intent signals from company metadata + prior knowledge — does NOT
    scrape the web.

    Produces research_data shape consumed by score_v2 + template filling:
        pain_match:            str | None   # most likely business pain (free text, <=120 chars)
        pain_category:         str          # canonical bucket: "pipeline" | "delivery" | "retention"
                                            #   | "positioning" | "pricing" | "team" | "tooling" | "other"
        activity_positive:     bool         # False — real activity signals require live data (Plan 2)
        funding_event_last_180d: bool       # False — requires live research (future heavy adapter)
        recent_hiring:         bool         # False — requires live job-board scraping (future adapter)
        confidence:            float        # 0..1, Claude's self-reported confidence (clamped)
        reasoning:             str          # one-sentence justification for the pain inference
    """

    name: str = "claude_research"
    cost_cents_per_call: int = 1  # Haiku ~$0.0003/call, rounded UP to 1 cent for safety

    def __init__(self, anthropic_client: AsyncAnthropic | None = None) -> None:
        """anthropic_client: AsyncAnthropic. Inject in tests; None = lazy production init."""
        self._anthropic_client = anthropic_client

    async def enrich(
        self,
        contact: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> EnrichResult:
        """Infer business pain for a contact via Claude Haiku.

        Skip paths (no API call, cost_cents=0):
        - dry_run=True
        - ANTHROPIC_API_KEY unset
        - company blank

        On a completed API call (any response), cost_cents=self.cost_cents_per_call.
        Parse failures return ok=True with cost charged — we were billed.
        Infrastructure errors propagate — no retry, no catch.
        """
        contact_id = contact.get("contact_id", "<unknown>")

        # --- dry run (check first — cheapest guard) ---
        if dry_run:
            logger.debug("claude_research dry_run contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=True,
                data={},
                cost_cents=0,
                reason="dry_run_skipped",
            )

        # --- API key guard ---
        if not os.environ.get("ANTHROPIC_API_KEY"):
            logger.warning("claude_research no_api_key contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=False,
                data={},
                cost_cents=0,
                reason="no_api_key",
            )

        # --- company guard ---
        company = (contact.get("company") or "").strip()
        if not company:
            logger.debug("claude_research no_company contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=False,
                data={},
                cost_cents=0,
                reason="no_company",
            )

        # --- build prompt ---
        user_message = _USER_TEMPLATE.format(
            company=company,
            domain=contact.get("company_domain") or "unknown",
            industry=contact.get("industry") or "unknown",
            employees=contact.get("employees") or "unknown",
            title=contact.get("title") or "unknown",
        )

        # --- API call (no try/except — infrastructure errors propagate) ---
        client = self._anthropic_client or AsyncAnthropic()
        response = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw_text = response.content[0].text.strip()

        # --- parse response ---
        try:
            parsed: dict[str, Any] = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning(
                "claude_research parse_failed contact_id=%s raw=%r",
                contact_id,
                raw_text[:200],
            )
            return EnrichResult(
                adapter_name=self.name,
                ok=True,
                cost_cents=self.cost_cents_per_call,
                reason="parse_failed",
                data=dict(_PARSE_FAILED_DATA),
                raw_response={"raw_text": raw_text},
            )

        # --- validate + sanitise ---
        pain_match: str | None = parsed.get("pain_match") or None
        if pain_match:
            pain_match = pain_match[:120]

        pain_category: str = str(parsed.get("pain_category") or "other")
        category_invalid = pain_category not in VALID_PAIN_CATEGORIES
        if category_invalid:
            pain_category = "other"

        confidence: float = float(parsed.get("confidence") or 0.0)
        confidence = max(0.0, min(1.0, confidence))

        reasoning: str = str(parsed.get("reasoning") or "")[:200]

        reason = "research_complete_category_invalid" if category_invalid else "research_complete"

        data: dict[str, Any] = {
            "pain_match": pain_match,
            "pain_category": pain_category,
            "activity_positive": False,       # light-touch: live activity data needed (Plan 2)
            "funding_event_last_180d": False,  # light-touch: live research needed (future adapter)
            "recent_hiring": False,            # light-touch: job-board scraping needed (future adapter)
            "confidence": confidence,
            "reasoning": reasoning,
        }

        logger.info(
            "claude_research contact_id=%s category=%s confidence=%.2f cost_cents=%d",
            contact_id, pain_category, confidence, self.cost_cents_per_call,
        )

        return EnrichResult(
            adapter_name=self.name,
            ok=True,
            cost_cents=self.cost_cents_per_call,
            reason=reason,
            data=data,
            raw_response={"raw_text": raw_text},
        )
