"""Python validator that enforces ``rules/global-writing-guardrails.md``.

Mirrors the hard-rule subset of ``skills/meta/validate-writing.md`` so the
daemon can fail closed on AI-speak, em-dashes, buzzwords, and filler. Used
by:

  - ``IcebreakerAdapter.generate``: post-Claude validation; fail returns
    empty icebreaker_content (caller treats as ``no_source_material`` and
    skips persistence into ``research_data``).
  - ``Composer.compose``: post-render validation on the rendered body; fail
    causes the draft to be skipped (logged in decision_log; not persisted
    to ``outreach_drafts``).

Pure function, zero I/O, zero state. Tests live in
``tests/test_outreach/test_writing_validator.py``.

The Python validator is intentionally a SUBSET of the markdown spec (see
``skills/meta/validate-writing.md``):

  - Hard rules: em-dashes, AI-cliché openers/phrases, buzzwords, filler.
  - Skipped (deferred to LLM-based validator): passive voice, sentence
    length, vague quantifiers, paragraph length, list-where-needed.

The hard-rule subset catches the failure mode the operator caught on
2026-04-29 (em-dash + "Came across X" + "Two things stuck with me" + AI-
speak in the body of an outreach draft). Extending to the full spec is a
follow-up slice when the LLM-validator pattern stabilises.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
# Banned tokens (hard fail — single-occurrence is enough)                      #
# --------------------------------------------------------------------------- #


# Em-dash variants. U+2014 (—), U+2013 (–), and the ASCII double-hyphen used
# as a dash. Banned outright.
_EMDASH_PATTERN = re.compile(r"[—–]|--")

# AI-cliché formulaic openers and middle-phrases. Locked to what the
# operator explicitly flagged on 2026-04-29 (Slice 21): "ngl", "Sharp
# positioning", "Two things stuck with me", "Came across", em-dashes.
# Plus the obvious cousins of those phrases ("Spent the morning with",
# "Sharp work/move", "Saw that you", "Loved your") since they come from
# the same Claude output mode. Conservative on phrases like "that's a big
# one" / "big shift" / "that lands" / "tbh" / "properly big" which the
# operator hasn't flagged explicitly — promote them to bans only when
# operator confirms they read as AI-speak too. Each entry is (pattern,
# label) for clean violation messages.
_AI_CLICHE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\btwo things stuck (?:with|in) me\b", re.I), "two things stuck with me"),
    (re.compile(r"\btwo things jumped out\b", re.I), "two things jumped out"),
    (re.compile(r"\bsharp positioning\b", re.I), "sharp positioning"),
    (re.compile(r"\bsharp move\b", re.I), "sharp move"),
    (re.compile(r"\bsaw that you\b", re.I), "saw that you"),
    (re.compile(r"\bloved your\b", re.I), "loved your"),
    (re.compile(r"\b(?:really )?sharp work\b", re.I), "sharp work"),
    (re.compile(r"\bcame across\b", re.I), "came across"),
    (re.compile(r"\bspent the morning with\b", re.I), "spent the morning with"),
    (re.compile(r"\bngl\b", re.I), "ngl"),
]

# Buzzwords from rules/global-writing-guardrails.md.
_BUZZWORD_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bleverage\b", re.I), "leverage"),
    (re.compile(r"\bsynergy\b", re.I), "synergy"),
    (re.compile(r"\bstreamline\b", re.I), "streamline"),
    (re.compile(r"\bbest[- ]in[- ]class\b", re.I), "best-in-class"),
    (re.compile(r"\bgame[- ]changer\b", re.I), "game-changer"),
    (re.compile(r"\bcutting[- ]edge\b", re.I), "cutting-edge"),
    (re.compile(r"\brobust\b", re.I), "robust"),
    (re.compile(r"\bseamless\b", re.I), "seamless"),
    (re.compile(r"\bunlock\b", re.I), "unlock"),
    (re.compile(r"\bempower\b", re.I), "empower"),
    (re.compile(r"\bactionable insights?\b", re.I), "actionable insights"),
    (re.compile(r"\btransform\b", re.I), "transform"),
]

# Filler phrases.
_FILLER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bjust checking in\b", re.I), "just checking in"),
    (re.compile(r"\bhope this finds you well\b", re.I), "hope this finds you well"),
    (re.compile(r"\bat the end of the day\b", re.I), "at the end of the day"),
    (re.compile(r"\bneedless to say\b", re.I), "needless to say"),
    (re.compile(r"\bin order to\b", re.I), "in order to"),
    (re.compile(r"\bcircle back\b", re.I), "circle back"),
    (re.compile(r"\btouch base\b", re.I), "touch base"),
    (re.compile(r"\bdeep dive\b", re.I), "deep dive"),
    (re.compile(r"\bmoving the needle\b", re.I), "moving the needle"),
    (re.compile(r"\blow[- ]hanging fruit\b", re.I), "low-hanging fruit"),
    (re.compile(r"\bthink outside the box\b", re.I), "think outside the box"),
]


# --------------------------------------------------------------------------- #
# Result dataclass                                                              #
# --------------------------------------------------------------------------- #


@dataclass
class Violation:
    """One rule hit. ``rule`` matches the section in
    ``rules/global-writing-guardrails.md``; ``offending_text`` is a short
    snippet for the operator to grep against."""

    rule: str
    offending_text: str


@dataclass
class ValidationResult:
    """Pass/fail with a list of violations. Empty list when ``passed=True``."""

    passed: bool
    violations: list[Violation] = field(default_factory=list)

    @property
    def violation_summary(self) -> str:
        """One-line summary for decision_log."""
        if self.passed:
            return "passed"
        labels = sorted({v.rule for v in self.violations})
        return f"failed: {len(self.violations)} violations across {labels}"


# --------------------------------------------------------------------------- #
# Public API                                                                    #
# --------------------------------------------------------------------------- #


def validate_writing(
    text: str | None,
    *,
    context: str = "generic",
) -> ValidationResult:
    """Check ``text`` against the hard-rule subset.

    ``context`` is reserved for future expansion (cold_email triggers
    word-count + single-idea checks). MVP: same checks for all contexts.
    Empty / None ``text`` passes — there's nothing to violate.
    """
    if not text:
        return ValidationResult(passed=True)

    violations: list[Violation] = []

    # --- em-dash (hardest rule) ---
    for m in _EMDASH_PATTERN.finditer(text):
        snippet = _snippet_around(text, m.start(), m.end())
        violations.append(
            Violation(rule="em_dash", offending_text=snippet)
        )

    # --- AI-clichés ---
    for pattern, label in _AI_CLICHE_PATTERNS:
        for m in pattern.finditer(text):
            violations.append(
                Violation(
                    rule=f"ai_cliche:{label}",
                    offending_text=m.group(0),
                )
            )

    # --- buzzwords ---
    for pattern, label in _BUZZWORD_PATTERNS:
        for m in pattern.finditer(text):
            violations.append(
                Violation(
                    rule=f"buzzword:{label}",
                    offending_text=m.group(0),
                )
            )

    # --- filler phrases ---
    for pattern, label in _FILLER_PATTERNS:
        for m in pattern.finditer(text):
            violations.append(
                Violation(
                    rule=f"filler:{label}",
                    offending_text=m.group(0),
                )
            )

    return ValidationResult(passed=not violations, violations=violations)


def _snippet_around(text: str, start: int, end: int, *, window: int = 30) -> str:
    """Return a context window around a match for human-readable violations."""
    s = max(0, start - window)
    e = min(len(text), end + window)
    snippet = text[s:e].replace("\n", " ")
    return snippet.strip()
