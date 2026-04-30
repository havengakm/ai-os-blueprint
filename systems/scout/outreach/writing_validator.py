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
    # Slice 37 (2026-04-30): fake-personalization shapes the operator
    # explicitly called out as AI-tells. "Saw you're a [job title]" and
    # "Noticed you're in [city]" treat the prospect as a generic role-
    # holder rather than a specific person. The cold-email skill's
    # frontmatter calls these out: "saw you're a [role]" / "notice
    # you're [city]" "almost sounds more fake than it does
    # personalized" (Saraev video). The framework also bans the
    # LinkedIn-headline reference: "I see you're the founder of a
    # branding agency."
    (re.compile(r"\b(?:saw|noticed) you'?re\s+(?:a|an|the)\s+\w", re.I), "saw you're a [job title]"),
    (re.compile(r"\b(?:saw|noticed) you'?re in\s+[A-Z]\w*", re.I), "saw you're in [city]"),
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

# Compliment shapes — Slice 35 narrowed in Slice 36 (2026-04-30) after
# operator-pointer to icebreaker-framework.md surfaced over-corrections.
# Slice 35's broad "is a [praise] [noun]" + "stuck with me" + "stands out"
# bans were catching framework-approved phrasings. Rolled back to:
# (a) operator's exact-flagged shapes from the Chatterkick failure
# (b) AI-default shapes that the framework's "Banned words" list also
#     rejects (impressed, remarkable, etc — already covered elsewhere)
# (c) the high-AI-tell phrases that almost-always read as flattery
#     across human + AI writing alike.
# See skills/cold-email/references/icebreaker-framework.md as canonical.
_COMPLIMENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Operator's exact-flagged shapes from the Slice 35 Chatterkick
    # failure — these stay, they're verbatim what the operator caught.
    (re.compile(r"\bis a clean way to\b", re.I), "is a clean way to"),
    (re.compile(r"\bstack the (?:real|actual) outcomes\b", re.I), "stack the actual outcomes"),
    (re.compile(r"\bhighlight (?:the )?key points people care about\b", re.I), "highlight key points people care about"),
    (re.compile(r"\b(?:the (?:real|actual) )?outcomes (?:that )?people care about\b", re.I), "outcomes people care about"),
    # High-AI-tell phrases. Framework's banned-words list also rejects
    # these or close cousins.
    (re.compile(r"\bdoes a lot of work\b", re.I), "does a lot of work"),
    (re.compile(r"\bactually sells itself\b", re.I), "actually sells itself"),
    (re.compile(r"\bactually made me rethink\b", re.I), "actually made me rethink"),
    (re.compile(r"\bhits different\b", re.I), "hits different"),
    (re.compile(r"\bthat lands\b", re.I), "that lands"),
    (re.compile(r"\bthat's the move\b", re.I), "that's the move"),
    (re.compile(r"\bnailed\s+(?:it|that|this)\b", re.I), "nailed it"),
    (re.compile(r"\bspot on\b", re.I), "spot on"),
    (re.compile(r"\bon point\b", re.I), "on point"),
    (re.compile(r"\bgenuinely (?:impressive|brilliant)\b", re.I), "genuinely impressive/brilliant"),
    (re.compile(r"\bproperly (?:big|impressive)\b", re.I), "properly big/impressive"),
    (re.compile(r"\b(?:totally|absolutely)\s+(?:brilliant|nailed)\b", re.I), "totally/absolutely [praise]"),
    # Specific phrases the framework's "Banned words" + tone-scale lists
    # treat as flat AI-praise. Kept narrow — exact phrases only.
    (re.compile(r"\bis a nice call\b", re.I), "is a nice call"),
    (re.compile(r"\breal talent\b", re.I), "real talent"),
    # Slice 36 rollbacks (REMOVED — operator-approved per
    # icebreaker-framework.md "Words that sound human" list):
    #   stuck with me / stuck in my head / jumped out
    #   stands out (and "stood out" past tense)
    #   broad "is a [praise] [noun]" pattern (catches "is a smart move" etc.)
    #   broad "such/really a [praise] [noun]" pattern
    #   real talent
    #   big fan / big move / big pickup / big catch / big deal
]


