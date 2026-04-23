"""Claude-with-web-search adapter for per-contact firmographic trigger detection.

Uses Anthropic's native web-search tool (web_search_20260209) to find recent
news events that make cold outreach timely: funding rounds, executive hires,
product launches, expansion, layoffs, press coverage.

MONEY PATH:
  - No retries — billed call, retries multiply charges.
  - dry_run must NEVER reach the API.
  - Parse failures still record cost_cents (Claude was billed regardless).
  - Infrastructure errors propagate — orchestrator handles accounting.

Complements TrigifyAdapter (behavioral signals). This adapter is firmographic;
Trigify is behavioral. Both feed research_data.trigger_events[] with compatible
shapes.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from typing import Any

from systems.scout.enrich.base import EnrichResult


logger = logging.getLogger(__name__)

SONNET_MODEL = "claude-sonnet-4-6-20251001"
MAX_TOKENS = 800

VALID_EVENT_TYPES = frozenset(
    {"funding_round", "executive_hire", "product_launch", "expansion", "layoffs", "press_coverage"}
)

_SYSTEM_PROMPT = (
    "You are a B2B research analyst finding recent public news about a specific company. "
    "You have access to a web search tool. Use it to find events that would make cold "
    "outreach to this company TIMELY and RELEVANT.\n\n"
    "Return STRICTLY valid JSON — no prose, no code fences.\n\n"
    "Focus on events from the last 90 days only. Never invent events — only report what "
    "search results explicitly support, with a source URL."
)

_USER_TEMPLATE = """\
Company: {company}
Domain: {domain}
Industry: {industry}
Size: {employees} employees
Contact title: {title}

Search for recent (last 90 days) public news about this company across these event types:
- funding_round (seed / Series A/B/C/D+ / bridge / line of credit)
- executive_hire (new CEO, CRO, CMO, CFO, COO, CTO, VP-level)
- product_launch (new product, major feature, new service line)
- expansion (new office, new market, new region, international expansion)
- layoffs (reductions in force, restructuring)
- press_coverage (major media mentions, awards, industry recognition, negative press)

Run up to 3 targeted web searches. Return STRICT JSON:

{{
  "trigger_events": [
    {{
      "type": "funding_round" | "executive_hire" | "product_launch" | "expansion" | "layoffs" | "press_coverage",
      "detail": "one-line description with specifics, max 200 chars",
      "source_url": "URL of the source article",
      "event_date": "YYYY-MM-DD or null if unknown",
      "recency_days": 0-90 or null,
      "confidence": 0.0-1.0
    }}
  ],
  "confidence": 0.0-1.0,
  "reasoning": "one sentence summary of what was found and how certain, max 240 chars"
}}

Rules:
- If no events found in 90 days, return {{"trigger_events": [], "confidence": 0.0, "reasoning": "..."}}
- Skip rumors, speculation, forward-looking statements without confirmed execution
- Each trigger_event MUST have source_url — never fabricate
- Cap trigger_events at 8 (highest confidence first)\
"""


# --------------------------------------------------------------------------- #
# Validation helpers                                                             #
# --------------------------------------------------------------------------- #

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _compute_recency(event_date_str: str | None) -> int | None:
    """Compute recency_days from event_date string if parseable."""
    if not event_date_str:
        return None
    try:
        evt = datetime.strptime(event_date_str, "%Y-%m-%d").date()
        today = date.today()
        delta = (today - evt).days
        return max(0, min(90, delta))
    except (ValueError, TypeError):
        return None


def _validate_events(raw: Any) -> list[dict[str, Any]]:
    """Validate, filter, and normalise trigger events from Claude's response."""
    if not isinstance(raw, list):
        return []

    valid: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        # Required fields
        if not item.get("type") or not item.get("detail") or not item.get("source_url"):
            continue
        # Type must be in allowed set
        event_type = str(item["type"])
        if event_type not in VALID_EVENT_TYPES:
            continue

        # Truncate detail
        detail = str(item["detail"])[:200]

        # Normalise recency_days
        recency_raw = item.get("recency_days")
        if recency_raw is not None:
            try:
                recency = int(recency_raw)
                recency = max(0, min(90, recency))
            except (ValueError, TypeError):
                recency = _compute_recency(item.get("event_date"))
        else:
            recency = _compute_recency(item.get("event_date"))

        confidence_raw = item.get("confidence", 0.0)
        try:
            confidence = _clamp(float(confidence_raw), 0.0, 1.0)
        except (ValueError, TypeError):
            confidence = 0.0

        valid.append({
            "type": event_type,
            "detail": detail,
            "source_url": str(item["source_url"]),
            "event_date": item.get("event_date"),
            "recency_days": recency,
            "confidence": confidence,
        })

    # Sort by confidence desc, cap at 8
    valid.sort(key=lambda e: e["confidence"], reverse=True)
    return valid[:8]


def _default_data() -> dict[str, Any]:
    return {
        "trigger_events": [],
        "has_active_trigger": False,
        "confidence": 0.0,
        "reasoning": "",
        "searches_performed": 0,
    }


