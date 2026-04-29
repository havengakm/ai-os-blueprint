"""ICP scoring — pure functions, no I/O, no side effects.

Three functions:
  score_v1(contact, client_config) -> int   # post-pull, pre-enrich. Max 70 (default weights).
  score_v2(contact, client_config) -> int   # post-enrich. Adds intent. Max 100 (default weights).
  assign_tier(score, client_config) -> str  # 'A' | 'B' | 'C' | 'D' | 'archive'

All weights and tier thresholds are read from client_config. If a key is missing
the module-level defaults (matching the DB defaults in 003_client_config_extensions.sql)
are used. This means tests can pass client_config={} and get sensible behaviour.

Signal point values (defaults):
  Fit (cap 40):
    industry in icp.industries                     → 15 pts
    title matches any icp.titles (case-insensitive) → 15 pts
    employees in [icp.employee_min, employee_max]   →  5 pts
    geography matches any icp.geographies (substr)  →  5 pts
  Reach (cap 20):
    verified email                                  → 10 pts
    unverified email                                →  5 pts
    linkedin_url present                            →  5 pts
    phone present                                   →  5 pts
  Recency (cap 10):
    raw_data.funding_event_last_180d is True        →  5 pts
    raw_data.recent_hiring is True                  →  5 pts
  Intent (cap 30) — score_v2 only:
    named clients in citable_details                  → 6 pts  (Slice 27, 2026-04-29)
    case study with measurable result (%/$/x)         → 5 pts  (Slice 27)
    pain_match is a non-empty string                  → 4 pts
    structural_signal in last 90d                     → 4 pts  (Slice 27)
    activity_positive is True                         → 3 pts
    LinkedIn DM post on relevant topic last 30d       → 4 pts  (Slice C, reserved)
    LinkedIn company page post last 30d               → 4 pts  (Slice C, reserved)

  Pre-Slice-C max raw = 22; reserved 8 for LinkedIn lifts to 30.

Category raw scores are scaled proportionally when the configured cap differs from
the default (e.g. raising fit cap from 40 to 60 scales a perfect-fit contact
from 40 to 60). This lets clients reweight categories in config without touching code.

If client_config has no 'icp' key, all fit signals return 0.
phone_gate and research_gate keys in tier_thresholds are ignored here — they are
enforced by the enrich orchestrator.
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Module-level defaults — match DB column defaults in 003_client_config_extensions.sql
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, int] = {
    "fit": 40,
    "intent": 30,
    "reach": 20,
    "recency": 10,
}

DEFAULT_TIER_THRESHOLDS: dict[str, int] = {
    "A": 80,
    "B": 65,
    "C": 50,
    "D": 35,
    "phone_gate": 50,
    "research_gate": 50,
    "archive_floor": 35,
}

# Raw point values for each sub-signal (at the default caps)
_RAW_FIT_INDUSTRY = 15
_RAW_FIT_TITLE = 15
_RAW_FIT_EMPLOYEES = 5
_RAW_FIT_GEOGRAPHY = 5
_DEFAULT_FIT_RAW_MAX = _RAW_FIT_INDUSTRY + _RAW_FIT_TITLE + _RAW_FIT_EMPLOYEES + _RAW_FIT_GEOGRAPHY  # 40

_RAW_REACH_VERIFIED_EMAIL = 10
_RAW_REACH_UNVERIFIED_EMAIL = 5
_RAW_REACH_LINKEDIN = 5
_RAW_REACH_PHONE = 5
# Unverified email is excluded from the sum because it is mutually exclusive
# with verified email in _score_reach; adding both would inflate the scaling max.
_DEFAULT_REACH_RAW_MAX = _RAW_REACH_VERIFIED_EMAIL + _RAW_REACH_LINKEDIN + _RAW_REACH_PHONE  # 20

_RAW_RECENCY_FUNDING = 5
_RAW_RECENCY_HIRING = 5
_DEFAULT_RECENCY_RAW_MAX = _RAW_RECENCY_FUNDING + _RAW_RECENCY_HIRING  # 10

# Intent signals — Slice 27 (2026-04-29) expansion. Two original
# binary signals (pain_match + activity_positive) plus three new
# research-derived signals from claude_deep_research output. Two
# additional signals reserved for Slice C (LinkedIn) so the cap of
# 30 is reachable once that ships. Pre-Slice-C max raw = 22.
_RAW_INTENT_NAMED_CLIENTS = 6        # citable_details with type in CLIENT_TYPES
_RAW_INTENT_CASE_STUDY_RESULT = 5    # case_study with %/$/x marker in detail
_RAW_INTENT_PAIN = 4                 # pain_match non-empty (was 15)
_RAW_INTENT_STRUCTURAL_RECENT = 4    # structural_signal recency_days <= 90
_RAW_INTENT_ACTIVITY = 3             # activity_positive True (was 15)
_RAW_INTENT_LINKEDIN_DM_POST = 4     # Slice C reserved
_RAW_INTENT_LINKEDIN_COMPANY = 4     # Slice C reserved
_DEFAULT_INTENT_RAW_MAX = (
    _RAW_INTENT_NAMED_CLIENTS
    + _RAW_INTENT_CASE_STUDY_RESULT
    + _RAW_INTENT_PAIN
    + _RAW_INTENT_STRUCTURAL_RECENT
    + _RAW_INTENT_ACTIVITY
    + _RAW_INTENT_LINKEDIN_DM_POST
    + _RAW_INTENT_LINKEDIN_COMPANY
)  # 30 — keeps default cap reachable once Slice C lands

# citable_details types that count as named-client / project evidence.
# Output of claude_deep_research extracts these from /clients, /work,
# /portfolio pages. Operator pushback 2026-04-29: a citable list of
# only "founded YYYY" + "tagline" doesn't qualify; needs a real
# named-client or named-project reference. The validator already
# strips tenure-only icebreakers at write time; this set keeps the
# scoring layer in sync.
_CLIENT_CITABLE_TYPES = frozenset({
    "named_client",
    "client_portfolio",
    "case_study",
    "project",
    "named_project",
})

# Marker pattern for measurable results inside a case_study detail
# string. Matches "20%", "$1.2M", "3x", "3X", "12 million" — any
# concrete metric the icebreaker can quote back. Plain noun-strings
# without a number are excluded.
import re as _re
_MEASURABLE_RESULT_RE = _re.compile(
    r"\d+\s*(?:%|x\b|×)|\$\s*\d|\d[\d,]*\s*(?:million|billion|m\b|b\b|k\b)",
    _re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _weights(client_config: dict[str, Any]) -> dict[str, int]:
    return {**DEFAULT_WEIGHTS, **client_config.get("weights", {})}


def _thresholds(client_config: dict[str, Any]) -> dict[str, int]:
    return {**DEFAULT_TIER_THRESHOLDS, **client_config.get("tier_thresholds", {})}


def _scale(raw: int, raw_max: int, cap: int) -> int:
    """Scale raw sub-signal total to the configured cap.

    Example: raw=40, raw_max=40, cap=60 → 60 (perfect contact gets full cap).
    Example: raw=30, raw_max=40, cap=40 → 30 (partial fit stays partial).
    Returns 0 if raw_max is 0 to avoid division by zero.
    """
    if raw_max == 0 or raw == 0:
        return 0
    return min(round(raw * cap / raw_max), cap)


def _score_fit(contact: dict[str, Any], icp: dict[str, Any], cap: int) -> int:
    """Score fit signals, scaled over fields that have data.

    Sparse-data contacts (e.g. ingest payloads missing industry/employees/
    geography but with a populated title) were landing below archive_floor
    purely because of missing-field penalties. The archive path then threw
    away perfectly viable contacts pre-enrich.

    Fix: scale raw → cap against the sum of raw weights for fields that
    were actually provided, not the full 40-point default. A title-only
    contact with a matching title scores 15/15*cap = cap, not 15/40*cap.
    Fully-populated contacts still behave as before (raw_max == 40).

    A field is "provided" when it is non-None on the contact. The ICP
    match result (present-and-matched vs present-and-unmatched) still maps
    to points-or-zero — we only gate INCLUSION in the denominator on
    "was there data to evaluate at all".
    """
    raw = 0
    raw_max = 0

    # Industry + title are FUZZY string matches against ICP-author-curated
    # term lists. A non-match often means substring-encoding drift (ICP says
    # "creative director", vendor returns "Director") rather than a real
    # negative signal. Treat "provided but no substring match" as NEUTRAL
    # (skip from raw_max) so v2's added person-data can never DROP the score
    # below v1's. Only matches contribute. Compare with employees/geography
    # below, where "out of range" IS a hard negative signal kept in raw_max.
    industries: list[str] = icp.get("industries") or []
    contact_industry_raw = contact.get("industry")
    if contact_industry_raw is not None:
        contact_industry = str(contact_industry_raw).lower()
        if contact_industry and any(i.lower() in contact_industry for i in industries if i):
            raw += _RAW_FIT_INDUSTRY
            raw_max += _RAW_FIT_INDUSTRY

    titles: list[str] = icp.get("titles") or []
    contact_title_raw = contact.get("title")
    if contact_title_raw is not None:
        contact_title = str(contact_title_raw).lower()
        if contact_title and any(t.lower() in contact_title for t in titles):
            raw += _RAW_FIT_TITLE
            raw_max += _RAW_FIT_TITLE

    emp_min: int | None = icp.get("employee_min")
    emp_max: int | None = icp.get("employee_max")
    employees = contact.get("employees")
    if employees is not None:
        raw_max += _RAW_FIT_EMPLOYEES
        if emp_min is not None and emp_max is not None and emp_min <= employees <= emp_max:
            raw += _RAW_FIT_EMPLOYEES

    geos: list[str] = icp.get("geographies") or []
    contact_geo_raw = contact.get("geography")
    if contact_geo_raw is not None:
        raw_max += _RAW_FIT_GEOGRAPHY
        contact_geo = str(contact_geo_raw).lower()
        if contact_geo and any(g.lower() in contact_geo for g in geos):
            raw += _RAW_FIT_GEOGRAPHY

    # No fit fields provided at all → 0 fit, as before. Otherwise scale
    # against the available-field total (raw_max), not the default 40.
    if raw_max == 0:
        return 0
    return _scale(raw, raw_max, cap)


def _score_reach(contact: dict[str, Any], cap: int) -> int:
    raw = 0
    email = contact.get("email") or ""
    if email:
        if contact.get("email_verified"):
            raw += _RAW_REACH_VERIFIED_EMAIL
        else:
            raw += _RAW_REACH_UNVERIFIED_EMAIL

    if contact.get("linkedin_url"):
        raw += _RAW_REACH_LINKEDIN

    if contact.get("phone"):
        raw += _RAW_REACH_PHONE

    return _scale(raw, _DEFAULT_REACH_RAW_MAX, cap)


def _score_recency(contact: dict[str, Any], cap: int) -> int:
    raw_data: dict[str, Any] = contact.get("raw_data") or {}
    raw = 0
    if raw_data.get("funding_event_last_180d") is True:
        raw += _RAW_RECENCY_FUNDING
    if raw_data.get("recent_hiring") is True:
        raw += _RAW_RECENCY_HIRING
    return _scale(raw, _DEFAULT_RECENCY_RAW_MAX, cap)


def _has_named_client(citable_details: list[Any]) -> bool:
    """True if any citable_details entry references a named client/project.

    A "named" reference is a dict with a recognised type AND non-empty detail.
    Marketing-copy entries (year_founded, company_about, value_proposition)
    don't count — they don't give the icebreaker a real surface to quote.
    """
    for cd in citable_details:
        if not isinstance(cd, dict):
            continue
        if cd.get("type") in _CLIENT_CITABLE_TYPES and cd.get("detail"):
            return True
    return False


def _has_measurable_case_study(citable_details: list[Any]) -> bool:
    """True if any case_study detail contains a measurable marker (%/$/x/M)."""
    for cd in citable_details:
        if not isinstance(cd, dict):
            continue
        if cd.get("type") not in {"case_study", "named_project", "project"}:
            continue
        detail = str(cd.get("detail") or "")
        if _MEASURABLE_RESULT_RE.search(detail):
            return True
    return False


def _has_recent_structural_signal(structural_signals: list[Any], max_days: int = 90) -> bool:
    """True if any structural_signal has recency_days <= max_days.

    Missing recency_days defaults to "old" (excluded) — only confirmed-
    recent signals count, otherwise stale data inflates the score.
    """
    for sig in structural_signals:
        if not isinstance(sig, dict):
            continue
        rd = sig.get("recency_days")
        if isinstance(rd, (int, float)) and rd <= max_days:
            return True
    return False


def _score_intent(contact: dict[str, Any], cap: int) -> int:
    research: dict[str, Any] = contact.get("research_data") or {}
    raw = 0

    citable_details = research.get("citable_details") or []
    if _has_named_client(citable_details):
        raw += _RAW_INTENT_NAMED_CLIENTS
    if _has_measurable_case_study(citable_details):
        raw += _RAW_INTENT_CASE_STUDY_RESULT

    if research.get("pain_match"):  # non-empty string
        raw += _RAW_INTENT_PAIN

    structural_signals = research.get("structural_signals") or []
    if _has_recent_structural_signal(structural_signals):
        raw += _RAW_INTENT_STRUCTURAL_RECENT

    if research.get("activity_positive") is True:
        raw += _RAW_INTENT_ACTIVITY

    # Slice C (reserved) — these read from research_data once LinkedIn
    # adapter populates them. Until then they don't fire and the max
    # achievable raw is 22/30.
    if research.get("linkedin_dm_recent_post_match") is True:
        raw += _RAW_INTENT_LINKEDIN_DM_POST
    if research.get("linkedin_company_recent_post") is True:
        raw += _RAW_INTENT_LINKEDIN_COMPANY

    return _scale(raw, _DEFAULT_INTENT_RAW_MAX, cap)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_v1(contact: dict[str, Any], client_config: dict[str, Any]) -> int:
    """Score a contact using only pull-payload signals. Returns 0–70 with default weights.

    Categories: fit, reach, recency. Intent is NOT computed here.
    If client_config has no 'icp' key, all fit signals return 0.
    """
    w = _weights(client_config)
    icp: dict[str, Any] = client_config.get("icp") or {}

    fit = _score_fit(contact, icp, w["fit"])
    reach = _score_reach(contact, w["reach"])
    recency = _score_recency(contact, w["recency"])

    return fit + reach + recency


def score_v2(contact: dict[str, Any], client_config: dict[str, Any]) -> int:
    """Full score after enrichment. Returns 0–100 with default weights.

    Adds intent signals from contact.research_data on top of score_v1.
    If research_data is absent or empty, v2 == v1.
    """
    w = _weights(client_config)
    v1 = score_v1(contact, client_config)
    intent = _score_intent(contact, w["intent"])
    return v1 + intent


def assign_tier(score: int, client_config: dict[str, Any]) -> str:
    """Return 'A' | 'B' | 'C' | 'D' | 'archive' per client_config.tier_thresholds.

    Tier boundaries (inclusive, evaluated top-down):
      score >= A            → 'A'
      score >= B            → 'B'
      score >= C            → 'C'
      score >= archive_floor → 'D'
      else                  → 'archive'

    phone_gate and research_gate keys are ignored — those are enforced downstream
    by the enrich orchestrator.
    """
    t = _thresholds(client_config)
    if score >= t["A"]:
        return "A"
    if score >= t["B"]:
        return "B"
    if score >= t["C"]:
        return "C"
    if score >= t["archive_floor"]:
        return "D"
    return "archive"
