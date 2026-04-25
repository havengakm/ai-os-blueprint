"""Icebreaker adapter — 4-tier Claude Sonnet icebreaker generator.

Stage-level post-processor (NOT an EnrichAdapter in TIER_ADAPTERS). Runs
AFTER the enrich orchestrator fan-out, inside ``EnrichStage._run()``,
because it needs access to BOTH the trigify adapter's ``trigger_events``
AND the deep-research adapter's ``structural_signals`` / ``citable_details``
— merged data only exists after fan-out.

Tier ladder (deterministic, in Python):
  Tier 1  frustrated social post within 14d (competitor rage, SDR burnout,
          tool complaint) — match against a keyword regex.
  Tier 2  neutral engagement on relevant content within 14d.
  Tier 3  structural signal (funding / hiring / leadership / M&A).
  Tier 4  website fallback — cite a specific project / named client /
          testimonial / case study from the scraped content.

The 4 prompt templates live on disk under ``prompts/`` and are loaded
ONCE at adapter init. Post-generation validators (regex-based) fail
closed and retry ONCE on banned words or anti-stalker hits.

MONEY PATH:
  - Every completed Claude call costs real money.
  - Retry is capped at 1 (worst case: 2x cost_cents_per_call).
  - dry_run, no_api_key, budget_exhausted short-circuit BEFORE the call.
  - Parse failures still record cost_cents (Claude was billed).
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


logger = logging.getLogger(__name__)

# Haiku 4.5 used for pipeline/batch ops per CLAUDE.md cost rules.
# The icebreaker generator runs per-contact at ~$0.0003/call vs Sonnet's
# $0.003 — critical for hitting the $0.002/contact cost target.
HAIKU_MODEL = "claude-haiku-4-5-20251001"
# Icebreakers are at most 2 sentences + JSON wrapper. 200 is plenty.
MAX_TOKENS = 200

# Recency window for trigify-based tiers. Signals older than this fall
# through to Tier 3 / 4.
RECENCY_WINDOW_DAYS = 14

_PROMPTS_DIR = Path(__file__).parent / "prompts"


# --------------------------------------------------------------------------- #
# Defensive parse helper — Claude occasionally wraps JSON in code fences        #
# --------------------------------------------------------------------------- #

_CODE_FENCE_OPEN_RE = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)
_CODE_FENCE_CLOSE_RE = re.compile(r"\s*```\s*$")


def _strip_code_fences(text: str) -> str:
    """Strip optional ```json ... ``` fences. No-op on clean JSON."""
    out = _CODE_FENCE_OPEN_RE.sub("", text)
    out = _CODE_FENCE_CLOSE_RE.sub("", out)
    return out


# --------------------------------------------------------------------------- #
# Tier-selection regexes                                                        #
# --------------------------------------------------------------------------- #

_FRUSTRATION_PATTERN = re.compile(
    r"\b(frustrated|annoyed|hate|tired of|sick of|fed up|stuck|struggling|"
    r"burnt out|burned out|nightmare|ridiculous|useless|broken|painful|"
    r"rant|done with|over it|had enough)\b",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Post-generation validators                                                    #
# --------------------------------------------------------------------------- #

_BANNED_WORDS_RE = re.compile(
    # Legacy bans (kept from v1 prompts).
    r"\b(impressed|remarkable|leverage|solution|optimize|synergy|"
    r"cutting[- ]edge|AI[- ]powered|AI whatever|operating system|autonomous|"
    r"workflow|"
    # v2 creative_branding bans (Kirsten's revised voice rules).
    # Excludes "scale" and "pipeline" from the legacy set so "scaling"
    # and "pipeline" both match as stems of the broader ban list below.
    r"scale|scaling|pipeline|headcount|BD|business development|capacity|"
    r"inbound|outrun|runway|growth metrics|gap|mood[- ]board|craft|"
    # v3: "lead gen" carries bad industry connotations per Kirsten —
    # prefer "growth systems" in copy. Matched as a whole phrase.
    r"lead gen|"
    # v3.1: corporate/consulting jargon that survived the banned-word list
    # and leaked into live drafts (Jonathan/Inkblot, Madelain/PR Worx).
    # Unambiguous single-word bans only; "engagement" / "positioning" /
    # "landscape" / "space" stay in the prompt text because they have
    # legitimate narrow uses (engagement rates, brand positioning).
    r"signalling|signaling|ecosystem|high[- ]growth)\b",
    re.IGNORECASE,
)

# Diagnostic phrases Kirsten explicitly rejected — they read as the writer
# playing consultant. Checked as substrings (case-insensitive) because they
# span whitespace and punctuation.
_BANNED_DIAGNOSTIC_PHRASES: tuple[str, ...] = (
    "usually means", "which suggests", "points to", "feels like",
    "the gap between", "this tells me", "that tends to", "which means",
    # v3.1 additions: consultant paraphrase phrases that leaked into
    # live drafts. Substrings, not word-bounded, because they span
    # punctuation ("explicitly cited as driver").
    "cited as", "driver behind", "member profile active",
    "uniquely positioned", "transformation journey",
    "pursuing expansion", "market entry", "market expansion",
)

# "operations" matches literal bans too. "typically" is a stem of diagnostic
# phrases — checked here separately because it's too common as a standalone
# English word to treat as a regex-blacklist. Operators can add fresh
# diagnostic phrases without touching regex.

# Separate from the word regex: these are characters / substrings, not
# whole words. Checked with plain substring search. Em dash is BANNED per
# rules/global-writing-guardrails.md section 2 (operator decision 2026-04-25
# after PR Worx live draft rendered with "South African PR — that's").
# v2 prompts previously allowed em dash as a clause joiner; that exemption
# is removed and the prompts now instruct Claude to use commas / periods.
_BANNED_CHARS: tuple[str, ...] = ("—",)  # em dash
_BANNED_URL_FRAGMENTS = ("http", "calendly", ".com/")

_ANTI_STALKER_RE = re.compile(
    r"\b(you liked|you commented|you engaged|your post)\b",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Result                                                                        #
# --------------------------------------------------------------------------- #

@dataclass
class IcebreakerResult:
    """What the icebreaker adapter returns per contact.

    ``ok`` indicates the call completed OR was deliberately skipped
    cleanly. Always inspect ``reason`` before using ``icebreaker_content``.
    """

    ok: bool
    icebreaker_content: str
    tier: int
    cost_cents: int
    reason: str


# --------------------------------------------------------------------------- #
# Budget tracker protocol (mirrors enrich orchestrator)                         #
# --------------------------------------------------------------------------- #

class BudgetTracker(Protocol):
    """Tier-budget accounting; same shape as the enrich orchestrator uses."""

    async def remaining_cents(self, client_id: str, tier: str) -> int: ...
    async def record_spend(self, client_id: str, tier: str, cents: int) -> None: ...


# --------------------------------------------------------------------------- #
# Adapter                                                                       #
# --------------------------------------------------------------------------- #

class IcebreakerAdapter:
    """4-tier Claude Sonnet icebreaker generator.

    Reads ``merged_research_data`` from the enrich fan-out, selects a tier
    deterministically in Python, then calls Claude Sonnet with a tier-
    specific prompt loaded from ``systems/scout/enrich/prompts/``.

    Post-generation validators (regex-based):
      - banned_words: fail-closed retry-once
      - anti-stalker (tiers 1-2 only): fail-closed retry-once
    """

    name: str = "icebreaker"
    cost_cents_per_call: int = 1  # ~1c Sonnet per call (200-token cap)

    def __init__(
        self,
        *,
        budget_tracker: BudgetTracker,
        anthropic_client: Any = None,
    ) -> None:
        self._budget_tracker = budget_tracker
        self._anthropic_client = anthropic_client
        self._anthropic_provided = anthropic_client is not None

        # Prompts loaded ONCE at adapter init. File I/O here is fine —
        # the stage builds the adapter once per run, not per contact.
        self._prompts: dict[int, str] = {
            1: (_PROMPTS_DIR / "icebreaker_tier_1.md").read_text(),
            2: (_PROMPTS_DIR / "icebreaker_tier_2.md").read_text(),
            3: (_PROMPTS_DIR / "icebreaker_tier_3.md").read_text(),
            4: (_PROMPTS_DIR / "icebreaker_tier_4.md").read_text(),
        }

    async def _ensure_anthropic_client(self) -> Any:
        if self._anthropic_client is None:
            from anthropic import AsyncAnthropic
            self._anthropic_client = AsyncAnthropic()
        return self._anthropic_client

    async def aclose(self) -> None:
        """Close the lazily-created Anthropic client. Idempotent."""
        if self._anthropic_client is not None and not self._anthropic_provided:
            try:
                await self._anthropic_client.close()
            finally:
                self._anthropic_client = None

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def generate(
        self,
        *,
        contact: dict[str, Any],
        merged_research_data: dict[str, Any],
        client_id: str,
        tier_budget: str,
        dry_run: bool = False,
    ) -> IcebreakerResult:
        """Generate an icebreaker for a contact.

        Skip paths (no Claude call, cost_cents=0):
          - dry_run=True                        → reason='dry_run_skipped'
          - ANTHROPIC_API_KEY unset             → reason='no_api_key'
          - budget exhausted (pre-call)         → reason='budget_exhausted'
          - no source material in merged data   → reason='no_source_material'

        Retry-exhausted paths (Claude called twice, billed twice):
          - reason='banned_word_retry_exhausted'   icebreaker_content=''
          - reason='anti_stalker_retry_exhausted'  icebreaker_content=''

        Parse failure (Claude called once, billed once):
          - reason='parse_failed'  icebreaker_content=''

        Success:
          - reason='tier_N_generated'  icebreaker_content=<sentence>
        """
        contact_id = contact.get("contact_id", "<unknown>")

        # --- dry run ---
        if dry_run:
            logger.debug("icebreaker dry_run contact_id=%s", contact_id)
            return IcebreakerResult(
                ok=True,
                icebreaker_content="",
                tier=0,
                cost_cents=0,
                reason="dry_run_skipped",
            )

        # --- API key guard ---
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return IcebreakerResult(
                ok=False,
                icebreaker_content="",
                tier=0,
                cost_cents=0,
                reason="no_api_key",
            )

        # --- tier selection (deterministic) ---
        trigger_events = merged_research_data.get("trigger_events") or []
        structural_signals = merged_research_data.get("structural_signals") or []
        citable_details = merged_research_data.get("citable_details") or []

        tier, selected_event = _select_tier(
            trigger_events=trigger_events,
            structural_signals=structural_signals,
            citable_details=citable_details,
        )

        if tier == 0:
            return IcebreakerResult(
                ok=True,
                icebreaker_content="",
                tier=0,
                cost_cents=0,
                reason="no_source_material",
            )

        # --- budget pre-check ---
        try:
            remaining = await self._budget_tracker.remaining_cents(
                client_id, tier_budget
            )
        except Exception as exc:
            # Fail safe: a tracker outage is not a reason to silently burn
            # money. Treat as exhausted.
            logger.warning(
                "icebreaker budget_tracker error contact_id=%s exc=%s",
                contact_id, exc,
            )
            remaining = -1

        if remaining < self.cost_cents_per_call:
            return IcebreakerResult(
                ok=True,
                icebreaker_content="",
                tier=tier,
                cost_cents=0,
                reason="budget_exhausted",
            )

        # --- build prompt ---
        prompt = _render_prompt(
            template=self._prompts[tier],
            tier=tier,
            contact=contact,
            selected_event=selected_event,
            citable_details=citable_details,
        )

        # --- first Claude call ---
        client = await self._ensure_anthropic_client()
        icebreaker = await _call_claude(client, prompt)
        total_cost_cents = self.cost_cents_per_call

        if icebreaker is None:
            # Parse failure — billed once.
            await self._record_spend_safely(
                client_id, tier_budget, total_cost_cents
            )
            logger.info(
                "icebreaker parse_failed contact_id=%s tier=%d cost_cents=%d",
                contact_id, tier, total_cost_cents,
            )
            return IcebreakerResult(
                ok=True,
                icebreaker_content="",
                tier=tier,
                cost_cents=total_cost_cents,
                reason="parse_failed",
            )

        # --- truth-gated skip: Claude returned empty string ---
        # v2 prompts instruct Claude to return "" when the source material
        # has no verbatim reference to cite. Treat that as no_source_material
        # (tier=0) — bill once, no retry, the composer falls back cleanly.
        if icebreaker == "":
            await self._record_spend_safely(
                client_id, tier_budget, total_cost_cents
            )
            logger.info(
                "icebreaker truth_gated_skip contact_id=%s tier=%d cost_cents=%d",
                contact_id, tier, total_cost_cents,
            )
            return IcebreakerResult(
                ok=True,
                icebreaker_content="",
                tier=0,
                cost_cents=total_cost_cents,
                reason="no_source_material",
            )

        # --- validate first response ---
        violation = _validate(icebreaker, tier=tier)

        if violation is None:
            await self._record_spend_safely(
                client_id, tier_budget, total_cost_cents
            )
            logger.info(
                "icebreaker tier_%d_generated contact_id=%s cost_cents=%d",
                tier, contact_id, total_cost_cents,
            )
            return IcebreakerResult(
                ok=True,
                icebreaker_content=icebreaker,
                tier=tier,
                cost_cents=total_cost_cents,
                reason=f"tier_{tier}_generated",
            )

        # --- retry ONCE with nudge ---
        retry_prompt = prompt + (
            f"\n\nREGENERATE. Your previous draft was:\n{icebreaker!r}\n\n"
            f"It violated a rule: {violation}. "
            f"Keep the same angle but rewrite to remove that violation."
        )
        icebreaker_retry = await _call_claude(client, retry_prompt)
        total_cost_cents += self.cost_cents_per_call

        await self._record_spend_safely(
            client_id, tier_budget, total_cost_cents
        )

        if icebreaker_retry is None:
            logger.info(
                "icebreaker retry_parse_failed contact_id=%s tier=%d cost_cents=%d",
                contact_id, tier, total_cost_cents,
            )
            return IcebreakerResult(
                ok=True,
                icebreaker_content="",
                tier=tier,
                cost_cents=total_cost_cents,
                reason="parse_failed",
            )

        second_violation = _validate(icebreaker_retry, tier=tier)
        if second_violation is None:
            logger.info(
                "icebreaker tier_%d_generated_after_retry contact_id=%s cost_cents=%d",
                tier, contact_id, total_cost_cents,
            )
            return IcebreakerResult(
                ok=True,
                icebreaker_content=icebreaker_retry,
                tier=tier,
                cost_cents=total_cost_cents,
                reason=f"tier_{tier}_generated",
            )

        # --- both attempts failed validation ---
        if second_violation.startswith("anti_stalker"):
            reason = "anti_stalker_retry_exhausted"
        else:
            reason = "banned_word_retry_exhausted"
        logger.info(
            "icebreaker %s contact_id=%s tier=%d cost_cents=%d",
            reason, contact_id, tier, total_cost_cents,
        )
        return IcebreakerResult(
            ok=True,
            icebreaker_content="",
            tier=tier,
            cost_cents=total_cost_cents,
            reason=reason,
        )

    async def _record_spend_safely(
        self,
        client_id: str,
        tier: str,
        cents: int,
    ) -> None:
        """Debit budget; swallow tracker failures (non-fatal to stage)."""
        if cents <= 0:
            return
        try:
            await self._budget_tracker.record_spend(client_id, tier, cents)
        except Exception as exc:
            logger.warning(
                "icebreaker record_spend failed client_id=%s tier=%s cents=%d exc=%s",
                client_id, tier, cents, exc,
            )


# --------------------------------------------------------------------------- #
# Tier selection                                                                #
# --------------------------------------------------------------------------- #

def _select_tier(
    *,
    trigger_events: list[dict[str, Any]],
    structural_signals: list[dict[str, Any]],
    citable_details: list[dict[str, Any]],
) -> tuple[int, dict[str, Any] | None]:
    """Deterministic tier selection. Returns (tier, selected_event_or_signal).

    tier == 0 means nothing to generate from.

    For tiers 1-2 the second element is the selected trigger_event.
    For tier 3 it is the selected structural_signal.
    For tier 4 it is None (the full citable_details list is passed to the
    prompt builder instead).
    """
    recent = [te for te in trigger_events if _recency_ok(te)]
    if recent:
        frustrated = [
            te for te in recent
            if _FRUSTRATION_PATTERN.search(str(te.get("detail") or ""))
        ]
        if frustrated:
            return 1, frustrated[0]
        return 2, recent[0]
    if structural_signals:
        return 3, structural_signals[0]
    if citable_details:
        return 4, None
    return 0, None


def _recency_ok(te: dict[str, Any]) -> bool:
    """True when a trigger event is within the RECENCY_WINDOW_DAYS window.

    Missing / None / unparseable ``recency_days`` is treated as stale.
    """
    try:
        return int(te.get("recency_days") or 999) <= RECENCY_WINDOW_DAYS
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------------------- #
# Prompt rendering                                                              #
# --------------------------------------------------------------------------- #

def _derive_short_company(company: str) -> str:
    """Strip common suffixes for the ``{short_company_name}`` placeholder.

    "Acme Consulting Ltd" -> "Acme Consulting"
    """
    if not company:
        return ""
    trimmed = company.strip()
    suffixes = (
        " Ltd", " LLC", " Inc", " Inc.", " Corp", " Corp.", " Co.",
        " Pty Ltd", " GmbH", " S.A.", ", Inc.", ", LLC",
    )
    for suffix in suffixes:
        if trimmed.endswith(suffix):
            return trimmed[: -len(suffix)].rstrip(",")
    return trimmed


def _render_prompt(
    *,
    template: str,
    tier: int,
    contact: dict[str, Any],
    selected_event: dict[str, Any] | None,
    citable_details: list[dict[str, Any]],
) -> str:
    """Render a tier prompt with runtime context injected.

    All placeholders use ``{}.format()``; the prompt files escape literal
    braces (`{{`, `}}`) as needed so JSON examples pass through.
    """
    company = str(contact.get("company") or "").strip()
    first_name = str(contact.get("first_name") or "").strip()
    short_company = _derive_short_company(company)

    base_fields: dict[str, str] = {
        "company": company or "(unknown)",
        "first_name": first_name or "(unknown)",
        "short_company_name": short_company or company or "(unknown)",
    }

    if tier == 1:
        ev = selected_event or {}
        base_fields["frustrated_post_text"] = str(ev.get("detail") or "")
        base_fields["frustrated_post_source"] = str(
            ev.get("source") or ev.get("platform") or "trigify"
        )
    elif tier == 2:
        ev = selected_event or {}
        base_fields["engaged_content_text"] = str(ev.get("detail") or "")
        base_fields["engaged_content_source"] = str(
            ev.get("source") or ev.get("platform") or "trigify"
        )
    elif tier == 3:
        sig = selected_event or {}
        base_fields["signal_category"] = _humanize_taxonomy_slug(
            str(sig.get("category") or "unknown")
        )
        base_fields["signal_type"] = _humanize_taxonomy_slug(
            str(sig.get("type") or "unknown")
        )
        base_fields["signal_summary"] = str(sig.get("summary") or "")
    elif tier == 4:
        base_fields["citable_details_bulleted"] = _format_citables(citable_details)

    return template.format(**base_fields)


def _humanize_taxonomy_slug(slug: str) -> str:
    """Turn internal taxonomy slugs into friendly prose for Claude prompts.

    Internal: 'funding_round' | 'operational_organizational' | 'm_and_a'
    Friendly: 'funding round' | 'operational organizational' | 'm and a'
    """
    return slug.replace("_", " ").strip() or "unknown"


def _format_citables(citable_details: list[dict[str, Any]]) -> str:
    """Render citable_details as a bullet list for the Tier 4 prompt."""
    if not citable_details:
        return "(none)"
    lines: list[str] = []
    for cd in citable_details[:8]:
        cd_type = str(cd.get("type") or "detail")
        cd_detail = str(cd.get("detail") or "").strip()
        cd_source = str(cd.get("source") or "website")
        if not cd_detail:
            continue
        lines.append(f"- [{cd_type} @ {cd_source}] {cd_detail}")
    return "\n".join(lines) if lines else "(none)"


# --------------------------------------------------------------------------- #
# Claude call + parsing                                                         #
# --------------------------------------------------------------------------- #

async def _call_claude(client: Any, prompt: str) -> str | None:
    """Call Claude Sonnet and extract the ``icebreaker`` field from JSON.

    Returns the icebreaker string, or None on parse failure.
    Infrastructure errors propagate — the stage layer logs them as
    adapter_error in the enrich summary.
    """
    response = await client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text = response.content[0].text.strip()
    parse_text = _strip_code_fences(raw_text)
    try:
        parsed = json.loads(parse_text)
    except json.JSONDecodeError:
        logger.warning("icebreaker parse_failed raw=%r", raw_text[:200])
        return None
    icebreaker = parsed.get("icebreaker") if isinstance(parsed, dict) else None
    if not isinstance(icebreaker, str):
        return None
    return icebreaker.strip()


# --------------------------------------------------------------------------- #
# Post-generation validation                                                    #
# --------------------------------------------------------------------------- #

def _validate(icebreaker: str, *, tier: int) -> str | None:
    """Return None if the icebreaker passes all checks, else a short reason.

    The returned string is used as the retry nudge — something like
    "banned_word:leverage" or "anti_stalker:you liked" or
    "diagnostic_phrase:usually means".

    Empty string is treated as a SKIP (the adapter routes empty output
    to tier=0 via the ``no_source_material`` path before calling this).
    """
    if not icebreaker:
        return "empty"

    m = _BANNED_WORDS_RE.search(icebreaker)
    if m:
        return f"banned_word:{m.group(0)}"

    for ch in _BANNED_CHARS:
        if ch in icebreaker:
            return f"banned_char:{ch!r}"

    lowered = icebreaker.lower()
    for fragment in _BANNED_URL_FRAGMENTS:
        if fragment in lowered:
            return f"banned_word:url_fragment:{fragment}"

    for phrase in _BANNED_DIAGNOSTIC_PHRASES:
        if phrase in lowered:
            return f"diagnostic_phrase:{phrase}"

    # Anti-stalker ONLY applies to social-engagement tiers.
    if tier in (1, 2):
        m = _ANTI_STALKER_RE.search(icebreaker)
        if m:
            return f"anti_stalker:{m.group(0)}"

    return None
