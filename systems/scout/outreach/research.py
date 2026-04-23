"""Research module — selects enrich/signal content for draft placeholders.

Pure selection logic: reads ``contact.research_data`` (populated by Task 12
enrich adapters) + component selections (Task 15 composer), returns
placeholder fills. No LLM calls, no HTTP, no DB reads, no contact mutation.
One ``decision_log`` entry per call records the source list so Plan 7 can
attribute outcomes to signals.

Placeholder mapping:
  - ``{{icebreaker_content}}`` → highest-priority trigger event (profile>domain
    match; recency + engagement weighted).
  - ``{{trigger_hook}}`` → most-recent firmographic event (funding_round /
    executive_hire / product_launch / expansion), ≤90d; falls back to
    behavioral events in the same window.
  - ``{{pain_evidence}}`` → citable_detail matching the pain_hook component's
    ``metadata.pain_category_preference``, else first citable_detail, else
    first buying_signal.
  - ``{{cta_content}}`` → passthrough from the cta component's
    ``variant_content`` (in fills struct for uniformity).

``pain_category_preference`` is a convention introduced by this module; the
Task 18 component-authoring SOP documents it operator-side. Weighting
constants (``RECENCY_BANDS_DAYS`` etc.) are hand-coded for MVP; Plan 7 will
learn them from reply-rate data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from systems.scout.outreach.component_store import ComponentVariant


# --------------------------------------------------------------------------- #
# Tunables — MVP hand-coded weights. Plan 7 will learn these.                   #
# --------------------------------------------------------------------------- #

# Recency bands in days. Lower band index = fresher = preferred.
RECENCY_BANDS_DAYS: tuple[int, ...] = (30, 90, 180)

# Match-key strength for trigify behavioral events. profile > domain > name.
_MATCH_KEY_PRIORITY: dict[str | None, int] = {
    "profile": 0, "domain": 1, "name": 2, None: 3,
}

# Engagement boost threshold — likes+comments+shares above this gets -1 bump.
ENGAGEMENT_BOOST_THRESHOLD: int = 10

# Firmographic event types (from claude_web_triggers.py) — strongest outbound
# hooks. Used by _select_trigger_hook.
FIRMOGRAPHIC_EVENT_TYPES: frozenset[str] = frozenset(
    {"funding_round", "executive_hire", "product_launch", "expansion"}
)

# Events older than this are stale for the trigger_hook slot.
TRIGGER_HOOK_MAX_RECENCY_DAYS: int = 90

# Truncation caps.
_DETAIL_PREVIEW_CHARS: int = 80
_DETAIL_MAX_CHARS: int = 160


# --------------------------------------------------------------------------- #
# Data shapes                                                                   #
# --------------------------------------------------------------------------- #

@dataclass
class ResearchFills:
    """Placeholder fills + source audit trail.

    Any field may be ``None`` when no source qualified — composer falls back
    to a generic variant. ``sources_used`` has one entry per filled
    placeholder, deduped by ``(placeholder, source)``.
    """

    icebreaker_content: str | None
    trigger_hook: str | None
    pain_evidence: str | None
    cta_content: str | None
    sources_used: list[dict[str, Any]] = field(default_factory=list)


class DecisionLoggerProtocol(Protocol):
    """Minimal subset of ``aios.foundation.decision_logger.DecisionLogger``."""

    async def log_decision(
        self,
        client_id: str,
        *,
        decision_type: str,
        decision: str,
        context: dict[str, Any],
        reasoning: str | None = None,
        source: str = "system",
        confidence: float | None = None,
    ) -> str | None:
        ...


# --------------------------------------------------------------------------- #
# Public API                                                                    #
# --------------------------------------------------------------------------- #

class ResearchSelector:
    """Select enrich content for composer placeholder fills.

    Stateless. Logger is optional; absent → fills returned without audit emit.
    """

    PLACEHOLDER_FIELDS: tuple[str, ...] = (
        "icebreaker_content", "trigger_hook", "pain_evidence", "cta_content",
    )

    def __init__(self, decision_logger: DecisionLoggerProtocol | None = None) -> None:
        self._logger = decision_logger

    async def select_fills(
        self,
        client_id: str,
        contact: dict[str, Any],
        component_selections: dict[str, ComponentVariant],
        *,
        dry_run: bool = False,
    ) -> ResearchFills:
        """Pick fills for each placeholder. ``dry_run`` flows into the log
        context (Plan 7 filters rehearsal runs) but does not alter selection.
        """
        rd = contact.get("research_data") or {}
        citable_details = _listify(rd.get("citable_details"))
        buying_signals = _listify(rd.get("buying_signals"))
        trigger_events = _listify(rd.get("trigger_events"))
        cta_component = component_selections.get("cta")

        sources_used: list[dict[str, Any]] = []

        icebreaker_content, src = _select_icebreaker(trigger_events)
        if src is not None:
            _append_source(sources_used, "icebreaker_content", src)

        trigger_hook, src = _select_trigger_hook(trigger_events)
        if src is not None:
            _append_source(sources_used, "trigger_hook", src)

        pain_evidence, src = _select_pain_evidence(
            citable_details, buying_signals,
            component_selections.get("pain_hook"),
        )
        if src is not None:
            _append_source(sources_used, "pain_evidence", src)

        cta_content = _select_cta_content(cta_component)
        if cta_content is not None and cta_component is not None:
            _append_passthrough(sources_used, cta_component, cta_content)

        fills = ResearchFills(
            icebreaker_content=icebreaker_content,
            trigger_hook=trigger_hook,
            pain_evidence=pain_evidence,
            cta_content=cta_content,
            sources_used=sources_used,
        )
        await self._emit_decision(client_id, contact, fills, component_selections, dry_run)
        return fills

    async def _emit_decision(
        self,
        client_id: str,
        contact: dict[str, Any],
        fills: ResearchFills,
        component_selections: dict[str, ComponentVariant],
        dry_run: bool,
    ) -> None:
        if self._logger is None:
            return
        contact_id = contact.get("contact_id", "<unknown>")
        filled = [f for f in self.PLACEHOLDER_FIELDS if getattr(fills, f)]
        empty = [f for f in self.PLACEHOLDER_FIELDS if not getattr(fills, f)]
        total = len(self.PLACEHOLDER_FIELDS)
        distinct_sources = {s["source"] for s in fills.sources_used}

        try:
            await self._logger.log_decision(
                client_id=client_id,
                decision_type="research_contact",
                decision=f"research_fills:{contact_id}:{len(filled)}of{total}",
                reasoning=(
                    f"Filled {len(filled)} of {total} placeholders from "
                    f"{len(distinct_sources)} distinct sources"
                ),
                context={
                    "contact_id": contact_id,
                    "niche": contact.get("niche"),
                    "sources_used": fills.sources_used,
                    "placeholders_filled": filled,
                    "placeholders_empty": empty,
                    "component_tuple": {
                        k: v.variant_key
                        for k, v in component_selections.items() if v is not None
                    },
                    "dry_run": dry_run,
                },
                source="system",
                confidence=None,
            )
        except Exception:
            # Logging must never break the waterfall (matches identity orchestrator).
            pass


# --------------------------------------------------------------------------- #
# Selection helpers                                                             #
# --------------------------------------------------------------------------- #

def _listify(value: Any) -> list[dict[str, Any]]:
    """Coerce to a safe list of dicts; drop non-dicts silently (DB JSON columns may have nulls)."""
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, dict)]


def _recency_band(recency_days: int | None) -> int:
    """Recency_days → band index (lower = fresher). None → stalest."""
    if recency_days is None:
        return len(RECENCY_BANDS_DAYS)
    for i, cap in enumerate(RECENCY_BANDS_DAYS):
        if recency_days < cap:
            return i
    return len(RECENCY_BANDS_DAYS)


def _engagement_sum(event: dict[str, Any]) -> int:
    """Sum likes + comments + shares (trigify events); 0 otherwise."""
    eng = event.get("engagement") or {}
    if not isinstance(eng, dict):
        return 0
    return (
        int(eng.get("likes") or 0)
        + int(eng.get("comments") or 0)
        + int(eng.get("shares") or 0)
    )


def _detail_or_none(
    item: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    """Return (truncated_detail, item) if item has a non-empty string detail; else (None, None)."""
    detail = item.get("detail")
    if not isinstance(detail, str) or not detail.strip():
        return None, None
    return detail[:_DETAIL_MAX_CHARS], item


def _select_icebreaker(
    trigger_events: list[dict[str, Any]],
) -> tuple[str | None, dict[str, Any] | None]:
    """Pick the highest-priority trigger event for the icebreaker slot.

    Ordering tuple (lower = better):
      1. Match-key strength: profile < domain < name < None
      2. Recency band: <30d < <90d < <180d < older/undated
      3. Engagement boost: sum > threshold → -1
      4. Raw engagement sum (tie-break, negated to prefer higher)
      5. Insertion order (stable fallback)
    """
    if not trigger_events:
        return None, None

    def sort_key(indexed: tuple[int, dict[str, Any]]) -> tuple[int, int, int, int, int]:
        idx, ev = indexed
        match_pri = _MATCH_KEY_PRIORITY.get(ev.get("match_key"), _MATCH_KEY_PRIORITY[None])
        recency = _recency_band(ev.get("recency_days"))
        eng_sum = _engagement_sum(ev)
        boost = -1 if eng_sum > ENGAGEMENT_BOOST_THRESHOLD else 0
        return (match_pri, recency, boost, -eng_sum, idx)

    winner = sorted(enumerate(trigger_events), key=sort_key)[0][1]
    return _detail_or_none(winner)


def _select_trigger_hook(
    trigger_events: list[dict[str, Any]],
) -> tuple[str | None, dict[str, Any] | None]:
    """Pick the trigger hook — firmographic ≤90d preferred over behavioral."""
    if not trigger_events:
        return None, None

    def qualifies(ev: dict[str, Any]) -> bool:
        recency = ev.get("recency_days")
        # Undated events aren't disqualified (some adapters omit recency);
        # dated events win ties via the sort key below.
        return recency is None or int(recency) <= TRIGGER_HOOK_MAX_RECENCY_DAYS

    firmographic: list[dict[str, Any]] = []
    behavioral: list[dict[str, Any]] = []
    for ev in trigger_events:
        if not qualifies(ev):
            continue
        if ev.get("type") in FIRMOGRAPHIC_EVENT_TYPES:
            firmographic.append(ev)
        else:
            behavioral.append(ev)

    pool = firmographic or behavioral
    if not pool:
        return None, None

    def sort_key(ev: dict[str, Any]) -> tuple[int, int]:
        # Dated events before undated; smaller recency first.
        recency = ev.get("recency_days")
        return (0 if recency is not None else 1, int(recency) if recency is not None else 0)

    return _detail_or_none(sorted(pool, key=sort_key)[0])


def _select_pain_evidence(
    citable_details: list[dict[str, Any]],
    buying_signals: list[dict[str, Any]],
    pain_hook_component: ComponentVariant | None,
) -> tuple[str | None, dict[str, Any] | None]:
    """Pick pain_evidence — prefer type-matched citable_detail, else fall back."""
    preferred_category: str | None = None
    if pain_hook_component is not None:
        md = pain_hook_component.metadata or {}
        if isinstance(md, dict):
            pref = md.get("pain_category_preference")
            if isinstance(pref, str) and pref:
                preferred_category = pref

    def first_with_detail(
        items: list[dict[str, Any]],
        type_filter: str | None = None,
    ) -> tuple[str | None, dict[str, Any] | None]:
        for item in items:
            if type_filter is not None and item.get("type") != type_filter:
                continue
            found, src = _detail_or_none(item)
            if src is not None:
                return found, src
        return None, None

    if citable_details:
        if preferred_category:
            found, src = first_with_detail(citable_details, preferred_category)
            if src is not None:
                return found, src
        found, src = first_with_detail(citable_details)
        if src is not None:
            return found, src

    return first_with_detail(buying_signals)


def _select_cta_content(cta_component: ComponentVariant | None) -> str | None:
    """Passthrough from the cta component. No research_data lookup."""
    if cta_component is None:
        return None
    content = cta_component.variant_content
    if not isinstance(content, str) or not content.strip():
        return None
    return content


# --------------------------------------------------------------------------- #
# Audit trail                                                                   #
# --------------------------------------------------------------------------- #

def _append_audit(
    sources_used: list[dict[str, Any]],
    *,
    placeholder: str,
    source: str,
    detail_preview: str,
    event_type: str,
) -> None:
    """Append audit entry, dedup by (placeholder, source)."""
    for existing in sources_used:
        if existing["placeholder"] == placeholder and existing["source"] == source:
            return
    sources_used.append({
        "placeholder": placeholder,
        "source": source,
        "detail_preview": detail_preview[:_DETAIL_PREVIEW_CHARS],
        "type": event_type,
    })


def _append_source(
    sources_used: list[dict[str, Any]],
    placeholder: str,
    event: dict[str, Any],
) -> None:
    """Record an enrich-sourced fill in the audit trail."""
    detail = event.get("detail") or ""
    if not isinstance(detail, str):
        detail = str(detail)
    _append_audit(
        sources_used,
        placeholder=placeholder,
        source=str(event.get("source") or "unknown"),
        detail_preview=detail,
        event_type=str(event.get("type") or event.get("category") or "unknown"),
    )


def _append_passthrough(
    sources_used: list[dict[str, Any]],
    cta_component: ComponentVariant,
    cta_content: str,
) -> None:
    """Record the cta passthrough — source is the variant itself."""
    _append_audit(
        sources_used,
        placeholder="cta_content",
        source=f"component:{cta_component.variant_key}",
        detail_preview=cta_content,
        event_type="component_passthrough",
    )
