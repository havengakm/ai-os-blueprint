"""Trigify discovery source — daily pull of engagers from configured monitors.

Companion to systems/scout/sources/trigify_monitors.py (provisioning) and
systems/scout/enrich/trigify.py (enrichment-time pull). Consumes the search
IDs written at onboarding and produces RawCompanyContact rows.

Flow: (1) read client_config.trigify_search_ids + trigify_discovery_config.
(2) GET /v1/searches once -> {search_id -> monitor_type} via name prefix.
(3) Per search (filtered by search_subset kwarg or config): GET
/v1/searches/{id}/results (MVP: page 1). (4) Per post: if engagement below
threshold, skip (post cooks for next run); else GET /v1/posts/{id}/engagers.
(5) Per engager: skip when employer not determinable (counted + logged); else
build RawCompanyContact, engager info into raw_data. (6) Dedup by source_id,
first-by-engaged_at-asc wins. (7) Cap at min(max_companies, max_leads_per_run).

Amendment 2: RawCompanyContact is company-level; engager person-level data
lives in raw_data for Task 9.5 identity lookup.

Defaults per Max Mitcham webinar 2026-04-22 (YouTube bKEmJIch0nI): 10-like
engagement threshold, 24h cook-time (emergent from daily cadence), 100-lead
cap, all 4 monitor subsets. Pagination MVP = page 1 only.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from config.settings import get_settings
from systems.scout.sources.base import RawCompanyContact

logger = logging.getLogger(__name__)

TRIGIFY_API_BASE = "https://api.trigify.io/v1"
TRIGIFY_SEARCHES_URL = f"{TRIGIFY_API_BASE}/searches"
TRIGIFY_SEARCH_RESULTS_URL = f"{TRIGIFY_API_BASE}/searches/{{search_id}}/results"
TRIGIFY_POST_ENGAGERS_URL = f"{TRIGIFY_API_BASE}/posts/{{post_id}}/engagers"
DEFAULT_RESULTS_PAGE_LIMIT = 100
DEFAULT_HTTP_TIMEOUT_SECONDS = 30.0

DEFAULT_MIN_ENGAGEMENT_TO_PULL = 10
DEFAULT_COOK_TIME_HOURS = 24
DEFAULT_MAX_LEADS_PER_RUN = 100
DEFAULT_SEARCH_SUBSETS_ENABLED: tuple[str, ...] = (
    "intent", "competitor", "thought_leader", "brand",
)

_SUBSET_TO_MONITOR_TYPE: dict[str, str] = {
    "intent": "intent_keyword",
    "competitor": "competitor_engagement",
    "thought_leader": "thought_leader_engagement",
    "brand": "brand_mention",
}
# Mirrors trigify_monitors.py::_TYPE_PREFIX — drives monitor_type inference.
_NAME_PREFIX_TO_MONITOR_TYPE: dict[str, str] = {
    "intent": "intent_keyword",
    "competitor": "competitor_engagement",
    "thought-leader": "thought_leader_engagement",
    "brand": "brand_mention",
}


@dataclass
class DiscoveryConfig:
    """Per-client thresholds from client_config.trigify_discovery_config JSONB."""

    min_engagement_to_pull: int = DEFAULT_MIN_ENGAGEMENT_TO_PULL
    cook_time_hours: int = DEFAULT_COOK_TIME_HOURS
    max_leads_per_run: int = DEFAULT_MAX_LEADS_PER_RUN
    search_subsets_enabled: tuple[str, ...] = DEFAULT_SEARCH_SUBSETS_ENABLED

    @classmethod
    def from_jsonb(cls, raw: dict[str, Any] | None) -> "DiscoveryConfig":
        if not raw:
            return cls()
        subsets = raw.get("search_subsets_enabled")
        subsets_t: tuple[str, ...]
        if isinstance(subsets, list):
            subsets_t = tuple(str(s) for s in subsets)
        else:
            subsets_t = DEFAULT_SEARCH_SUBSETS_ENABLED
        return cls(
            min_engagement_to_pull=int(
                raw.get("min_engagement_to_pull", DEFAULT_MIN_ENGAGEMENT_TO_PULL)
            ),
            cook_time_hours=int(raw.get("cook_time_hours", DEFAULT_COOK_TIME_HOURS)),
            max_leads_per_run=int(
                raw.get("max_leads_per_run", DEFAULT_MAX_LEADS_PER_RUN)
            ),
            search_subsets_enabled=subsets_t,
        )


@dataclass
class DiscoverySummary:
    """Observability counters from a single pull() call."""

    searches_queried: int = 0
    posts_scanned: int = 0
    posts_below_threshold: int = 0
    posts_qualified: int = 0
    engagers_extracted: int = 0
    engagers_skipped_no_employer: int = 0
    leads_returned: int = 0
    errors: int = 0
    by_monitor_type: dict[str, int] = field(default_factory=dict)


class DiscoveryStorage(Protocol):
    """Storage contract. Prod: systems/scout/supabase_backends/; tests: fake."""

    async def get_trigify_search_ids(self, client_id: str) -> list[str]: ...

    async def get_discovery_config(self, client_id: str) -> dict[str, Any]: ...

    async def log_decision(
        self, client_id: str, *,
        decision_type: str, decision: str, context: dict[str, Any],
        reasoning: str | None = None, confidence: float | None = None,
    ) -> None: ...


class TrigifyDiscoverySource:
    """CompanySourceAdapter implementation for Trigify-discovered engagers."""

    name: str = "trigify_discovery"

    def __init__(
        self,
        storage: DiscoveryStorage,
        *,
        http_client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
    ) -> None:
        self._storage = storage
        self._http_client = http_client
        self._api_key = api_key
        self.last_summary: DiscoverySummary | None = None

    async def pull(
        self,
        client_id: str,
        max_companies: int,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> list[RawCompanyContact]:
        """kwargs.search_subset: {"intent","competitor","thought_leader","brand"}."""
        summary = DiscoverySummary()
        self.last_summary = summary

        search_ids = await self._storage.get_trigify_search_ids(client_id)
        if not search_ids:
            logger.info(
                "trigify_discovery no_search_ids client_id=%s dry_run=%s",
                client_id, dry_run,
            )
            return []

        config = DiscoveryConfig.from_jsonb(
            await self._storage.get_discovery_config(client_id)
        )

        requested_subset = kwargs.get("search_subset")
        if requested_subset is not None and requested_subset not in _SUBSET_TO_MONITOR_TYPE:
            raise ValueError(
                f"search_subset must be one of {list(_SUBSET_TO_MONITOR_TYPE)}; "
                f"got {requested_subset!r}"
            )

        api_key = self._resolve_api_key()
        client_provided = self._http_client is not None
        client = self._http_client or httpx.AsyncClient(
            timeout=DEFAULT_HTTP_TIMEOUT_SECONDS,
        )

        collected: list[tuple[RawCompanyContact, str]] = []  # (contact, engaged_at)

        try:
            search_id_to_type = await _fetch_search_id_to_monitor_type(
                client, api_key, client_id,
            )

            if requested_subset is not None:
                enabled_types: set[str] = {_SUBSET_TO_MONITOR_TYPE[requested_subset]}
            else:
                enabled_types = {
                    _SUBSET_TO_MONITOR_TYPE[s]
                    for s in config.search_subsets_enabled
                    if s in _SUBSET_TO_MONITOR_TYPE
                }

            for search_id in search_ids:
                monitor_type = search_id_to_type.get(search_id) or "unknown"
                if monitor_type not in enabled_types:
                    continue
                await self._pull_one_search(
                    client, api_key, client_id, search_id, monitor_type,
                    config, summary, collected, dry_run,
                )
        finally:
            if not client_provided:
                await client.aclose()

        # Dedup by engager_linkedin_url, keeping first-by-engaged_at-asc (the
        # earliest engagement wins). Empty engaged_at sorts LAST via sentinel
        # so real timestamps win over blanks. source_id embeds post_id for
        # cross-run uniqueness; dedup key is the engager to avoid duplicating
        # the same person across multiple posts in one run.
        collected_sorted = sorted(
            enumerate(collected),
            key=lambda t: (t[1][1] or "￿", t[0]),
        )
        seen_engagers: set[str] = set()
        deduped: list[RawCompanyContact] = []
        for _, (contact, _ea) in collected_sorted:
            engager_url = contact.raw_data.get("engager_linkedin_url", "")
            if engager_url in seen_engagers:
                continue
            seen_engagers.add(engager_url)
            deduped.append(contact)

        effective_cap = min(max_companies, config.max_leads_per_run)
        if effective_cap >= 0:
            deduped = deduped[:effective_cap]
        summary.leads_returned = len(deduped)

        await _safe_log(
            self._storage, client_id,
            decision_type="trigify_discovery",
            decision="pull_completed",
            context={
                "searches_queried": summary.searches_queried,
                "posts_scanned": summary.posts_scanned,
                "posts_below_threshold": summary.posts_below_threshold,
                "posts_qualified": summary.posts_qualified,
                "engagers_extracted": summary.engagers_extracted,
                "engagers_skipped_no_employer": summary.engagers_skipped_no_employer,
                "leads_returned": summary.leads_returned,
                "errors": summary.errors,
                "by_monitor_type": summary.by_monitor_type,
                "dry_run": dry_run,
                "search_subset": requested_subset,
            },
        )
        logger.info(
            "trigify_discovery pull_completed client_id=%s "
            "searches=%d posts=%d qualified=%d engagers=%d leads=%d errors=%d dry_run=%s",
            client_id, summary.searches_queried, summary.posts_scanned,
            summary.posts_qualified, summary.engagers_extracted,
            summary.leads_returned, summary.errors, dry_run,
        )
        return deduped

    async def _pull_one_search(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        client_id: str,
        search_id: str,
        monitor_type: str,
        config: DiscoveryConfig,
        summary: DiscoverySummary,
        collected: list[tuple[RawCompanyContact, str]],
        dry_run: bool,
    ) -> None:
        """Pull one search's qualifying posts + engagers into ``collected``.
        Counters updated on ``summary``. HTTP errors incremented, not raised."""
        try:
            posts = await _fetch_search_results(client, api_key, search_id)
        except httpx.HTTPError as e:
            summary.errors += 1
            logger.warning(
                "trigify_discovery search_results_failed "
                "client_id=%s search_id=%s error=%r",
                client_id, search_id, e,
            )
            await _safe_log(
                self._storage, client_id,
                decision_type="trigify_discovery",
                decision="search_results_failed",
                context={
                    "search_id": search_id, "monitor_type": monitor_type,
                    "error": repr(e), "dry_run": dry_run,
                },
            )
            return

        summary.searches_queried += 1

        for post in posts:
            summary.posts_scanned += 1
            engagement_total = _engagement_total(post)
            post_id = str(post.get("id") or post.get("post_id") or "")
            if not post_id:
                continue
            if engagement_total < config.min_engagement_to_pull:
                summary.posts_below_threshold += 1
                continue
            summary.posts_qualified += 1

            try:
                engagers = await _fetch_post_engagers(client, api_key, post_id)
            except httpx.HTTPError as e:
                summary.errors += 1
                logger.warning(
                    "trigify_discovery engagers_failed "
                    "client_id=%s post_id=%s error=%r",
                    client_id, post_id, e,
                )
                continue

            post_url = _extract_post_url(post)
            engaged_at = _extract_engaged_at(post)
            post_topic = _derive_post_topic(post, monitor_type)

            for eng in engagers:
                await self._process_engager(
                    eng, client_id, search_id, post_id, post_url,
                    post_topic, engagement_total, engaged_at, monitor_type,
                    summary, collected, dry_run,
                )

    async def _process_engager(
        self,
        eng: dict[str, Any],
        client_id: str,
        search_id: str,
        post_id: str,
        post_url: str,
        post_topic: str,
        engagement_total: int,
        engaged_at: str,
        monitor_type: str,
        summary: DiscoverySummary,
        collected: list[tuple[RawCompanyContact, str]],
        dry_run: bool,
    ) -> None:
        summary.engagers_extracted += 1
        employer = _extract_employer(eng)
        engager_url = eng.get("linkedin_url") or eng.get("profile_url") or ""
        if not employer or not engager_url:
            summary.engagers_skipped_no_employer += 1
            await _safe_log(
                self._storage, client_id,
                decision_type="trigify_discovery",
                decision="engager_skipped:no_employer",
                context={
                    "post_id": post_id,
                    "engager_linkedin_url": engager_url,
                    "engager_name": eng.get("name") or eng.get("full_name") or "",
                    "monitor_type": monitor_type,
                    "dry_run": dry_run,
                },
            )
            return

        raw_data = {
            "engager_linkedin_url": engager_url,
            "engager_name": eng.get("name") or eng.get("full_name") or "",
            "engager_title": eng.get("title") or eng.get("headline") or "",
            "post_id": post_id,
            "post_url": post_url,
            "post_topic": post_topic,
            "post_engagement_total": engagement_total,
            "monitor_type": monitor_type,
            "monitor_search_id": search_id,
            "engaged_at": engaged_at,
        }
        contact = RawCompanyContact(
            company=employer,
            company_domain=(
                eng.get("employer_domain") or eng.get("company_domain") or None
            ),
            source=self.name,
            source_id=_build_source_id(post_id, engager_url),
            raw_data=raw_data,
        )
        collected.append((contact, engaged_at or ""))
        summary.by_monitor_type[monitor_type] = (
            summary.by_monitor_type.get(monitor_type, 0) + 1
        )

    def _resolve_api_key(self) -> str:
        if self._api_key:
            return self._api_key
        key = get_settings().trigify_api_key
        if not key:
            raise EnvironmentError(
                "TRIGIFY_API_KEY is not set. Add it to .env (see "
                "skills/operations/discover-trigify-leads.md preconditions)."
            )
        return key


# --------------------------------------------------------------------------- #
# HTTP helpers                                                                  #
# --------------------------------------------------------------------------- #

async def _fetch_search_id_to_monitor_type(
    client: httpx.AsyncClient, api_key: str, client_id: str,
) -> dict[str, str]:
    """GET /v1/searches -> filter by [{client_id}]- prefix -> infer type from name."""
    response = await client.get(
        TRIGIFY_SEARCHES_URL, headers={"x-api-key": api_key},
    )
    response.raise_for_status()
    body = response.json()
    raw_list = body.get("searches") if isinstance(body, dict) else body
    if not isinstance(raw_list, list):
        raw_list = []

    prefix = f"[{client_id}]-"
    out: dict[str, str] = {}
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or ""
        sid = item.get("id") or item.get("search_id") or ""
        if not name or not sid or not name.startswith(prefix):
            continue
        monitor_type = _infer_monitor_type_from_name_remainder(name[len(prefix):])
        if monitor_type:
            out[str(sid)] = monitor_type
    return out


def _infer_monitor_type_from_name_remainder(remainder: str) -> str | None:
    """``intent-social-signals`` -> ``intent_keyword``. Longest prefix first so
    ``thought-leader`` is checked before any single-token prefix."""
    for prefix in sorted(_NAME_PREFIX_TO_MONITOR_TYPE, key=len, reverse=True):
        if remainder.startswith(prefix + "-") or remainder == prefix:
            return _NAME_PREFIX_TO_MONITOR_TYPE[prefix]
    return None


async def _fetch_search_results(
    client: httpx.AsyncClient, api_key: str, search_id: str,
) -> list[dict[str, Any]]:
    """GET /v1/searches/{id}/results. MVP: page 1."""
    response = await client.get(
        TRIGIFY_SEARCH_RESULTS_URL.format(search_id=search_id),
        headers={"x-api-key": api_key},
        params={"limit": DEFAULT_RESULTS_PAGE_LIMIT},
    )
    response.raise_for_status()
    body = response.json()
    results = body.get("results") if isinstance(body, dict) else body
    if not isinstance(results, list):
        return []
    return [r for r in results if isinstance(r, dict)]


async def _fetch_post_engagers(
    client: httpx.AsyncClient, api_key: str, post_id: str,
) -> list[dict[str, Any]]:
    """GET /v1/posts/{post_id}/engagers?type=like,comment,share."""
    response = await client.get(
        TRIGIFY_POST_ENGAGERS_URL.format(post_id=post_id),
        headers={"x-api-key": api_key},
        params={"type": "like,comment,share"},
    )
    response.raise_for_status()
    body = response.json()
    engagers = body.get("engagers") if isinstance(body, dict) else body
    if not isinstance(engagers, list):
        return []
    return [e for e in engagers if isinstance(e, dict)]


# --------------------------------------------------------------------------- #
# Extraction helpers                                                             #
# --------------------------------------------------------------------------- #

def _engagement_total(post: dict[str, Any]) -> int:
    """likes + comments + shares. Accept nested ``engagement.{...}`` or flat."""
    eng = post.get("engagement")
    if isinstance(eng, dict):
        return (
            int(eng.get("likes") or 0)
            + int(eng.get("comments") or 0)
            + int(eng.get("shares") or 0)
        )
    return (
        int(post.get("likes") or 0)
        + int(post.get("comments") or 0)
        + int(post.get("shares") or 0)
    )


def _extract_post_url(post: dict[str, Any]) -> str:
    content = post.get("content")
    if isinstance(content, dict) and content.get("url"):
        return str(content["url"])
    return str(post.get("url") or post.get("post_url") or "")


def _extract_engaged_at(post: dict[str, Any]) -> str:
    for key in ("engaged_at", "published_at", "created_at"):
        val = post.get(key)
        if val:
            return str(val)
    return ""


def _derive_post_topic(post: dict[str, Any], monitor_type: str) -> str:
    """Rule-based topic derivation. No LLM call."""
    if monitor_type == "intent_keyword":
        monitor = post.get("monitor")
        if isinstance(monitor, dict):
            q = monitor.get("query") or monitor.get("phrase") or ""
            if q:
                return str(q)
        for key in ("matched_keyword", "match_keyword", "query"):
            val = post.get(key)
            if val:
                return str(val)
        return ""
    if monitor_type == "competitor_engagement":
        target = _extract_target_name(post)
        return f"engaged with {target}" if target else "engaged with competitor"
    if monitor_type == "thought_leader_engagement":
        target = _extract_target_name(post)
        return (
            f"engaged with {target}'s post" if target
            else "engaged with thought leader's post"
        )
    if monitor_type == "brand_mention":
        return "mentioned our brand"
    return ""


def _extract_target_name(post: dict[str, Any]) -> str:
    """Author of the post is the target for competitor/thought_leader monitors."""
    author = post.get("author")
    if isinstance(author, dict):
        return str(author.get("name") or author.get("full_name") or "")
    return ""


def _extract_employer(engager: dict[str, Any]) -> str:
    """Return engager's employer name, or '' if not determinable. Permissive
    over Trigify's field-naming variations."""
    for key in ("employer", "company", "company_name", "current_company"):
        val = engager.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict):
            name = val.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return ""


