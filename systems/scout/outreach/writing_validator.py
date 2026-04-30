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

# Founding-year / company-tenure references. Operator-flagged 2026-04-29
# (Slice 23) after three Tier-4 icebreakers all opened with founding year
# ("founded in 2011", "been at this since 2011", "decade-plus run in this
# space"). Tenure is the laziest concrete fact the LLM can grab when
# citable_details is thin, so it became the default fallback. Reads as AI;
# no human opens an email by quoting the year a company was founded.
# See ``memory/feedback_no_founding_year_in_icebreakers.md``.
_TENURE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bfounded in \d{4}\b", re.I), "founded in YYYY"),
    (re.compile(r"\bfounded \d{4}\b", re.I), "founded YYYY"),
    (re.compile(r"\bsince \d{4}\b", re.I), "since YYYY"),
    (re.compile(r"\bbeen at (?:this|it)\b", re.I), "been at this / been at it"),
    (re.compile(r"\bbeen (?:in|doing) (?:this|the) (?:game|business|industry|space|room)\b", re.I), "been in this space / room / game"),
    (re.compile(r"\bbeen in the room (?:long enough|for)\b", re.I), "been in the room"),
    (re.compile(r"\bdecade[- ]plus\b", re.I), "decade-plus"),
    (re.compile(r"\bdecade[- ]long\b", re.I), "decade-long"),
    (re.compile(r"\b(?:over |for over )?a decade\b", re.I), "a decade / over a decade"),
    (re.compile(r"\bdecades? in (?:this|the)\b", re.I), "decades in this/the"),
]

# Compliment shapes — Slice 35 (2026-04-30). Operator-flagged after the
# Chatterkick run produced "is a clean way to stack the actual outcomes
# people care about" — passed every other validator class but read as
# disingenuous flattery. The icebreaker's payload sentence (when present)
# must demonstrate situation-connection (a constraint, friction, trade-
# off in the work) NOT praise. These regex catch the most common AI
# compliment fallbacks. Prompt-level rules cover the structural ask.
# See ``memory/sessions/2026-04-30.md`` (4th addendum).
_COMPLIMENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # "is a [praise] [noun]" / "such a [praise] [noun]" — the dominant shape
    (
        re.compile(
            r"\b(?:is|are|was|were|that's)\s+(?:a|an)\s+(?:clean|nice|smart|sharp|solid|good|great|brilliant|elegant|clever|interesting|impressive|powerful|strong|beautiful|striking|striking)\s+(?:way|call|move|take|framing|approach|one|signal|read|catch)\b",
            re.I,
        ),
        "compliment shape: 'is a [praise] [noun]'",
    ),
    (
        re.compile(
            r"\b(?:such|so|really|quite)\s+(?:a|an)?\s*(?:clean|nice|smart|sharp|solid|good|great|brilliant|elegant|clever|impressive|powerful|strong|beautiful)\s+(?:way|call|move|take|framing|approach|one|signal|read|catch|piece)\b",
            re.I,
        ),
        "compliment shape: 'such/really a [praise] [noun]'",
    ),
    # Specific phrases that pattern-match disingenuous flattery
    (re.compile(r"\bdoes a lot of work\b", re.I), "does a lot of work"),
    (re.compile(r"\bactually sells itself\b", re.I), "actually sells itself"),
    (re.compile(r"\bactually made me rethink\b", re.I), "actually made me rethink"),
    (re.compile(r"\bhits different\b", re.I), "hits different"),
    (re.compile(r"\bthat lands\b", re.I), "that lands"),
    (re.compile(r"\bthat's the move\b", re.I), "that's the move"),
    (re.compile(r"\breal talent\b", re.I), "real talent"),
    (re.compile(r"\bgenuinely (?:impressive|sharp|good|brilliant|powerful)\b", re.I), "genuinely [praise]"),
    (re.compile(r"\bproperly (?:good|sharp|brilliant|big|impressive)\b", re.I), "properly [praise]"),
    (re.compile(r"\b(?:totally|absolutely)\s+(?:agree|brilliant|sharp|on point|nailed)\b", re.I), "totally/absolutely [praise]"),
    (re.compile(r"\bnailed\s+(?:it|that|this)\b", re.I), "nailed it"),
    (re.compile(r"\bspot on\b", re.I), "spot on"),
    (re.compile(r"\bon point\b", re.I), "on point"),
    (re.compile(r"\b(?:big|huge) (?:fan|move|deal|pickup|catch)\b", re.I), "big/huge [praise-noun]"),
    (re.compile(r"\bstands out\b", re.I), "stands out"),
    (re.compile(r"\b(?:jumped out|stuck with me|stuck in my head)\b", re.I), "jumped out / stuck with me"),
    # "stack the [real|actual] outcomes" — operator's exact flagged shape
    (re.compile(r"\bstack the (?:real|actual) outcomes\b", re.I), "stack the actual outcomes"),
    # "highlight key points people care about" — operator's exact flagged shape
    (re.compile(r"\bhighlight (?:the )?key points people care about\b", re.I), "highlight key points people care about"),
    # "people care about" + "actually [adverb]" / praise-y modifiers
    (re.compile(r"\b(?:the (?:real|actual) )?outcomes (?:that )?people care about\b", re.I), "outcomes people care about"),
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

    # --- founding-year / company-tenure references ---
    for pattern, label in _TENURE_PATTERNS:
        for m in pattern.finditer(text):
            violations.append(
                Violation(
                    rule=f"tenure:{label}",
                    offending_text=m.group(0),
                )
            )

    # --- compliment shapes (Slice 35) ---
    for pattern, label in _COMPLIMENT_PATTERNS:
        for m in pattern.finditer(text):
            violations.append(
                Violation(
                    rule=f"compliment:{label}",
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
