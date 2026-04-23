"""Trigify monitor provisioning — create side of the Trigify API.

Companion to systems/scout/enrich/trigify.py (pull side). This module is called
ONCE at client onboarding to provision monitors, then never again (unless the
operator adds a new competitor or thought leader).

Output: for each monitor spec in the operator's YAML, call POST /v1/searches,
get back a search_id, append to client_config.trigify_search_ids.

Idempotency: before creating, GET /v1/searches and check for a name collision
(prefix ``[{client_id}]-...``). If a monitor with the same name exists, skip
creation and return the existing ID.

Monitor types supported (per Max Mitcham webinar 2026-04-22, YouTube
bKEmJIch0nI):
  - intent_keyword              — buyer-intent keyword watchers
  - competitor_engagement       — watch engagement on competitor profiles/pages
  - thought_leader_engagement   — watch engagement on authority profiles
  - brand_mention               — watch own-brand mentions + misspellings

This module is a provisioning utility, NOT a ``CompanySourceAdapter``. The
daily discovery source adapter (pending, Task 1.5.9b) will consume the search
IDs this module writes.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from config.settings import get_settings

logger = logging.getLogger(__name__)

TRIGIFY_API_BASE = "https://api.trigify.io/v1"
TRIGIFY_SEARCHES_URL = f"{TRIGIFY_API_BASE}/searches"

# Per Max webinar 2026-04-22: intent keywords + competitor engagement +
# thought-leader engagement + brand mentions.
VALID_MONITOR_TYPES: frozenset[str] = frozenset({
    "intent_keyword",
    "competitor_engagement",
    "thought_leader_engagement",
    "brand_mention",
})

# Type prefix used in the monitor name (shorter than the internal enum).
_TYPE_PREFIX: dict[str, str] = {
    "intent_keyword": "intent",
    "competitor_engagement": "competitor",
    "thought_leader_engagement": "thought-leader",
    "brand_mention": "brand",
}

# Default platforms when the operator doesn't specify.
_DEFAULT_INTENT_PLATFORMS: list[str] = ["linkedin", "x"]
_DEFAULT_BRAND_PLATFORMS: list[str] = ["linkedin", "x"]

_SLUG_MAX_LEN = 40
_HTTP_TIMEOUT_SECONDS = 30.0


# --------------------------------------------------------------------------- #
# Data classes                                                                  #
# --------------------------------------------------------------------------- #

@dataclass
class MonitorSpec:
    """One monitor to create. Built from the operator's YAML."""

    name: str                         # [client_id]-{type}-{slug} (auto-built)
    monitor_type: str                 # one of VALID_MONITOR_TYPES
    trigify_payload: dict[str, Any]   # {query, platforms} or {target_url, ...}
    source_yaml_section: str          # "intent_keywords" | "competitors" | ...


@dataclass
class ProvisioningResult:
    """What the creator returns. Operator reads this to verify."""

    client_id: str
    created: list[tuple[str, str]] = field(default_factory=list)
    """[(name, search_id)] for monitors newly created."""

    skipped_existing: list[tuple[str, str]] = field(default_factory=list)
    """[(name, search_id)] for monitors that already existed (idempotent)."""

    failed: list[tuple[str, str]] = field(default_factory=list)
    """[(name, error_message)] for monitors whose POST failed."""

    all_search_ids: list[str] = field(default_factory=list)
    """created + skipped_existing IDs, persisted to client_config."""

    dry_run_planned: list[MonitorSpec] = field(default_factory=list)
    """If dry_run=True, the MonitorSpec list that WOULD be created."""


# --------------------------------------------------------------------------- #
# Storage protocol                                                              #
# --------------------------------------------------------------------------- #

class TrigifyMonitorStorage(Protocol):
    """Storage contract for persisting search IDs post-creation."""

    async def update_trigify_search_ids(
        self, client_id: str, search_ids: list[str],
    ) -> None:
        """Overwrite ``client_config.trigify_search_ids`` with the full list."""
        ...


# --------------------------------------------------------------------------- #
# Creator                                                                        #
# --------------------------------------------------------------------------- #