def _extract_text_block(content: list[Any]) -> str:
    """Find the final text block in response.content (web-search results precede it)."""
    for block in reversed(content):
        try:
            text = block.text
            if text is not None:
                return text.strip()
        except AttributeError:
            continue
    return ""


def _extract_search_count(usage: Any) -> int:
    """Extract web_search_requests from response.usage.server_tool_use if available."""
    try:
        return int(usage.server_tool_use.web_search_requests)
    except (AttributeError, TypeError, ValueError):
        return 0


# --------------------------------------------------------------------------- #
# Adapter                                                                        #
# --------------------------------------------------------------------------- #

class ClaudeWebTriggersAdapter:
    """Claude-with-web-search adapter for per-contact firmographic triggers.

    Fires per-contact at enrich time. Uses Anthropic's native web-search tool
    (web_search_20260209) to find recent news events that would make a cold
    outreach land: funding rounds, executive hires, product launches,
    expansion announcements, layoffs, press coverage.

    Complements Trigify (behavioral signals from LinkedIn engagement monitoring).
    This adapter is firmographic; Trigify is behavioral. Both feed
    `research_data.trigger_events[]` with compatible shapes.
    """

    name: str = "claude_web_triggers"
    cost_cents_per_call: int = 5  # ~2.3c Sonnet tokens + ~2-3c web-search charges, rounded up

    def __init__(
        self,
        anthropic_client: Any = None,
    ) -> None:
        self._anthropic_client = anthropic_client
        self._anthropic_provided = anthropic_client is not None

    async def _ensure_client(self) -> Any:
        if self._anthropic_client is None:
            from anthropic import AsyncAnthropic
            self._anthropic_client = AsyncAnthropic()
        return self._anthropic_client

    async def aclose(self) -> None:
        """Close lazily-created Anthropic client. Idempotent."""
        if self._anthropic_client is not None and not self._anthropic_provided:
            try:
                await self._anthropic_client.close()
            finally:
                self._anthropic_client = None

    async def enrich(
        self,
        contact: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> EnrichResult:
        """Find firmographic trigger events for a contact via web search.

        Skip paths (no API call, cost_cents=0):
          - dry_run=True
          - ANTHROPIC_API_KEY unset
          - company blank

        Parse failures: ok=True, cost_cents=cost_cents_per_call (billed regardless).
        Infrastructure errors propagate.
        """
        contact_id = contact.get("contact_id", "<unknown>")

        # --- dry run (first — before any env checks) ---
        if dry_run:
            logger.debug("claude_web_triggers dry_run contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=True,
                data=_default_data(),
                cost_cents=0,
                reason="dry_run_skipped",
            )

        # --- API key guard ---
        if not os.environ.get("ANTHROPIC_API_KEY"):
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
            return EnrichResult(
                adapter_name=self.name,
                ok=False,
                data={},
                cost_cents=0,
                reason="no_company",
            )

        # --- build prompt ---
        domain = (contact.get("company_domain") or "").strip() or "unknown"
        industry = (contact.get("industry") or "").strip() or "unknown"
        employees = contact.get("employees") or "unknown"
        title = (contact.get("title") or "").strip() or "unknown"

        user_prompt = _USER_TEMPLATE.format(
            company=company,
            domain=domain,
            industry=industry,
            employees=employees,
            title=title,
        )

        # --- Claude call (no try/except — infrastructure errors propagate) ---
        client = await self._ensure_client()
        response = await client.messages.create(
            model=SONNET_MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
        )

        raw_text = _extract_text_block(response.content)
        searches_performed = _extract_search_count(response.usage)

        # --- parse ---
        try:
            parsed: dict[str, Any] = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning(
                "claude_web_triggers parse_failed contact_id=%s raw=%r",
                contact_id, raw_text[:200],
            )
            data = _default_data()
            data["searches_performed"] = searches_performed
            return EnrichResult(
                adapter_name=self.name,
                ok=True,
                cost_cents=self.cost_cents_per_call,
                reason="parse_failed",
                data=data,
                raw_response={},
            )

        # --- validate ---
        trigger_events = _validate_events(parsed.get("trigger_events"))

        confidence_raw = parsed.get("confidence", 0.0)
        try:
            confidence = _clamp(float(confidence_raw), 0.0, 1.0)
        except (ValueError, TypeError):
            confidence = 0.0

        reasoning = str(parsed.get("reasoning") or "")[:240]

        has_active_trigger = any(
            e["recency_days"] is not None and e["recency_days"] <= 60
            for e in trigger_events
        )

        data: dict[str, Any] = {
            "trigger_events": trigger_events,
            "has_active_trigger": has_active_trigger,
            "confidence": confidence,
            "reasoning": reasoning,
            "searches_performed": searches_performed,
        }

        reason = "triggers_found" if trigger_events else "no_triggers_found"

        logger.info(
            "claude_web_triggers contact_id=%s triggers=%d active=%s confidence=%.2f cost_cents=%d",
            contact_id, len(trigger_events), has_active_trigger, confidence, self.cost_cents_per_call,
        )

        return EnrichResult(
            adapter_name=self.name,
            ok=True,
            cost_cents=self.cost_cents_per_call,
            reason=reason,
            data=data,
            raw_response={},
        )
