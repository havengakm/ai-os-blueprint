"""Claude Sonnet deep research adapter — multi-page scrape + extraction.

Fetches up to 8 pages from the company's domain and LinkedIn, then calls
Claude Sonnet to extract citable details and buying signals. Uses real
scraped content rather than prior knowledge — every detail must cite a source.

MONEY PATH: every completed API call costs real money. Rules:
  - No retries — billed call, retries multiply charges.
  - dry_run must NEVER reach the API or the browser.
  - Parse failures still record cost_cents (Claude was billed regardless).
  - Infrastructure errors propagate — orchestrator handles accounting.
  - Per-page errors are caught and logged; scrape continues to next page.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

from playwright.async_api import async_playwright

from systems.scout.enrich.base import EnrichResult


logger = logging.getLogger(__name__)

# Haiku 4.5 per CLAUDE.md cost rules. Deep Research runs per-contact
# at ~$0.003-0.005 on Haiku vs ~$0.03-0.04 on Sonnet — the single biggest
# cost item in the enrich stage.
HAIKU_MODEL = "claude-haiku-4-5-20251001"
# Bumped from 800 -> 1200 to accommodate the structural_signals array (Task C).
# Validator caps structural_signals at 8 entries, so cost stays bounded.
MAX_TOKENS = 1200
# Trimmed from 20_000 -> 12_000. With Haiku at $0.80/M input we still
# pay for every token, and most studio sites fit inside 12k char after
# HTML stripping. Budget: 12_000 chars ≈ 3_000 tokens × $0.80/M ≈ $0.0024.
CONTENT_CHAR_LIMIT = 12_000
# Trimmed from 8 -> 5 pages. Most signal + identity lives on home +
# about + team + services; 5 is plenty and saves ~3 page-fetches × ~4k
# chars = ~12k tokens per contact.
MAX_PAGES = 5
FETCH_GAP_SECONDS = 1.0

VALID_PAIN_CATEGORIES = frozenset(
    {"pipeline", "delivery", "retention", "positioning", "pricing", "team", "tooling", "other"}
)
ACTIVE_SIGNAL_CATEGORIES = frozenset(
    {"hiring", "expansion", "product_launch", "leadership_change", "funding"}
)
VALID_SIGNAL_CATEGORIES = ACTIVE_SIGNAL_CATEGORIES | {"tooling", "other"}

# Structural signals: canonical 5-category B2B Signal Taxonomy.
# Source: data/reference/signals/b2b-signal-taxonomy.md
# Icebreaker adapter Tier 3 reads research_data.structural_signals[].
VALID_STRUCTURAL_CATEGORIES = frozenset({
    "operational_organizational", "financial_growth", "technographic",
    "social_engagement", "negative_pain",
})

VALID_STRUCTURAL_TYPES_BY_CATEGORY: dict[str, frozenset[str]] = {
    "operational_organizational": frozenset({
        "new_leadership", "hiring_spike", "headless_growth",
        "geographic_expansion", "m_and_a",
    }),
    "financial_growth": frozenset({
        "funding_round", "major_contract_win", "ipo_filing",
        "profitability_milestone",
    }),
    "technographic": frozenset({
        "software_migration", "trial_tool_install", "legacy_decay",
        "emerging_tech_adoption",
    }),
    "social_engagement": frozenset({
        "how_to_query", "problem_aware_engagement", "alumni_move",
        "event_attendance", "referral_request",
    }),
    "negative_pain": frozenset({
        "downsizing", "cs_failure", "market_share_decline",
        "founder_burnout",
    }),
}

_COMPANY_PATHS = [
    "/about", "/about-us", "/services", "/what-we-do", "/approach",
    "/methodology", "/case-studies", "/clients", "/portfolio", "/work",
    "/testimonials", "/team", "/our-team", "/leadership", "/blog",
]

# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------
_SCRIPT_RE = re.compile(r"<script[^>]*>.*?</script>", re.I | re.S)
_STYLE_RE = re.compile(r"<style[^>]*>.*?</style>", re.I | re.S)
_NAV_RE = re.compile(r"<nav[^>]*>.*?</nav>", re.I | re.S)
_FOOTER_RE = re.compile(r"<footer[^>]*>.*?</footer>", re.I | re.S)


_CODE_FENCE_OPEN_RE = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)
_CODE_FENCE_CLOSE_RE = re.compile(r"\s*```\s*$")


def _strip_code_fences(text: str) -> str:
    """Strip optional ```json ... ``` fences. No-op on clean JSON.

    Claude Sonnet 4.6 usually returns strict JSON when asked, but
    occasionally wraps responses in ```json fences in complex-prompt
    contexts. This rescues those without mangling clean responses.
    """
    out = _CODE_FENCE_OPEN_RE.sub("", text)
    out = _CODE_FENCE_CLOSE_RE.sub("", out)
    return out


def _clean_html(raw: str) -> str:
    """Strip scripts, styles, navs, footers from HTML."""
    html = _SCRIPT_RE.sub("", raw)
    html = _STYLE_RE.sub("", html)
    html = _NAV_RE.sub("", html)
    html = _FOOTER_RE.sub("", html)
    return html


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------

def _company_page_urls(domain: str) -> list[str]:
    base = domain.rstrip("/")
    if not base.startswith("http"):
        base = f"https://{base}"
    return [f"{base}{path}" for path in _COMPANY_PATHS]


def _linkedin_urls(company: str) -> list[str]:
    slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")
    return [
        f"https://www.linkedin.com/company/{slug}/",
        f"https://www.linkedin.com/company/{slug}/posts/",
    ]


# ---------------------------------------------------------------------------
# Playwright fetch helper
# ---------------------------------------------------------------------------

async def _fetch_html(browser: Any, url: str) -> str | None:
    """Fetch a single page; return HTML or None on any error."""
    context = await browser.new_context()
    try:
        page = await context.new_page()
        response = await page.goto(url, timeout=15000, wait_until="domcontentloaded")
        if not response or response.status >= 400:
            return None
        return await page.content()
    except Exception as exc:
        logger.debug("_fetch_html error url=%s exc=%s", url, exc)
        return None
    finally:
        await context.close()


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_citable_details(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if not all(k in item for k in ("type", "detail", "source")):
            continue
        out.append({
            "type": str(item["type"]),
            "detail": str(item["detail"])[:160],
            "source": str(item["source"]),
        })
        if len(out) >= 8:
            break
    return out


def _validate_buying_signals(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if not all(k in item for k in ("category", "detail", "source")):
            continue
        category = str(item["category"])
        if category not in VALID_SIGNAL_CATEGORIES:
            continue
        out.append({
            "category": category,
            "detail": str(item["detail"])[:160],
            "source": str(item["source"]),
        })
        if len(out) >= 8:
            break
    return out


def _validate_structural_signals(
    raw: Any,
    *,
    sources_fetched: list[str],
) -> list[dict[str, str]]:
    """Validate structural_signals against the 5-category taxonomy.

    Drops entries that are not dicts, miss required keys, use unknown categories
    or subtypes, or cite an evidence_url that was not in sources_fetched (prevents
    Claude from inventing URLs). Truncates summary to 200 chars. Caps at 8.
    """
    if not isinstance(raw, list):
        return []
    allowed_urls = set(sources_fetched)
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if not all(k in item for k in ("category", "type", "evidence_url", "summary")):
            continue
        category = str(item["category"])
        if category not in VALID_STRUCTURAL_CATEGORIES:
            continue
        subtype = str(item["type"])
        if subtype not in VALID_STRUCTURAL_TYPES_BY_CATEGORY[category]:
            continue
        evidence_url = str(item["evidence_url"])
        if evidence_url not in allowed_urls:
            continue
        out.append({
            "category": category,
            "type": subtype,
            "evidence_url": evidence_url,
            "summary": str(item["summary"])[:200],
        })
        if len(out) >= 8:
            break
    return out


def _default_data() -> dict[str, Any]:
    return {
        "citable_details": [],
        "buying_signals": [],
        "structural_signals": [],
        "pain_match": "",
        "pain_category": "other",
        "has_active_buying_signal": False,
        "confidence": 0.0,
        "reasoning": "",
        "sources_fetched": [],
    }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a B2B research analyst. Given scraped website content about a company, "
    "extract citable details, buying signals, and structural signals. "
    "Return strict JSON only, no prose, no code fences. "
    "Never invent specifics. Every detail must have a source from the content."
)

_USER_TEMPLATE = """\
Company: {company}
Domain: {domain}
Industry: {industry}
Employees: {employees}
Contact title: {title}
{trigger_block}
<available_source_urls>
{sources_list}
</available_source_urls>

<scraped_content>
{content}
</scraped_content>

Extract research from the scraped content above. Return STRICT JSON with this exact shape, no prose, no code fences:

{{
  "citable_details": [
    {{"type": "case_study", "detail": "specific result <= 160 chars", "source": "case_studies"}}
  ],
  "buying_signals": [
    {{"category": "hiring", "detail": "specific signal <= 160 chars", "source": "about"}}
  ],
  "structural_signals": [
    {{"category": "financial_growth", "type": "funding_round", "evidence_url": "<one of available_source_urls>", "summary": "plain-language 1 sentence <= 200 chars"}}
  ],
  "pain_match": "most likely business pain <= 160 chars",
  "pain_category": "pipeline|delivery|retention|positioning|pricing|team|tooling|other",
  "confidence": 0.0,
  "reasoning": "<= 240 chars"
}}

Valid buying_signal.category values: hiring, expansion, tooling, product_launch, leadership_change, funding, other.
Valid pain_category values: pipeline, delivery, retention, positioning, pricing, team, tooling, other.

structural_signals: classify any business-movement hits against this 5-category taxonomy. Use EXACTLY these slug values.

  - operational_organizational: new_leadership, hiring_spike, headless_growth, geographic_expansion, m_and_a
  - financial_growth: funding_round, major_contract_win, ipo_filing, profitability_milestone
  - technographic: software_migration, trial_tool_install, legacy_decay, emerging_tech_adoption
  - social_engagement: how_to_query, problem_aware_engagement, alumni_move, event_attendance, referral_request
  - negative_pain: downsizing, cs_failure, market_share_decline, founder_burnout

Rules for structural_signals:
  - evidence_url MUST be one of the URLs listed in <available_source_urls>. Do not invent URLs.
  - summary is plain-language, 1 sentence, <= 200 chars, no jargon, no buzzwords.
  - Only include structural_signals that are directly stated in the scraped content. Do not guess or infer.

Only include entries that are directly supported by the scraped content.\
"""


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class ClaudeDeepResearchAdapter:
    """Heavy research adapter — multi-page scrape + Claude Sonnet extraction.

    Fetches up to 8 pages from the company domain and LinkedIn, aggregates
    the cleaned HTML, then calls Claude Sonnet to extract:
      - citable_details: concrete facts with sources (case studies, results)
      - buying_signals: live signals from scraped content
      - pain_match / pain_category: most likely business pain
      - has_active_buying_signal: computed from signals + trigger_events
      - confidence / reasoning: Claude's self-assessment

    Lifecycle mirrors ClaudeIdentityScraper (ef30029):
      - Lazy browser + client; _browser_provided / _anthropic_provided flags
      - aclose() closes only lazily-created resources; idempotent
      - NO __aenter__ / __aexit__
    """

    name: str = "claude_deep_research"
    cost_cents_per_call: int = 3  # ~2.3c Sonnet, rounded up

    def __init__(
        self,
        browser: Any = None,
        anthropic_client: Any = None,
    ) -> None:
        self._browser = browser
        self._browser_provided = browser is not None
        self._anthropic_client = anthropic_client
        self._anthropic_provided = anthropic_client is not None
        self._playwright_ctx: Any = None

    async def _ensure_browser(self) -> Any:
        if self._browser is None:
            self._playwright_ctx = await async_playwright().start()
            self._browser = await self._playwright_ctx.chromium.launch(headless=True)
        return self._browser

    async def _ensure_anthropic_client(self) -> Any:
        if self._anthropic_client is None:
            from anthropic import AsyncAnthropic
            self._anthropic_client = AsyncAnthropic()
        return self._anthropic_client

    async def aclose(self) -> None:
        """Close lazily-created browser + Anthropic client. Idempotent."""
        if self._browser is not None and not self._browser_provided:
            try:
                await self._browser.close()
            finally:
                self._browser = None
        if self._playwright_ctx is not None:
            try:
                await self._playwright_ctx.stop()
            finally:
                self._playwright_ctx = None
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
        """Deep research enrichment for a contact.

        Skip paths (no network, cost_cents=0):
          - dry_run=True
          - ANTHROPIC_API_KEY unset
          - company blank
          - company_domain blank

        Parse failures: ok=True, cost_cents=cost_cents_per_call (Claude was billed).
        No-content: ok=True, cost_cents=0 (Claude not called).
        Infrastructure errors propagate.
        """
        contact_id = contact.get("contact_id", "<unknown>")

        # --- dry run ---
        if dry_run:
            logger.debug("claude_deep_research dry_run contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=True,
                data={},
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

        # --- domain guard ---
        domain = (contact.get("company_domain") or "").strip()
        if not domain:
            return EnrichResult(
                adapter_name=self.name,
                ok=False,
                data={},
                cost_cents=0,
                reason="no_domain",
            )

        # --- fetch pages ---
        # LinkedIn URLs FIRST (2 pages) so they always get a shot before MAX_PAGES is
        # consumed by empty/404 company pages. Company paths follow. Earlier versions
        # put company paths first + sliced the combined list, making LinkedIn URLs
        # (then at positions 15-16) permanently unreachable. Now LinkedIn is at
        # positions 0-1 and the natural loop termination at MAX_PAGES leaves ~6 slots
        # for company pages after LinkedIn. If LinkedIn is blocked / empty in production
        # it costs 2 slots of the 8-page budget — acceptable tradeoff because LinkedIn
        # surfaces the freshest trigger events (recent posts, funding, exec changes).
        all_urls = _linkedin_urls(company) + _company_page_urls(domain)
        browser = await self._ensure_browser()

        sources_fetched: list[str] = []
        content_parts: list[str] = []
        pages_attempted = 0

        for url in all_urls:
            if pages_attempted >= MAX_PAGES:
                break
            pages_attempted += 1
            try:
                html = await _fetch_html(browser, url)
            except Exception as exc:
                logger.warning("claude_deep_research fetch error url=%s exc=%s", url, exc)
                continue
            if html:
                cleaned = _clean_html(html)
                if cleaned.strip():
                    sources_fetched.append(url)
                    content_parts.append(cleaned)
            if pages_attempted < MAX_PAGES:
                await asyncio.sleep(FETCH_GAP_SECONDS)

        # --- no content path ---
        if not content_parts:
            data = _default_data()
            data["sources_fetched"] = sources_fetched
            return EnrichResult(
                adapter_name=self.name,
                ok=True,
                data=data,
                cost_cents=0,
                reason="no_content_scraped",
            )

        aggregated = "".join(content_parts)[:CONTENT_CHAR_LIMIT]

        # --- build prompt ---
        trigger_events = contact.get("trigger_events") or []
        if trigger_events:
            trigger_lines = "\n".join(
                f"  - {te.get('type', 'unknown')} ({te.get('recency_days', '?')} days ago)"
                for te in trigger_events
            )
            trigger_block = f"Trigger events:\n{trigger_lines}\n"
        else:
            trigger_block = ""

        sources_list = "\n".join(sources_fetched)

        user_message = _USER_TEMPLATE.format(
            company=company,
            domain=domain,
            industry=contact.get("industry") or "unknown",
            employees=contact.get("employees") or "unknown",
            title=contact.get("title") or "unknown",
            trigger_block=trigger_block,
            sources_list=sources_list,
            content=aggregated,
        )

        # --- Claude call (no try/except — infrastructure errors propagate) ---
        client = await self._ensure_anthropic_client()
        response = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw_text = response.content[0].text.strip()

        # --- parse (defensive: strip optional ```json fences) ---
        parse_text = _strip_code_fences(raw_text)
        try:
            parsed: dict[str, Any] = json.loads(parse_text)
        except json.JSONDecodeError:
            logger.warning(
                "claude_deep_research parse_failed contact_id=%s raw=%r",
                contact_id, raw_text[:200],
            )
            data = _default_data()
            data["sources_fetched"] = sources_fetched
            return EnrichResult(
                adapter_name=self.name,
                ok=True,
                cost_cents=self.cost_cents_per_call,
                reason="parse_failed",
                data=data,
                raw_response={"raw_text": raw_text},
            )

        # --- validate ---
        citable_details = _validate_citable_details(parsed.get("citable_details"))
        buying_signals = _validate_buying_signals(parsed.get("buying_signals"))
        structural_signals = _validate_structural_signals(
            parsed.get("structural_signals"),
            sources_fetched=sources_fetched,
        )

        pain_match = str(parsed.get("pain_match") or "")[:160]
        pain_category = str(parsed.get("pain_category") or "other")
        if pain_category not in VALID_PAIN_CATEGORIES:
            pain_category = "other"

        confidence = float(parsed.get("confidence") or 0.0)
        confidence = max(0.0, min(1.0, confidence))
        reasoning = str(parsed.get("reasoning") or "")[:240]

        # --- has_active_buying_signal ---
        signal_active = any(
            s["category"] in ACTIVE_SIGNAL_CATEGORIES for s in buying_signals
        )
        trigger_active = any(
            int((te.get("recency_days") or 999)) < 90
            for te in trigger_events
        )
        has_active_buying_signal = signal_active or trigger_active

        data = {
            "citable_details": citable_details,
            "buying_signals": buying_signals,
            "structural_signals": structural_signals,
            "pain_match": pain_match,
            "pain_category": pain_category,
            "has_active_buying_signal": has_active_buying_signal,
            "confidence": confidence,
            "reasoning": reasoning,
            "sources_fetched": sources_fetched,
        }

        if citable_details or buying_signals or structural_signals:
            reason = "research_complete"
        else:
            reason = "research_complete_sparse"

        logger.info(
            "claude_deep_research contact_id=%s category=%s confidence=%.2f "
            "citable=%d signals=%d structural=%d cost_cents=%d",
            contact_id, pain_category, confidence,
            len(citable_details), len(buying_signals), len(structural_signals),
            self.cost_cents_per_call,
        )

        return EnrichResult(
            adapter_name=self.name,
            ok=True,
            cost_cents=self.cost_cents_per_call,
            reason=reason,
            data=data,
            raw_response={"raw_text": raw_text},
        )