class TrigifyMonitorCreator:
    """Provision Trigify monitors via POST /v1/searches. Idempotent."""

    def __init__(
        self,
        storage: TrigifyMonitorStorage,
        *,
        http_client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
    ) -> None:
        """storage: backend to persist search IDs after creation.
        http_client: inject for tests (MockTransport). Production passes None.
        api_key: override for tests; if None, read from settings lazily."""
        self._storage = storage
        self._http_client = http_client
        self._api_key = api_key

    async def provision_from_yaml(
        self,
        client_id: str,
        yaml_spec: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> ProvisioningResult:
        """Parse YAML → build MonitorSpec[] → check idempotency → provision.

        yaml_spec shape (operator-authored):
            intent_keywords:
              - phrase: "social signals"
                scope_terms: ["gtm", "outbound"]
                platforms: ["linkedin"]     # optional, defaults to linkedin+x
            competitors:
              - name: "Clay.com"
                linkedin_url: "https://linkedin.com/company/clay-labs"
            thought_leaders:
              - name: "Nick Saraev"
                linkedin_url: "https://linkedin.com/in/nicksaraev"
            brand:
              - "Triggery"
              - "TrggerFy"

        dry_run=True: parse + build specs, NO HTTP calls, return
        ``dry_run_planned`` populated for operator confirmation.
        """
        specs = _build_specs_from_yaml(client_id, yaml_spec)
        result = ProvisioningResult(client_id=client_id)

        if dry_run:
            result.dry_run_planned = specs
            logger.info(
                "trigify_monitor_creator dry_run client_id=%s planned=%d",
                client_id, len(specs),
            )
            return result

        api_key = self._resolve_api_key()

        client_provided = self._http_client is not None
        client = self._http_client or httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS)

        try:
            existing = await _fetch_existing_for_client(client, api_key, client_id)
            # Map of name -> search_id for this client only.
            for spec in specs:
                if spec.name in existing:
                    existing_id = existing[spec.name]
                    result.skipped_existing.append((spec.name, existing_id))
                    continue

                try:
                    new_id = await _create_monitor(client, api_key, spec)
                except httpx.HTTPStatusError as e:
                    err = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                    result.failed.append((spec.name, err))
                    logger.warning(
                        "trigify_monitor_creator create_failed client_id=%s name=%s error=%s",
                        client_id, spec.name, err,
                    )
                    continue
                except httpx.HTTPError as e:
                    err = f"Network error: {e!r}"
                    result.failed.append((spec.name, err))
                    logger.warning(
                        "trigify_monitor_creator network_error client_id=%s name=%s error=%s",
                        client_id, spec.name, err,
                    )
                    continue

                result.created.append((spec.name, new_id))
        finally:
            if not client_provided:
                await client.aclose()

        result.all_search_ids = (
            [sid for _, sid in result.created]
            + [sid for _, sid in result.skipped_existing]
        )

        # Persist — even if some failed, we commit the partial successes.
        await self._storage.update_trigify_search_ids(
            client_id, result.all_search_ids,
        )

        logger.info(
            "trigify_monitor_creator provisioned client_id=%s created=%d "
            "skipped_existing=%d failed=%d total_ids=%d",
            client_id,
            len(result.created),
            len(result.skipped_existing),
            len(result.failed),
            len(result.all_search_ids),
        )
        return result

    def _resolve_api_key(self) -> str:
        """Return the key from constructor override or settings. Raises
        EnvironmentError early with an actionable message if unset."""
        if self._api_key:
            return self._api_key
        settings = get_settings()
        key = settings.trigify_api_key
        if not key:
            raise EnvironmentError(
                "TRIGIFY_API_KEY is not set. Add it to .env (see "
                "skills/onboarding/configure-trigify-monitors.md preconditions)."
            )
        return key


# --------------------------------------------------------------------------- #
# YAML → MonitorSpec[]                                                          #
# --------------------------------------------------------------------------- #