# Diagnostic / pundit shapes — Slice 36 (2026-04-30). The framework
# explicitly names this failure mode: "Diagnosis disguised as research:
# 'I noticed your agency doesn't seem to have an outbound system...' —
# puts them on the defensive." Operator-named pattern after the Slice 35
# example I drafted ("the hard part is usually proving which post drove
# which call — most attribution stops at the platform boundary") drifted
# into critique. These regex catch the consultant-paraphrase / unsolicited-
# advice / Socratic-gotcha shapes the LLM reaches for when steered away
# from compliments.
_DIAGNOSTIC_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Operator-flagged: "the hard part is", "the trick is"
    (re.compile(r"\bthe hard part (?:is|with that|of that)\b", re.I), "the hard part is"),
    (re.compile(r"\bthe (?:trick|key|secret) (?:is|with that|of that)\b", re.I), "the trick is"),
    (re.compile(r"\bthe tricky part\b", re.I), "the tricky part"),
    # Diagnostic / consultant-paraphrase
    (re.compile(r"\busually means\b", re.I), "usually means"),
    (re.compile(r"\busually results in\b", re.I), "usually results in"),
    (re.compile(r"\busually looks like\b", re.I), "usually looks like"),
    (re.compile(r"\busually (?:gets|breaks|stops|fails)\b", re.I), "usually [verb]s"),
    # "Most teams/agencies/companies can't/don't/won't" — broad-strokes
    # generalization that comes across as lecturing.
    (re.compile(r"\bmost (?:teams|agencies|companies|founders|operators) (?:can't|don't|won't|miss|fail|stop|hit|stumble)\b", re.I), "most [teams] can't/don't"),
    # "Where most teams fail/struggle" — Socratic gotcha
    (re.compile(r"\bwhere most (?:teams|agencies|companies|founders) (?:fail|struggle|hit a wall|stop|stumble|miss)\b", re.I), "where most teams fail"),
    # "Stops at" — the exact phrase from my Slice 35 example
    (re.compile(r"\bstops at the (?:platform|client|attribution|funnel) boundary\b", re.I), "stops at the X boundary"),
    # "I noticed X, which means/suggests Y problem" — diagnosis disguised
    (re.compile(r"\bwhich (?:means|suggests|tells me|points to)\b", re.I), "which means/suggests"),
    # Operator's framework-flagged: "the agency doesn't seem to have"
    (re.compile(r"\b(?:your|the) (?:agency|company|team|business) (?:doesn't|does not) (?:seem to have|appear to have)\b", re.I), "your agency doesn't seem to have"),
    # "You might want to / could want to" — unsolicited advice
    (re.compile(r"\byou (?:might|could|may) want to (?:try|consider|look at|think about)\b", re.I), "you might want to try/consider"),
    # "Have you tried / have you considered" — Socratic
    (re.compile(r"\bhave you (?:tried|considered|thought about)\b", re.I), "have you tried/considered"),
    # "The (real|actual) (question|issue|problem) is" — Socratic gotcha
    (re.compile(r"\bthe (?:real|actual) (?:question|issue|problem|challenge) is\b", re.I), "the real question is"),
    # "Is usually [verbing]" — broad lecturing shape
    (re.compile(r"\bis usually (?:proving|getting|convincing|figuring|deciding|knowing)\b", re.I), "is usually [lecturing-verb]"),
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

    # --- compliment shapes (Slice 35, narrowed Slice 36) ---
    for pattern, label in _COMPLIMENT_PATTERNS:
        for m in pattern.finditer(text):
            violations.append(
                Violation(
                    rule=f"compliment:{label}",
                    offending_text=m.group(0),
                )
            )

    # --- diagnostic / pundit shapes (Slice 36) ---
    for pattern, label in _DIAGNOSTIC_PATTERNS:
        for m in pattern.finditer(text):
            violations.append(
                Violation(
                    rule=f"diagnostic:{label}",
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
