"""Client config validator.

Plan 2 Phase 6 Task 2.6.2. Three classes of footgun caught before a
client_config row reaches production:

  1. Title entries < 4 chars — short titles match too aggressively
     in pull-stage rule-based fit checks ('CEO' matches 'video CEO',
     'CEO assistant', etc).
  2. Geography entries in the known-ambiguous set ({'US', 'UK', 'AU'}).
     2-letter ISO codes match too broadly in free-text searches; force
     full names ('United States', 'United Kingdom', 'Australia').
  3. tier_thresholds monotonicity violations: must satisfy
     A > B > C > D > archive_floor strictly.

Used by:
  - ``scripts/provision_new_client.py`` (Task 2.6.1) before the
    initial client_config insert.
  - ``api/routers/optimizer.py`` (future) on every client_config
    update endpoint — lands when that endpoint is added.
  - Manual operator workflows via ``assert_valid_client_config``.
"""
from __future__ import annotations


MIN_TITLE_CHARS: int = 4

# 2-letter ISO codes that match too broadly. Operators must use full names.
AMBIGUOUS_GEOGRAPHIES: frozenset[str] = frozenset({"US", "UK", "AU"})


# Tier thresholds we check (in monotonicity order — left must be strictly
# greater than right).
_TIER_PAIRS: tuple[tuple[str, str], ...] = (
    ("A", "B"),
    ("B", "C"),
    ("C", "D"),
    ("D", "archive_floor"),
)


class ConfigValidationError(ValueError):
    """Raised by ``assert_valid_client_config`` when validation fails.
    Subclass of ValueError so callers can catch either."""


def validate_client_config(config: dict) -> list[str]:
    """Return a list of human-readable validation errors. Empty list = valid.

    Pure function — does NOT raise. Caller decides whether to escalate.
    Use ``assert_valid_client_config`` for the raise-on-error variant.
    """
    errors: list[str] = []

    # ----- Footgun 1: title length ------------------------------------ #
    icp = config.get("icp") or {}
    titles = icp.get("titles") or []
    for title in titles:
        if not isinstance(title, str):
            errors.append(
                f"icp.titles entry {title!r} must be a string"
            )
            continue
        if len(title.strip()) < MIN_TITLE_CHARS:
            errors.append(
                f"icp.titles entry {title!r} must be at least "
                f"{MIN_TITLE_CHARS} chars (avoids 'CEO' substring footgun "
                "where short titles match too aggressively)"
            )

    # ----- Footgun 2: ambiguous geography ----------------------------- #
    geographies = icp.get("geographies") or []
    for geo in geographies:
        if not isinstance(geo, str):
            errors.append(f"icp.geographies entry {geo!r} must be a string")
            continue
        if geo in AMBIGUOUS_GEOGRAPHIES:
            errors.append(
                f"icp.geographies entry {geo!r} is ambiguous — use the "
                "full country name ('United States' / 'United Kingdom' / "
                "'Australia') instead of the 2-letter code"
            )

    # ----- Footgun 3: tier monotonicity ------------------------------ #
    thresholds = config.get("tier_thresholds") or {}
    for higher, lower in _TIER_PAIRS:
        h = thresholds.get(higher)
        lo = thresholds.get(lower)
        if h is None or lo is None:
            continue  # missing values: caller decides defaults at use-site
        if h <= lo:
            errors.append(
                f"tier_thresholds.{higher} ({h}) must be > "
                f"tier_thresholds.{lower} ({lo}) — strict monotonicity required"
            )

    return errors


def assert_valid_client_config(config: dict) -> None:
    """Raise ``ConfigValidationError`` with all errors in the message
    when validation fails. No-op on a clean config."""
    errors = validate_client_config(config)
    if errors:
        raise ConfigValidationError(
            "client_config validation failed:\n  - "
            + "\n  - ".join(errors)
        )
