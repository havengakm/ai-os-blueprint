"""Composer — bandit-selects components, fills placeholders, persists draft.

Per-contact flow: fetch approved ComponentVariants for (niche, offer_label),
epsilon-greedy select one per component_type on ``win_rate``, call
ResearchSelector for placeholder fills, render subject + body, persist a
draft row (unless dry_run), emit one decision_log entry.

No LLM calls. No network. Pure composition over already-fetched variants
and already-enriched research data.

component_selections uses stable ``variant_key`` strings (not DB UUIDs) so
audit logs stay human-readable and survive DB re-seeds — Plan 7 cohort
evaluators can match selections back to YAML source files without
dereferencing a UUID through a live DB.
"""
from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from systems.scout.outreach.component_store import ComponentVariant
    from systems.scout.outreach.research import ResearchFills, ResearchSelector

logger = logging.getLogger(__name__)

# --- Tunables --------------------------------------------------------------- #

DEFAULT_EPSILON: float = 0.1

#: Active directories that populate contact.research_data.ad_activity. Variants
#: that reference {{ad_activity_observation}} are only selectable when at least
#: one of these is active on the client.
AD_ACTIVITY_DIRECTORIES: frozenset[str] = frozenset({
    "google_ads_library", "linkedin_ads_library", "meta_ads_library",
})
#: Component types the composer REQUIRES a variant for. A missing
#: pool for any of these yields a ComposerSkip with reason
#: ``no_variants_for:<type>``. v3 locks creative_branding on all 9
#: types — ``bridge`` is the new substantive transition between
#: icebreaker and who_i_am, and ``pain_hook`` is back in required
#: with empathy-led content.
COMPONENT_TYPES_REQUIRED: tuple[str, ...] = (
    "subject_line", "icebreaker", "bridge", "who_i_am", "pain_hook",
    "credibility", "offer_frame", "cta", "signature",
)
#: Component types the composer will USE if variants are available,
#: but will skip silently when the pool is empty.
#: - body_template (Plan 1.5 Task 1.5.7): outer-frame variant. When
#:   selected, the composer renders inner body components first then
#:   substitutes them into the template's placeholders. When the pool
#:   is empty, the composer falls back to the legacy modular concat.
COMPONENT_TYPES_OPTIONAL: tuple[str, ...] = ("body_template",)
#: Union of required + optional, ordered for iteration. Exported for
#: backward compatibility + symmetry with the pre-v2 surface.
COMPONENT_TYPES_ORDERED: tuple[str, ...] = (
    "subject_line", "icebreaker", "bridge", "who_i_am", "pain_hook",
    "credibility", "offer_frame", "cta", "signature", "body_template",
)
#: Body rendering order — top-to-bottom as the prospect reads it.
#: v3: bridge sits between icebreaker and who_i_am; pain_hook precedes
#: credibility so empathy sets up the proof. Optional types are dropped
#: silently when absent from the selection map.
_BODY_COMPONENTS: tuple[str, ...] = (
    "icebreaker", "bridge", "who_i_am", "pain_hook", "credibility",
    "offer_frame", "cta", "signature",
)
_BODY_SEPARATOR: str = "\n\n"
# Neutral prior keeps win_rate=None variants in contention vs weak-signal winners.
_NEUTRAL_WIN_RATE_PRIOR: float = 0.5
_AD_ACTIVITY_PLACEHOLDER: str = "{{ad_activity_observation}}"
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")
_PLATFORM_LABELS: dict[str, str] = {
    "google": "Google", "linkedin": "LinkedIn", "facebook": "Facebook",
    "instagram": "Instagram", "tiktok": "TikTok",
}
_DECISION_SUBJECT_PREVIEW: int = 60
# Map {{placeholder}} name -> ResearchFills attribute.
# ``first_name`` is deliberately absent — the composer resolves it via its
# own ``_coalesce_first_name`` branch (falls back to "there", never flagged
# as missing). The other productised placeholders route through ResearchFills
# so the ``{{short_company_name}} / {{operator_name}} / {{offer_*}}`` slots
# surface in ``fills_missing`` when their source is empty.
_RESEARCH_PLACEHOLDER_ATTRS: dict[str, str] = {
    "icebreaker_content": "icebreaker_content",
    "trigger_hook": "trigger_hook",
    "pain_evidence": "pain_evidence",
    "cta_content": "cta_content",
    "short_company_name": "short_company_name",
    "operator_name": "operator_name",
    "offer_promise": "offer_promise",
    "offer_period": "offer_period",
    "offer_risk_reversal": "offer_risk_reversal",
    # v2 niche-level fills — source: client_facts. Power the shared
    # who_i_am + offer_frame templates across deployments.
    "niche": "niche",
    "niche_specific_term": "niche_specific_term",
    "meetings_niche_term": "meetings_niche_term",
}


