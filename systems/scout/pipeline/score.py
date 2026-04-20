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
    research_data.pain_match is a non-empty string  → 15 pts
    research_data.activity_positive is True         → 15 pts

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

_DEFAULT_WEIGHTS: dict[str, int] = {
    "fit": 40,
    "intent": 30,
    "reach": 20,
    "recency": 10,
}

_DEFAULT_TIER_THRESHOLDS: dict[str, int] = {
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
_DEFAULT_REACH_RAW_MAX = _RAW_REACH_VERIFIED_EMAIL + _RAW_REACH_LINKEDIN + _RAW_REACH_PHONE  # 20

_RAW_RECENCY_FUNDING = 5
_RAW_RECENCY_HIRING = 5
_DEFAULT_RECENCY_RAW_MAX = _RAW_RECENCY_FUNDING + _RAW_RECENCY_HIRING  # 10

_RAW_INTENT_PAIN = 15
_RAW_INTENT_ACTIVITY = 15
_DEFAULT_INTENT_RAW_MAX = _RAW_INTENT_PAIN + _RAW_INTENT_ACTIVITY  # 30


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _weights(client_config: dict[str, Any]) -> dict[str, int]:
    return {**_DEFAULT_WEIGHTS, **client_config.get("weights", {})}


def _thresholds(client_config: dict[str, Any]) -> dict[str, int]:
    return {**_DEFAULT_TIER_THRESHOLDS, **client_config.get("tier_thresholds", {})}


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
    raw = 0
    industries: list[str] = icp.get("industries") or []
    if contact.get("industry") in industries:
        raw += _RAW_FIT_INDUSTRY

    titles: list[str] = icp.get("titles") or []
    contact_title: str = (contact.get("title") or "").lower()
    if contact_title and any(t.lower() in contact_title for t in titles):
        raw += _RAW_FIT_TITLE

    emp_min: int | None = icp.get("employee_min")
    emp_max: int | None = icp.get("employee_max")
    employees = contact.get("employees")
    if employees is not None and emp_min is not None and emp_max is not None:
        if emp_min <= employees <= emp_max:
            raw += _RAW_FIT_EMPLOYEES

    geos: list[str] = icp.get("geographies") or []
    contact_geo: str = (contact.get("geography") or "").lower()
    if contact_geo and any(g.lower() in contact_geo for g in geos):
        raw += _RAW_FIT_GEOGRAPHY

    return _scale(raw, _DEFAULT_FIT_RAW_MAX, cap)


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

    return min(raw, cap)


def _score_recency(contact: dict[str, Any], cap: int) -> int:
    raw_data: dict[str, Any] = contact.get("raw_data") or {}
    raw = 0
    if raw_data.get("funding_event_last_180d") is True:
        raw += _RAW_RECENCY_FUNDING
    if raw_data.get("recent_hiring") is True:
        raw += _RAW_RECENCY_HIRING
    return min(raw, cap)


def _score_intent(contact: dict[str, Any], cap: int) -> int:
    research: dict[str, Any] = contact.get("research_data") or {}
    raw = 0
    if research.get("pain_match"):  # non-empty string
        raw += _RAW_INTENT_PAIN
    if research.get("activity_positive") is True:
        raw += _RAW_INTENT_ACTIVITY
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
