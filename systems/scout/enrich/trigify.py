"""Trigify behavioral-signal adapter.

Trigify operates in 'listen mode' — monitors are pre-configured in Trigify
(keyword watchers, profile watchers, competitor watchers, influencer watchers)
via `POST /v1/searches`. This adapter does NOT create monitors — it pulls
accumulated results at enrich time and filters to match this contact by
LinkedIn URL or company domain.

Cost model:
  - `GET /v1/searches/{id}/results` → FREE per call (what this adapter calls)
  - `POST /v1/searches` (create monitor) → 1 credit — done once at client
    onboarding, NOT per contact. That cost is upstream (Task 16 / onboarding SOP).
  - Person enrichment → 4-15 credits — NOT used here (Claude research handles that).

So this adapter returns cost_cents=0 for the entire enrich path.

Client integration prerequisites (NOT this adapter's responsibility):
  - Trigify workspace provisioned for the client.
  - Searches created via POST /v1/searches (with [client_id]- prefix in name).
  - Search IDs stored in client_config.trigify_search_ids (JSONB array).
  - Those IDs are passed in by the orchestrator via contact['trigify_search_ids'].

Pagination: MVP uses a single page (limit=100 most-recent results per monitor).
Full cursor pagination is a backlog item.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from config.settings import get_settings
from systems.scout.enrich.base import EnrichResult


logger = logging.getLogger(__name__)

TRIGIFY_RESULTS_URL = "https://api.trigify.io/v1/searches/{search_id}/results"
RESULTS_PAGE_LIMIT = 100
MAX_EVENTS = 20
DETAIL_CHAR_LIMIT = 160
MIN_COMPANY_NAME_LEN = 4  # guard against spurious substring matches on short names

# Slice C (2026-04-29): recency window for the two reserved LinkedIn intent
# signals consumed by score._score_intent. Operator's signal table specifies
# "last 30d" for both decision-maker post and company-page post relevance.
# Hardcoded here for now; per-client override via
# client_config.tier_thresholds.linkedin_recency_days is a backlog item only
# worth wiring once we see live data demanding a different window.
LINKEDIN_RECENCY_DAYS = 30


class TrigifyAdapter:
    """Trigify behavioral-signal adapter. name='trigify'."""

    name: str = "trigify"
    cost_cents_per_call: int = 0    # monitor-pull is free; monitor creation is upstream

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        """http_client for test injection; production passes None and adapter builds its own."""
        self._http_client = http_client

    async def enrich(
        self,
        contact: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> EnrichResult:
        """Pull behavioral signals from pre-configured Trigify monitors for this contact.

        Skip paths (no network, cost_cents=0):
          - dry_run=True                        → reason='dry_run_skipped'
          - TRIGIFY_API_KEY unset               → reason='no_api_key'
          - trigify_search_ids empty/missing    → reason='no_monitors_configured'
          - all match keys blank                → reason='no_match_keys'

        Infrastructure errors propagate — no retries.
        """
        contact_id = contact.get("contact_id", "<unknown>")

        # --- dry run ---
        if dry_run:
            logger.debug("trigify dry_run contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=True,
                data={},
                cost_cents=0,
                reason="dry_run_skipped",
            )

        # --- key guard ---
        settings = get_settings()
        api_key = settings.trigify_api_key
        if not api_key:
            logger.warning("trigify no_api_key contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=False,
                data={},
                cost_cents=0,
                reason="no_api_key",
            )

        # --- monitors guard ---
        search_ids: list[str] = contact.get("trigify_search_ids") or []
        if not search_ids:
            logger.debug("trigify no_monitors_configured contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=False,
                data={},
                cost_cents=0,
                reason="no_monitors_configured",
            )

        # --- match-key guard ---
        linkedin_url = (contact.get("linkedin_url") or "").strip()
        company_domain = (contact.get("company_domain") or "").strip().lower()
        company = (contact.get("company") or "").strip()
        if not linkedin_url and not company_domain and not company:
            logger.debug("trigify no_match_keys contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=False,
                data={},
                cost_cents=0,
                reason="no_match_keys",
            )

        # Normalise linkedin_url once for comparison
        norm_linkedin = linkedin_url.rstrip("/").lower() if linkedin_url else ""

        # --- fetch and match ---
        client_provided = self._http_client is not None
        client = self._http_client or httpx.AsyncClient(timeout=30.0)

        matched_events: dict[str, dict] = {}   # keyed by result.id for dedup
        total_results_scanned = 0

        try:
            for search_id in search_ids:
                url = TRIGIFY_RESULTS_URL.format(search_id=search_id)
                response = await client.get(
                    url,
                    headers={"x-api-key": api_key},
                    params={"limit": RESULTS_PAGE_LIMIT},
                )
                response.raise_for_status()   # propagate 4xx/5xx — no retry
                body: dict[str, Any] = response.json()

                results: list[dict] = body.get("results") or []
                total_results_scanned += len(results)

                for item in results:
                    match_key = _match_contact(
                        item,
                        norm_linkedin=norm_linkedin,
                        company_domain=company_domain,
                        company=company,
                    )
                    if match_key is None:
                        continue

                    result_id = item.get("id") or ""
                    if result_id in matched_events:
                        continue    # deduplicate across monitors

                    event = _build_event(item, match_key)
                    matched_events[result_id] = event

        finally:
            if not client_provided:
                await client.aclose()

        # --- aggregate + cap ---
        events = sorted(
            matched_events.values(),
            key=_engagement_sum,
            reverse=True,
        )[:MAX_EVENTS]

        reason = "behavioral_signals_found" if events else "no_signals_matched"

        # --- Slice C: derive reserved LinkedIn intent flags ---
        # score._score_intent reads two booleans for 4+4 = 8 reserved
        # intent points. Trigify monitor config IS the topic filter
        # (operators set up keyword watchers on relevant topics), so a
        # matched recent LinkedIn event is by definition topic-relevant.
        # No runtime topic-check needed.
        linkedin_dm_recent = _has_recent_linkedin_event(
            events,
            match_keys={"profile"},
            max_days=LINKEDIN_RECENCY_DAYS,
        )
        linkedin_company_recent = _has_recent_linkedin_event(
            events,
            match_keys={"domain", "name"},
            max_days=LINKEDIN_RECENCY_DAYS,
        )

        logger.info(
            "trigify contact_id=%s monitors=%d scanned=%d matched=%d reason=%s "
            "linkedin_dm_recent=%s linkedin_company_recent=%s",
            contact_id,
            len(search_ids),
            total_results_scanned,
            len(matched_events),
            reason,
            linkedin_dm_recent,
            linkedin_company_recent,
        )

        return EnrichResult(
            adapter_name=self.name,
            ok=True,
            data={
                "trigger_events": events,
                "monitors_queried": list(search_ids),
                "total_results_scanned": total_results_scanned,
                "matched_count": len(matched_events),
                "linkedin_dm_recent_post_match": linkedin_dm_recent,
                "linkedin_company_recent_post": linkedin_company_recent,
            },
            cost_cents=0,
            reason=reason,
            raw_response={},  # Multi-monitor payloads would bloat memory; data.monitors_queried carries audit intent
        )


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _match_contact(
    item: dict[str, Any],
    *,
    norm_linkedin: str,
    company_domain: str,
    company: str,
) -> str | None:
    """Return match_key ('profile'|'domain'|'name') or None if no match."""
    # Profile match (strongest)
    if norm_linkedin:
        raw_profile_url = (item.get("author") or {}).get("profile_url") or ""
        if raw_profile_url.rstrip("/").lower() == norm_linkedin:
            return "profile"

    content = item.get("content") or {}
    text = (content.get("text") or "").lower()
    content_url = (content.get("url") or "").lower()

    # Domain match
    if company_domain:
        if company_domain in text or company_domain in content_url:
            return "domain"

    # Company name match (length-gated). `company` is already stripped by the caller.
    if company and len(company) >= MIN_COMPANY_NAME_LEN:
        if company.lower() in text:
            return "name"

    return None


def _build_event(item: dict[str, Any], match_key: str) -> dict[str, Any]:
    """Build a trigger_event dict from a Trigify result item."""
    content = item.get("content") or {}
    text = (content.get("text") or "")
    detail = text[:DETAIL_CHAR_LIMIT] if text else None

    source_platform = item.get("source") or "unknown"
    published_at = item.get("published_at")
    recency_days = _compute_recency(published_at)

    return {
        "type": "behavioral_signal",
        "detail": detail,
        "source": f"trigify_{source_platform}",
        "url": content.get("url"),
        "platform": source_platform,
        "match_key": match_key,
        "engagement": item.get("engagement") or {},
        "published_at": published_at,
        "recency_days": recency_days,
    }


def _engagement_sum(event: dict[str, Any]) -> int:
    """Sum likes + comments + shares for sorting; None values treated as 0."""
    eng = event.get("engagement") or {}
    return (eng.get("likes") or 0) + (eng.get("comments") or 0) + (eng.get("shares") or 0)


def _has_recent_linkedin_event(
    events: list[dict[str, Any]],
    *,
    match_keys: set[str],
    max_days: int,
) -> bool:
    """True if any event is on linkedin, matched on ``match_keys``, and recent.

    ``recency_days=None`` (unparseable timestamp) is treated as "old" — we don't
    fire the signal off undated content. Mirrors the conservative stance in
    ``systems.scout.pipeline.score._has_recent_structural_signal``.

    Slice C (2026-04-29): used to derive the two reserved LinkedIn intent
    booleans consumed by ``score._score_intent``.
    """
    for ev in events:
        if ev.get("platform") != "linkedin":
            continue
        if ev.get("match_key") not in match_keys:
            continue
        rd = ev.get("recency_days")
        if isinstance(rd, (int, float)) and rd <= max_days:
            return True
    return False


def _compute_recency(published_at: str | None) -> int | None:
    """Return days since published_at (UTC), or None if unparseable/missing.

    Normalises naive datetimes to UTC before subtraction — Trigify has been
    observed to return ISO-8601 timestamps without a `Z` suffix or offset
    in some edge cases, which would otherwise raise TypeError when subtracting
    from an offset-aware `now`.
    """
    if not published_at:
        return None
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        # Assume naive datetimes are UTC — safer than breaking the batch.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        return max(0, (now - dt).days)
    except (ValueError, AttributeError, TypeError):
        return None