# --- Data shapes ----------------------------------------------------------- #

@dataclass
class ComposedDraft:
    """Successful composition result.

    ``component_selections`` maps component_type -> variant_key (stable string).
    ``fills_missing`` lists placeholder names that appeared in at least one
    component's content but had no corresponding fill; these render as empty
    strings so the caller can decide whether the gap is acceptable.
    """

    contact_id: str
    subject: str
    body: str
    component_selections: dict[str, str]
    sources_referenced: list[dict[str, Any]]
    fills_missing: list[str]
    persisted_draft_id: str | None


@dataclass
class ComposerSkip:
    """Returned when composition cannot proceed — typically because a required
    component_type has zero approved variants (possibly after ad-activity
    filtering)."""

    contact_id: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


# --- Storage contract ------------------------------------------------------ #

class ComposerStorageBackend(Protocol):
    """Storage contract — tests inject an in-memory fake; Task 16 wires Supabase.

    Five methods: ``fetch_eligible_contacts`` (daemon batch-entry), the
    per-contact trio (``fetch_approved_variants`` + ``fetch_active_directories``
    + ``persist_draft``), and ``log_decision``.
    """

    async def fetch_eligible_contacts(
        self,
        client_id: str,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return contacts eligible for compose — status ``'enriched'``,
        ``icp_tier`` in A/B/C, no existing ``outreach_drafts`` row yet.
        Caller iterates and passes each to ``Composer.compose()``. If
        ``limit`` is ``None``, no cap. ``limit`` caps the returned
        eligible set (after excluding contacts that already have a
        draft), not the candidate pool."""
        ...

    async def fetch_approved_variants(
        self,
        client_id: str,
        niche: str,
        offer_label: str,
    ) -> dict[str, list[ComponentVariant]]:
        """Return ``component_type -> list[ComponentVariant]`` where
        ``status='approved'`` and niche + offer_label match. Missing types MAY
        be absent from the dict or mapped to ``[]`` — both are tolerated."""
        ...

    async def fetch_active_directories(self, client_id: str) -> list[str]:
        """Return ``client_config.active_directories``; empty list means none."""
        ...

    async def fetch_client_facts(self, client_id: str) -> dict[str, Any]:
        """Return a flat ``{key: value_str}`` lookup of this client's facts.

        Used by ResearchSelector to fill deployment-agnostic placeholders
        (``operator_name``, ``offer_promise``, ``offer_period``,
        ``offer_risk_reversal``). Empty dict when the client has no facts
        — the composer will then surface the missing placeholders via
        ``fills_missing`` so operators can spot unseeded deployments.
        """
        ...

    async def persist_draft(
        self,
        client_id: str,
        contact_id: str,
        *,
        subject: str,
        body: str,
        component_selections: dict[str, str],
        research_sources: list[dict[str, Any]],
    ) -> str:
        """Insert into outreach_drafts; returns the new draft UUID."""
        ...

    async def log_decision(self, client_id: str, **kwargs: Any) -> str | None:
        """Minimal subset of DecisionLogger.log_decision."""
        ...


# --- Composer -------------------------------------------------------------- #

class Composer:
    """Bandit-driven draft composer.

    Stateless between ``compose`` calls. Inject a seeded ``rng`` for
    deterministic tests. ``epsilon`` is the exploration rate (0 = pure exploit,
    1 = pure explore).
    """

    def __init__(
        self,
        storage: ComposerStorageBackend,
        research_selector: ResearchSelector,
        *,
        epsilon: float = DEFAULT_EPSILON,
        rng: random.Random | None = None,
        validate_writing: bool = True,
    ) -> None:
        """``validate_writing`` defaults True (production safety net per
        Slice 21 of 2026-04-29 — em-dashes / AI-cliches / buzzwords fail
        the draft closed). Unit tests use legacy fixtures that don't pass
        the validator yet; pass ``validate_writing=False`` in those tests.
        Updating the fixtures is its own follow-up slice."""
        self._storage = storage
        self._research = research_selector
        self._epsilon = epsilon
        self._rng = rng or random.Random()
        self._validate_writing = validate_writing

    async def compose(
        self,
        client_id: str,
        contact: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> ComposedDraft | ComposerSkip:
        """Compose a draft for one contact. Returns ``ComposedDraft`` on success
        (also on persistence failure — decision_log still fires and
        ``persisted_draft_id`` is ``None``). Returns ``ComposerSkip`` when any
        component_type has zero approved variants after ad-activity filtering;
        a decision_log entry records why."""
        contact_id: str = contact.get("contact_id", "<unknown>")
        niche: str = contact.get("niche", "")
        offer_label: str = contact.get("offer_label", "")

        variants_by_type = await self._storage.fetch_approved_variants(
            client_id, niche, offer_label,
        )
        active_directories = await self._storage.fetch_active_directories(client_id)
        # Per-contact fetch for MVP — compose() is the per-contact entry point
        # (the batch loop lives in the daemon). Plan 7 can add a per-batch
        # cache layer here if the DB hit-rate becomes a concern.
        client_facts = await self._storage.fetch_client_facts(client_id)
        has_ad_activity_enabled = any(
            d in AD_ACTIVITY_DIRECTORIES for d in active_directories
        )

        filtered_by_type = _filter_ad_activity_variants(
            variants_by_type, has_ad_activity_enabled,
        )

        selections: dict[str, ComponentVariant] = {}
        for component_type in COMPONENT_TYPES_ORDERED:
            pool = filtered_by_type.get(component_type) or []
            if not pool:
                if component_type in COMPONENT_TYPES_OPTIONAL:
                    # Silently skip — the body renderer drops optional
                    # types that don't have a selection for this contact.
                    continue
                skip = ComposerSkip(
                    contact_id=contact_id,
                    reason=f"no_variants_for:{component_type}",
                    details={
                        "niche": niche,
                        "offer_label": offer_label,
                        "ad_activity_enabled": has_ad_activity_enabled,
                    },
                )
                await self._emit_decision(
                    client_id,
                    decision_type="render_draft",
                    decision=f"render_draft:skip:{contact_id}:{skip.reason}",
                    reasoning=f"Composer skipped contact: {skip.reason}",
                    context={
                        "contact_id": contact_id,
                        "niche": niche,
                        "offer_label": offer_label,
                        "channel": "email",
                        "skip_reason": skip.reason,
                        "skip_details": skip.details,
                        "dry_run": dry_run,
                    },
                    source="system",
                    confidence=None,
                )
                return skip
            selections[component_type] = self._bandit_select(pool)

        fills = await self._research.select_fills(
            client_id, contact, selections,
            client_facts=client_facts, dry_run=dry_run,
        )

        fills_missing: list[str] = []
        subject = self._render_template(
            selections["subject_line"].variant_content,
            contact, fills, fills_missing,
        )
        if "body_template" in selections:
            # Body template path (Plan 1.5 Task 1.5.7). Render each inner
            # body component first using research fills, then substitute the
            # rendered text into the body_template's placeholders. Enables
            # template-level bandit A/B (modular vs storytelling) without
            # rewriting the inner components.
            inner_renders: dict[str, str] = {
                f"{ct}_content": self._render_template(
                    selections[ct].variant_content,
                    contact, fills, fills_missing,
                )
                for ct in _BODY_COMPONENTS
                if ct in selections
            }
            body = self._render_template(
                selections["body_template"].variant_content,
                contact, fills, fills_missing, extras=inner_renders,
            )
        else:
            # Modular fallback: legacy behaviour preserved. Inner body
            # components are concatenated with the body separator.
            #
            # Drop empty / whitespace-only renders so an unfilled component
            # (e.g. v1_passthrough icebreaker without enrichment-generated
            # content) doesn't leave a leading blank-line stub in the body.
            rendered_sections = [
                self._render_template(
                    selections[ct].variant_content,
                    contact, fills, fills_missing,
                )
                for ct in _BODY_COMPONENTS
                if ct in selections  # optional types (pain_hook) drop out cleanly
            ]
            body = _BODY_SEPARATOR.join(
                section for section in rendered_sections if section.strip()
            )
        fills_missing = _dedup_preserve_order(fills_missing)

        component_selections = {t: v.variant_key for t, v in selections.items()}

        # Fail-closed writing-rule check on the rendered body. Catches the
        # AI-speak / em-dash / buzzword class of bug the operator caught
        # 2026-04-29 (Slice 21). If the body fails the writing guardrails,
        # log a decision and SKIP persistence — caller treats this contact
        # as "not drafted" so it remains eligible for re-render once the
        # underlying template / icebreaker source is fixed.
        from systems.scout.outreach.writing_validator import (
            validate_writing as _validate_writing_fn,
        )
        body_validation = (
            _validate_writing_fn(body, context="cold_email")
            if self._validate_writing
            else None
        )
        if body_validation is not None and not body_validation.passed:
            await self._emit_decision(
                client_id,
                decision_type="render_draft",
                decision=(
                    f"render_draft:skip:{contact_id}:writing_validation_failed"
                ),
                reasoning=(
                    f"Composer skipped persist: {body_validation.violation_summary}"
                ),
                context={
                    "contact_id": contact_id,
                    "violations": [
                        {"rule": v.rule, "offending_text": v.offending_text}
                        for v in body_validation.violations[:5]
                    ],
                    "subject_preview": subject[:_DECISION_SUBJECT_PREVIEW],
                },
            )
            return ComposerSkip(
                contact_id=contact_id,
                reason="writing_validation_failed",
                details={
                    "violations": [
                        {"rule": v.rule, "offending_text": v.offending_text}
                        for v in body_validation.violations[:5]
                    ],
                    "subject_preview": subject[:_DECISION_SUBJECT_PREVIEW],
                },
            )

        persisted_id: str | None = None
        if not dry_run:
            try:
                persisted_id = await self._storage.persist_draft(
                    client_id, contact_id,
                    subject=subject, body=body,
                    component_selections=component_selections,
                    research_sources=fills.sources_used,
                )
            except Exception as exc:
                logger.warning(
                    "composer persist failed contact_id=%s error=%s",
                    contact_id, exc,
                )

        await self._emit_decision(
            client_id,
            decision_type="render_draft",
            decision=(
                f"render_draft:{contact_id}:"
                f"{subject[:_DECISION_SUBJECT_PREVIEW]}"
            ),
            reasoning=(
                f"Composed from {len(selections)} components; "
                f"{len(fills_missing)} placeholders unfilled"
            ),
            context={
                "contact_id": contact_id,
                "niche": niche,
                "offer_label": offer_label,
                "sequence_round": contact.get("sequence_round"),
                "channel": "email",
                "component_tuple": component_selections,
                "fills_missing": fills_missing,
                "signals_referenced": fills.sources_used,
                "persisted_draft_id": persisted_id,
                "dry_run": dry_run,
            },
            source="system",
            confidence=None,
        )

        return ComposedDraft(
            contact_id=contact_id,
            subject=subject,
            body=body,
            component_selections=component_selections,
            sources_referenced=list(fills.sources_used),
            fills_missing=fills_missing,
            persisted_draft_id=persisted_id,
        )

    # ------------------------------------------------------------------ #

    def _bandit_select(self, pool: list[ComponentVariant]) -> ComponentVariant:
        """Epsilon-greedy selection.

        Single-variant pools skip math. With probability ``epsilon``:
        uniform-random explore. Otherwise exploit by ``(win_rate, sample_size)``
        descending — ``win_rate=None`` gets the neutral 0.5 prior. Remaining
        ties resolve via RNG to avoid stable first-seen bias.
        """
        if len(pool) == 1:
            return pool[0]
        if self._rng.random() < self._epsilon:
            return self._rng.choice(pool)
        best_score = max(_score(v) for v in pool)
        leaders = [v for v in pool if _score(v) == best_score]
        return leaders[0] if len(leaders) == 1 else self._rng.choice(leaders)

    def _render_template(
        self,
        template: str,
        contact: dict[str, Any],
        fills: ResearchFills,
        fills_missing: list[str],
        extras: dict[str, str] | None = None,
    ) -> str:
        """Replace ``{{placeholder}}`` tokens. Unknown/empty placeholders
        render as empty string AND append the name to ``fills_missing``.

        ``extras`` (Plan 1.5 Task 1.5.7) is an optional dict that takes
        precedence over the standard resolution chain. Used by the
        body_template path to substitute pre-rendered inner-component
        text (``icebreaker_content``, ``bridge_content``, etc.) into the
        outer body_template variant's placeholders.
        """
        research_data = contact.get("research_data") or {}
        ad_activity_value = _render_ad_activity_observation(
            research_data.get("ad_activity") if isinstance(research_data, dict) else None,
        )
        first_name_value = _coalesce_first_name(contact.get("first_name"))
        company_value = _stringify(contact.get("company"))
        extras = extras or {}

        def resolve(name: str) -> str:
            # Extras (body_template inner renders) take precedence so the
            # outer template can refer to inner-component text by the same
            # placeholder name as the corresponding research fill.
            if name in extras:
                return extras[name]
            if name == "first_name":
                return first_name_value
            if name == "company":
                return company_value
            if name == "ad_activity_observation":
                # Empty observation is acceptable when variant-filter is off
                # but this contact has no ad_activity; don't flag as missing.
                return ad_activity_value
            if name == "signature_content":
                return ""  # signature is rendered as its own body segment
            attr = _RESEARCH_PLACEHOLDER_ATTRS.get(name)
            if attr is not None:
                value = getattr(fills, attr)
                if value is None or value == "":
                    fills_missing.append(name)
                    return ""
                return value
            fills_missing.append(name)
            return ""

        return _PLACEHOLDER_RE.sub(lambda m: resolve(m.group(1)), template)

    async def _emit_decision(
        self, client_id: str, **kwargs: Any,
    ) -> None:
        """Fire log_decision; swallow all exceptions (logging never breaks us)."""
        try:
            await self._storage.log_decision(client_id, **kwargs)
        except Exception:
            pass


# --- Module-level helpers -------------------------------------------------- #

def _score(variant: ComponentVariant) -> tuple[float, int]:
    """Exploit-sort key: (win_rate-or-prior, sample_size). Higher wins."""
    wr = variant.win_rate if variant.win_rate is not None else _NEUTRAL_WIN_RATE_PRIOR
    return (wr, variant.sample_size)


def _filter_ad_activity_variants(
    variants_by_type: dict[str, list[ComponentVariant]],
    has_ad_activity_enabled: bool,
) -> dict[str, list[ComponentVariant]]:
    """Drop variants that reference ``{{ad_activity_observation}}`` when the
    client hasn't enabled any ad-library directory. Copy-on-write: never
    mutates the caller's dict or lists."""
    if has_ad_activity_enabled:
        return {ct: list(variants or []) for ct, variants in variants_by_type.items()}
    return {
        ct: [
            v for v in (variants or [])
            if _AD_ACTIVITY_PLACEHOLDER not in (v.variant_content or "")
        ]
        for ct, variants in variants_by_type.items()
    }


def _render_ad_activity_observation(ad_activity: Any) -> str:
    """Render a one-sentence observation from contact.research_data.ad_activity.

    Returns empty string when ad_activity is absent, empty, or malformed.
    Expected shape:
        {"ad_count": int>0, "platforms": list[str] non-empty,
         "active_within_days": int | None (default 30), ...}
    """
    if not isinstance(ad_activity, dict):
        return ""
    ad_count = ad_activity.get("ad_count")
    if (
        not isinstance(ad_count, int)
        or isinstance(ad_count, bool)
        or ad_count <= 0
    ):
        return ""
    platforms = ad_activity.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        return ""
    platforms_str = _humanize_platforms(
        [p for p in platforms if isinstance(p, str) and p]
    )
    if not platforms_str:
        return ""
    window_raw = ad_activity.get("active_within_days")
    window = window_raw if isinstance(window_raw, int) and window_raw > 0 else 30
    return f"Running {ad_count} {platforms_str} ads over the last {window} days."


def _humanize_platforms(platforms: list[str]) -> str:
    """``['google', 'linkedin']`` -> ``'Google + LinkedIn'``. Dedup preserves
    first-seen order so scraper-output ordering survives."""
    labeled = [_PLATFORM_LABELS.get(p.lower(), p.title()) for p in platforms]
    seen: list[str] = []
    for p in labeled:
        if p and p not in seen:
            seen.append(p)
    return " + ".join(seen)


def _coalesce_first_name(raw: Any) -> str:
    """Fall back to ``'there'`` for missing / empty / non-string first_name."""
    if not isinstance(raw, str):
        return "there"
    stripped = raw.strip()
    return stripped or "there"


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _dedup_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