_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _build_source_id(post_id: str, engager_linkedin_url: str) -> str:
    return f"trigify:{post_id}:{_linkedin_slug(engager_linkedin_url)}"


def _linkedin_slug(url: str) -> str:
    """``https://linkedin.com/in/jane-doe/`` -> ``jane-doe``. Falls back to
    slugified full URL when ``/in/`` and ``/company/`` both miss."""
    if not url:
        return ""
    lowered = url.lower()
    for pattern in (r"/in/([^/?#]+)", r"/company/([^/?#]+)"):
        m = re.search(pattern, lowered)
        if m:
            handle = m.group(1).strip("-")
            return _SLUG_NON_ALNUM.sub("-", handle).strip("-")
    return _SLUG_NON_ALNUM.sub("-", lowered).strip("-")


async def _safe_log(
    storage: DiscoveryStorage,
    client_id: str,
    *,
    decision_type: str,
    decision: str,
    context: dict[str, Any],
    reasoning: str | None = None,
    confidence: float | None = None,
) -> None:
    """Wrap storage.log_decision — logging failure must never propagate."""
    try:
        await storage.log_decision(
            client_id,
            decision_type=decision_type,
            decision=decision,
            context=context,
            reasoning=reasoning,
            confidence=confidence,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "trigify_discovery decision_log_failed client_id=%s decision=%s error=%r",
            client_id, decision, e,
        )