def _build_specs_from_yaml(
    client_id: str, yaml_spec: dict[str, Any],
) -> list[MonitorSpec]:
    """Walk the 4 YAML sections, build MonitorSpec[] with validated payloads.

    Raises ValueError with a pointer to the offending section/item on malformed
    input."""
    if not isinstance(yaml_spec, dict):
        raise ValueError(
            "yaml_spec must be a mapping; got " + type(yaml_spec).__name__
        )

    specs: list[MonitorSpec] = []
    specs.extend(_parse_intent_keywords(client_id, yaml_spec.get("intent_keywords") or []))
    specs.extend(_parse_competitors(client_id, yaml_spec.get("competitors") or []))
    specs.extend(_parse_thought_leaders(client_id, yaml_spec.get("thought_leaders") or []))
    specs.extend(_parse_brand(client_id, yaml_spec.get("brand") or []))
    return specs


def _parse_intent_keywords(
    client_id: str, entries: list[Any],
) -> list[MonitorSpec]:
    if not isinstance(entries, list):
        raise ValueError("intent_keywords must be a list")
    out: list[MonitorSpec] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(
                f"intent_keywords[{idx}]: expected mapping, got {type(entry).__name__}"
            )
        phrase = (entry.get("phrase") or "").strip()
        if not phrase:
            raise ValueError(
                f"intent_keywords[{idx}]: missing required field 'phrase'"
            )
        scope_terms = entry.get("scope_terms") or []
        if not isinstance(scope_terms, list):
            raise ValueError(
                f"intent_keywords[{idx}]: 'scope_terms' must be a list"
            )
        platforms = entry.get("platforms") or _DEFAULT_INTENT_PLATFORMS
        if not isinstance(platforms, list) or not platforms:
            raise ValueError(
                f"intent_keywords[{idx}]: 'platforms' must be a non-empty list"
            )

        # Build query: phrase + optional scope_terms (all required in post text).
        query = phrase
        if scope_terms:
            query = phrase + " " + " ".join(str(t) for t in scope_terms)

        name = _build_name(client_id, "intent_keyword", phrase)
        payload = {"query": query, "platforms": list(platforms)}

        out.append(MonitorSpec(
            name=name,
            monitor_type="intent_keyword",
            trigify_payload=payload,
            source_yaml_section="intent_keywords",
        ))
    return out


def _parse_competitors(
    client_id: str, entries: list[Any],
) -> list[MonitorSpec]:
    if not isinstance(entries, list):
        raise ValueError("competitors must be a list")
    out: list[MonitorSpec] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(
                f"competitors[{idx}]: expected mapping, got {type(entry).__name__}"
            )
        name_field = (entry.get("name") or "").strip()
        url = (entry.get("linkedin_url") or "").strip()
        if not name_field:
            raise ValueError(
                f"competitors[{idx}]: missing required field 'name'"
            )
        if not url:
            raise ValueError(
                f"competitors[{idx}]: missing required field 'linkedin_url'"
            )

        name = _build_name(client_id, "competitor_engagement", name_field)
        payload = {"target_url": url}

        out.append(MonitorSpec(
            name=name,
            monitor_type="competitor_engagement",
            trigify_payload=payload,
            source_yaml_section="competitors",
        ))
    return out


def _parse_thought_leaders(
    client_id: str, entries: list[Any],
) -> list[MonitorSpec]:
    if not isinstance(entries, list):
        raise ValueError("thought_leaders must be a list")
    out: list[MonitorSpec] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(
                f"thought_leaders[{idx}]: expected mapping, got {type(entry).__name__}"
            )
        name_field = (entry.get("name") or "").strip()
        url = (entry.get("linkedin_url") or "").strip()
        if not name_field:
            raise ValueError(
                f"thought_leaders[{idx}]: missing required field 'name'"
            )
        if not url:
            raise ValueError(
                f"thought_leaders[{idx}]: missing required field 'linkedin_url'"
            )

        name = _build_name(client_id, "thought_leader_engagement", name_field)
        payload = {"target_url": url}

        out.append(MonitorSpec(
            name=name,
            monitor_type="thought_leader_engagement",
            trigify_payload=payload,
            source_yaml_section="thought_leaders",
        ))
    return out


