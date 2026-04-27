"""Uncertain-zone LLM augment for the score stage.

Plan 2 Phase 5 Task 2.5.7. When a contact's rule-based ``icp_score``
lands in the uncertain zone (default 40-60, configurable per
``client_config.icp.uncertain_zone``), this judge invokes a Haiku-tier
LLM to return a nudge ∈ {-15, -5, 0, +5, +15} that score_stage applies
to the rule score before tier assignment.

Cost discipline: Haiku, ~250 max_tokens → ~0.1c per call. Only the
~10-20% of contacts in the uncertain zone fire it, keeping per-cohort
cost low.

Skip paths (no Anthropic call, ok=False):
- dry_run=True            → reason='dry_run_skipped', nudge=0
- ANTHROPIC_API_KEY unset → reason='no_api_key', nudge=0

Failure paths (Anthropic called, parse / validation rejected):
- 'parse_failed'        — body wasn't parseable JSON
- 'invalid_nudge_value' — model returned a value outside the canonical set

All failure paths return ``nudge=0`` so the rule-based score stands
on its own — the judge can't make things worse, only refine what's
already a defensible call.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 250

DEFAULT_UNCERTAIN_ZONE_LOW: int = 40
DEFAULT_UNCERTAIN_ZONE_HIGH: int = 60

VALID_NUDGES: frozenset[int] = frozenset({-15, -5, 0, 5, 15})


_PROMPT_PATH = Path(__file__).parent / "prompts" / "uncertain_zone_judge.md"


_CODE_FENCE_OPEN_RE = re.compile(r"^\s*```(?:json)?\s*", re.IGNORECASE)
_CODE_FENCE_CLOSE_RE = re.compile(r"\s*```\s*$")


def _strip_code_fences(text: str) -> str:
    out = _CODE_FENCE_OPEN_RE.sub("", text)
    out = _CODE_FENCE_CLOSE_RE.sub("", out)
    return out.strip()


@dataclass
class NudgeResult:
    """One judge verdict. ``ok=False`` paths still return a usable
    ``nudge=0`` so callers can apply the rule score uniformly."""

    ok: bool
    nudge: int
    reasoning: str
    cost_cents: int
    reason: str


def is_in_uncertain_zone(
    score: int,
    *,
    low: int = DEFAULT_UNCERTAIN_ZONE_LOW,
    high: int = DEFAULT_UNCERTAIN_ZONE_HIGH,
) -> bool:
    """True when ``low <= score <= high`` (inclusive). Callers use this
    to decide whether to dispatch the judge at all — saves the LLM call
    on the ~80% of contacts whose rule score is clearly Tier A or
    clearly archive."""
    return low <= score <= high


def _failed(reason: str) -> NudgeResult:
    return NudgeResult(
        ok=False, nudge=0, reasoning="", cost_cents=0, reason=reason,
    )


class UncertainZoneJudge:
    """Haiku-backed score nudge for uncertain-zone contacts."""

    name: str = "uncertain_zone_judge"
    cost_cents_per_call: int = 0  # Haiku ~0.1c rounds to 0 at int precision

    def __init__(self, *, anthropic_client: Any | None = None) -> None:
        self._anthropic_client = anthropic_client
        self._anthropic_provided = anthropic_client is not None
        self._prompt_template = _PROMPT_PATH.read_text()

    async def _ensure_anthropic_client(self) -> Any:
        if self._anthropic_client is None:
            from anthropic import AsyncAnthropic
            self._anthropic_client = AsyncAnthropic()
        return self._anthropic_client

    async def aclose(self) -> None:
        if self._anthropic_client is not None and not self._anthropic_provided:
            try:
                await self._anthropic_client.close()
            finally:
                self._anthropic_client = None

    async def judge(
        self,
        *,
        contact: dict[str, Any],
        client_icp: dict[str, Any],
        dry_run: bool = False,
    ) -> NudgeResult:
        if dry_run:
            return _failed("dry_run_skipped")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return _failed("no_api_key")

        client = await self._ensure_anthropic_client()
        prompt = self._format_prompt(contact, client_icp)

        msg = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            text = msg.content[0].text
        except (AttributeError, IndexError):
            return _failed("parse_failed")

        try:
            data = json.loads(_strip_code_fences(text))
        except (json.JSONDecodeError, ValueError):
            return _failed("parse_failed")

        if not isinstance(data, dict):
            return _failed("parse_failed")

        try:
            nudge = int(data.get("nudge", 0))
        except (TypeError, ValueError):
            return _failed("parse_failed")

        if nudge not in VALID_NUDGES:
            return _failed("invalid_nudge_value")

        reasoning = str(data.get("reasoning") or "")[:300]

        return NudgeResult(
            ok=True,
            nudge=nudge,
            reasoning=reasoning,
            cost_cents=self.cost_cents_per_call,
            reason="ok",
        )

    def _format_prompt(
        self, contact: dict[str, Any], client_icp: dict[str, Any],
    ) -> str:
        return self._prompt_template.format(
            company=contact.get("company") or "",
            title=contact.get("title") or "",
            industry=contact.get("industry") or "",
            employees=contact.get("employees") if contact.get("employees") is not None else "",
            description=contact.get("company_description") or "",
            geography=contact.get("geography") or "",
            icp_titles=", ".join(client_icp.get("titles") or []) or "(any)",
            icp_industries=", ".join(client_icp.get("industries") or []) or "(any)",
            icp_employee_min=client_icp.get("employee_min", ""),
            icp_employee_max=client_icp.get("employee_max", ""),
            icp_geographies=", ".join(client_icp.get("geographies") or []) or "(any)",
            icp_positive_examples=", ".join(client_icp.get("positive_examples") or []) or "(none provided)",
            icp_negative_examples=", ".join(client_icp.get("negative_examples") or []) or "(none provided)",
        )