def _parse_brand(
    client_id: str, entries: list[Any],
) -> list[MonitorSpec]:
    if not isinstance(entries, list):
        raise ValueError("brand must be a list")
    out: list[MonitorSpec] = []
    for idx, entry in enumerate(entries):
        # Brand entries are plain strings (brand term + misspellings).
        if not isinstance(entry, str):
            raise ValueError(
                f"brand[{idx}]: expected string, got {type(entry).__name__}"
            )
        term = entry.strip()
        if not term:
            raise ValueError(f"brand[{idx}]: empty string not allowed")

        name = _build_name(client_id, "brand_mention", term)
        payload = {"query": term, "platforms": list(_DEFAULT_BRAND_PLATFORMS)}

        out.append(MonitorSpec(
            name=name,
            monitor_type="brand_mention",
            trigify_payload=payload,
            source_yaml_section="brand",
        ))
    return out


# --------------------------------------------------------------------------- #
# Naming + slug                                                                 #
# --------------------------------------------------------------------------- #

def _build_name(client_id: str, monitor_type: str, source_text: str) -> str:
    """Return ``[{client_id}]-{type_prefix}-{slug}``. Deterministic."""
    if monitor_type not in VALID_MONITOR_TYPES:
        raise ValueError(f"unknown monitor_type: {monitor_type}")
    prefix = _TYPE_PREFIX[monitor_type]
    slug = _slugify(source_text)
    return f"[{client_id}]-{prefix}-{slug}"


def _slugify(text: str) -> str:
    """Kebab-case + max 40 chars, truncated at word boundary when possible.

    "social signals" → "social-signals"
    "Clay.com" → "clay-com"
    "social signals in GTM" → "social-signals-in-gtm"
    """
    if not text:
        return ""
    # Lowercase, replace any non-alphanumeric run with a dash.
    lowered = text.lower()
    collapsed = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if len(collapsed) <= _SLUG_MAX_LEN:
        return collapsed
    # Truncate at word boundary: drop trailing partial word after cut.
    cut = collapsed[:_SLUG_MAX_LEN]
    # If we cut mid-word (next char after cut is alnum), back off to last dash.
    if len(collapsed) > _SLUG_MAX_LEN and collapsed[_SLUG_MAX_LEN] not in ("-", ""):
        last_dash = cut.rfind("-")
        if last_dash > 0:
            cut = cut[:last_dash]
    return cut.rstrip("-")


# --------------------------------------------------------------------------- #
# HTTP helpers                                                                   #
# --------------------------------------------------------------------------- #

async def _fetch_existing_for_client(
    client: httpx.AsyncClient, api_key: str, client_id: str,
) -> dict[str, str]:
    """GET /v1/searches, filter by ``[{client_id}]-`` name prefix, return
    {name: search_id}. Monitors belonging to OTHER clients are stripped."""
    response = await client.get(
        TRIGIFY_SEARCHES_URL,
        headers={"x-api-key": api_key},
    )
    response.raise_for_status()
    body = response.json()
    # Accept either {"searches": [...]} or bare list — be permissive.
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
        if not name or not sid:
            continue
        if name.startswith(prefix):
            out[name] = str(sid)
    return out


async def _create_monitor(
    client: httpx.AsyncClient, api_key: str, spec: MonitorSpec,
) -> str:
    """POST /v1/searches. Returns the new search_id. Raises httpx.HTTPStatusError
    on non-2xx."""
    body = {
        "name": spec.name,
        "monitor_type": spec.monitor_type,
        **spec.trigify_payload,
    }
    response = await client.post(
        TRIGIFY_SEARCHES_URL,
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        json=body,
    )
    response.raise_for_status()
    payload = response.json()
    sid = payload.get("id") or payload.get("search_id") or ""
    if not sid:
        raise ValueError(
            f"Trigify POST /v1/searches succeeded but returned no id "
            f"for monitor name={spec.name!r}"
        )
    return str(sid)
