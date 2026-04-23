"""Enrich pipeline stage — orchestrator-plus-persistence layer.

Fetches contacts eligible for enrichment, dispatches each to
EnrichOrchestrator, merges every adapter's data into a single
``research_data_patch``, persists the patch, and returns a structured
summary for observability.

Standalone pipeline stage — NOT a BaseSystem subclass. BaseSystem wiring
is deferred to Task 16.5.

Pattern mirrors ``identity.py`` (waterfall-stage sibling), but the
semantics are fan-out: every tier-matching adapter contributes to the
merged patch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from systems.scout.enrich.icebreaker_adapter import IcebreakerAdapter
    from systems.scout.enrich.orchestrator import EnrichOrchestrator


# Final decision-type label for the enrich stage. Added to the
# decision_log.decision_type CHECK constraint by
# scripts/sql/005_foundation_completion.sql (Task 12.5). Mirrors
# ``_DECISION_TYPE`` in ``systems/scout/enrich/orchestrator.py``.
_DECISION_TYPE = "enrich_contact"

# Default archive floor — contacts below this icp_score are already
# archived by the screen/score stage and should never reach enrich.
_DEFAULT_ARCHIVE_FLOOR = 35


# --------------------------------------------------------------------------- #
# Data shapes                                                                   #
# --------------------------------------------------------------------------- #


@dataclass
class EnrichContactRow:
    """Minimal contact shape fetched from storage for enrichment."""

    contact_id: str
    icp_tier: str  # "A" / "B" / "C" / "D"
    email: str | None
    company: str
    company_domain: str | None
    linkedin_url: str | None
    industry: str | None
    existing_research_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class EnrichStageResult:
    """Aggregate result of an enrich-stage run."""

    client_id: str
    dry_run: bool
    total_eligible: int = 0
    total_enriched: int = 0
    total_errored: int = 0
    total_budget_paused: int = 0
    total_cost_cents: int = 0
    by_tier: dict[str, int] = field(
        default_factory=lambda: {"A": 0, "B": 0, "C": 0, "D": 0}
    )
    by_adapter_hit: dict[str, int] = field(default_factory=dict)
    by_adapter_skip: dict[str, int] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Storage protocol                                                              #
# --------------------------------------------------------------------------- #


class EnrichStorageBackend(Protocol):
    """Storage contract for the enrich stage.

    Kept deliberately small — Task 16 wraps a real Supabase client; tests
    use an in-memory fake.
    """

    async def get_eligible_contacts_for_enrich(
        self,
        client_id: str,
        *,
        archive_floor: int,
        limit: int | None = None,
    ) -> list[EnrichContactRow]:
        """Return contacts where:

        - ``icp_score >= archive_floor``
        - ``first_name IS NOT NULL`` (identity resolved)
        - ``status NOT IN ('archived', 'archived_no_decision_maker', 'killed')``
        - ``enriched_at IS NULL`` (not previously enriched this round)

        Caller-supplied limit caps batch size; ``None`` means no cap.
        """
        ...

    async def get_client_trigify_search_ids(self, client_id: str) -> list[str]:
        """Return ``client_config.trigify_search_ids`` for this client.

        Empty list when none configured — the Trigify adapter will skip
        with ``no_monitors_configured``. Called ONCE per stage run and
        attached to every contact dict.
        """
        ...

    async def update_contact_enrich_data(
        self,
        client_id: str,
        contact_id: str,
        *,
        research_data_patch: dict[str, Any],
        email_verified: bool | None,
        email_catch_all: bool | None,
        enriched_at_utc: str,
    ) -> None:
        """Merge ``research_data_patch`` into ``contacts.research_data``
        JSONB (deep merge: dict keys upsert, list values extend + dedupe
        on a composite key), set ``email_verified`` / ``email_catch_all``
        top-level columns, stamp ``enriched_at``.
        """
        ...

    async def log_decision(
        self,
        client_id: str,
        *,
        decision_type: str,
        decision: str,
        context: dict[str, Any],
        reasoning: str | None = None,
        confidence: float | None = None,
    ) -> None:
        """Append an entry to decision_log. Mirrors ``identity.py``."""
        ...


# --------------------------------------------------------------------------- #
# Stage                                                                         #
# --------------------------------------------------------------------------- #


class EnrichStage:
    """Fetches eligible contacts, fans out enrichment adapters via the
    orchestrator, merges results, persists the patch.

    Standalone orchestrator — no BaseSystem, no foundation loading
    (Task 16.5). Budget tracking is baked into the orchestrator at
    construction time, not re-injected here.
    """

    def __init__(
        self,
        orchestrator: "EnrichOrchestrator",
        storage: EnrichStorageBackend,
        *,
        archive_floor: int = _DEFAULT_ARCHIVE_FLOOR,
        icebreaker_adapter: "IcebreakerAdapter | None" = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._storage = storage
        self._archive_floor = archive_floor
        # Optional post-processor — runs AFTER the fan-out merge so it can
        # see both trigify and deep-research outputs. Clients that do not
        # want icebreakers simply omit this.
        self._icebreaker_adapter = icebreaker_adapter

    async def run(
        self,
        client_id: str,
        *,
        dry_run: bool = False,
        limit: int | None = None,
    ) -> EnrichStageResult:
        """Run the enrich stage.

        1. Fetch eligible contacts + trigify_search_ids (once per run).
        2. For each contact: build a contact dict, call
           ``orchestrator.enrich_contact(...)``, merge every adapter's
           ``data`` into a single patch, persist the patch unless dry_run.
        3. On persistence exception: increment total_errored, log
           ``persist_failed``, continue to the next contact.
        4. Track per-tier counts, per-adapter hit/skip counts, total cost,
           contacts paused by budget exhaustion.
        5. Always emit a final ``enrich_stage_summary`` decision_log entry
           (even on dry_run and even when every contact errored).
        """
        result = EnrichStageResult(client_id=client_id, dry_run=dry_run)

        contacts = await self._storage.get_eligible_contacts_for_enrich(
            client_id,
            archive_floor=self._archive_floor,
            limit=limit,
        )
        result.total_eligible = len(contacts)

        trigify_search_ids = await self._storage.get_client_trigify_search_ids(client_id)

        for contact in contacts:
            contact_dict = _build_contact_dict(contact, trigify_search_ids)

            orc_result = await self._orchestrator.enrich_contact(
                client_id,
                contact_dict,
                contact.icp_tier,
                dry_run=dry_run,
            )

            # Cost + budget + tier counters (always update).
            result.total_cost_cents += orc_result.total_cost_cents
            if contact.icp_tier in result.by_tier:
                result.by_tier[contact.icp_tier] += 1
            if orc_result.budget_exhausted:
                result.total_budget_paused += 1

            # Per-adapter hit/skip counters.
            for adapter_name, adapter_result in orc_result.adapter_results.items():
                if adapter_result.ok:
                    result.by_adapter_hit[adapter_name] = (
                        result.by_adapter_hit.get(adapter_name, 0) + 1
                    )
            for adapter_name in orc_result.skipped:
                result.by_adapter_skip[adapter_name] = (
                    result.by_adapter_skip.get(adapter_name, 0) + 1
                )

            # Merge every adapter's data into one patch.
            merged = _merge_adapter_data(orc_result.adapter_results)

            # Stage-level post-processor: icebreaker generator. Runs AFTER
            # the merge so it can read trigger_events (trigify) AND
            # structural_signals / citable_details (deep research) in one
            # pass. Injected only when the client wants icebreakers — a
            # missing adapter is a no-op, not an error.
            if self._icebreaker_adapter is not None:
                ib_result = await self._icebreaker_adapter.generate(
                    contact=contact_dict,
                    merged_research_data=merged,
                    client_id=client_id,
                    tier_budget=contact.icp_tier,
                    dry_run=dry_run,
                )
                result.total_cost_cents += ib_result.cost_cents
                if ib_result.ok and ib_result.icebreaker_content:
                    merged["icebreaker_content"] = ib_result.icebreaker_content
                    merged["icebreaker_tier"] = ib_result.tier
                    result.by_adapter_hit["icebreaker"] = (
                        result.by_adapter_hit.get("icebreaker", 0) + 1
                    )
                else:
                    result.by_adapter_skip["icebreaker"] = (
                        result.by_adapter_skip.get("icebreaker", 0) + 1
                    )

            # Lift email_verified / email_catch_all OUT of the patch onto
            # top-level columns. Missing keys → None (storage can treat
            # None as "no update").
            email_verified = merged.pop("email_verified", None)
            email_catch_all = merged.pop("email_catch_all", None)

            # "Usefully enriched" = at least one adapter returned ok AND
            # produced non-empty data.
            enriched = any(
                r.ok and bool(r.data) for r in orc_result.adapter_results.values()
            )
            if enriched:
                result.total_enriched += 1

            if dry_run:
                continue

            # Persist. Failures never abort the loop.
            try:
                await self._storage.update_contact_enrich_data(
                    client_id,
                    contact.contact_id,
                    research_data_patch=merged,
                    email_verified=email_verified,
                    email_catch_all=email_catch_all,
                    enriched_at_utc=_utc_now_iso(),
                )
            except Exception as exc:
                await self._log_persist_failure(client_id, contact.contact_id, exc)
                result.total_errored += 1

        await self._log_summary(client_id, result)
        return result

    async def _log_summary(
        self, client_id: str, result: EnrichStageResult
    ) -> None:
        """Emit the final stage-summary decision. Never raises."""
        try:
            await self._storage.log_decision(
                client_id,
                decision_type=_DECISION_TYPE,
                decision="enrich_stage_summary",
                reasoning=(
                    f"Processed {result.total_eligible} contacts: "
                    f"{result.total_enriched} enriched, "
                    f"{result.total_errored} errored, "
                    f"{result.total_budget_paused} paused by budget, "
                    f"{result.total_cost_cents}c total spend"
                ),
                context={
                    "client_id": client_id,
                    "dry_run": result.dry_run,
                    "total_eligible": result.total_eligible,
                    "total_enriched": result.total_enriched,
                    "total_errored": result.total_errored,
                    "total_budget_paused": result.total_budget_paused,
                    "total_cost_cents": result.total_cost_cents,
                    "by_tier": result.by_tier,
                    "by_adapter_hit": result.by_adapter_hit,
                    "by_adapter_skip": result.by_adapter_skip,
                },
                confidence=None,
            )
        except Exception:
            pass  # summary logging must never propagate

    async def _log_persist_failure(
        self,
        client_id: str,
        contact_id: str,
        exc: Exception,
    ) -> None:
        """Log a per-contact persistence failure. Never raises."""
        reasoning = f"{type(exc).__name__}: {exc}"[:500]
        try:
            await self._storage.log_decision(
                client_id,
                decision_type=_DECISION_TYPE,
                decision=f"enrich_stage:persist_failed:{contact_id}",
                reasoning=reasoning,
                context={"contact_id": contact_id},
            )
        except Exception:
            pass  # logging must never propagate


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #


def _build_contact_dict(
    row: EnrichContactRow,
    trigify_search_ids: list[str],
) -> dict[str, Any]:
    """Translate an EnrichContactRow into the dict shape the orchestrator
    (and its adapters) expect.

    Apollo writes ``company_revenue_usd`` / ``company_employees`` /
    ``company_founded_year`` into ``research_data``; the already_complete
    guard on ``apollo_enrich`` looks at bare ``revenue_usd`` / ``employees``
    / ``founded_year`` keys, so we map ``company_*`` → bare at the stage
    boundary.
    """
    existing = row.existing_research_data or {}
    return {
        "contact_id": row.contact_id,
        "email": row.email,
        "company": row.company,
        "company_domain": row.company_domain,
        "linkedin_url": row.linkedin_url,
        "industry": row.industry,
        "trigify_search_ids": trigify_search_ids,
        # apollo_enrich already_complete guard
        "revenue_usd": existing.get("company_revenue_usd"),
        "employees": existing.get("company_employees"),
        "founded_year": existing.get("company_founded_year"),
    }


def _merge_adapter_data(
    adapter_results: dict[str, Any],
) -> dict[str, Any]:
    """Merge every successful adapter's ``data`` dict into one patch.

    Order matters — ``adapter_results`` is insertion-ordered and reflects
    the tier adapter order from the orchestrator. Later adapters
    overwrite scalars from earlier ones; lists extend + dedupe; dicts
    deep-merge.

    Only adapters with ``ok=True`` contribute (a failed call's data is
    ignored even if non-empty, matching the orchestrator's "check
    reason before using data" contract).
    """
    merged: dict[str, Any] = {}
    for adapter_result in adapter_results.values():
        if not adapter_result.ok:
            continue
        _deep_merge_into(merged, adapter_result.data or {})
    return merged


def _deep_merge_into(dest: dict[str, Any], patch: dict[str, Any]) -> None:
    """In-place deep merge of ``patch`` into ``dest``.

    - If both sides have a dict for a key → recurse.
    - If both sides have a list → extend + dedupe (see _extend_dedupe).
    - Otherwise → ``patch`` overwrites ``dest``.
    """
    for key, new_value in patch.items():
        if key in dest:
            old_value = dest[key]
            if isinstance(old_value, dict) and isinstance(new_value, dict):
                _deep_merge_into(old_value, new_value)
                continue
            if isinstance(old_value, list) and isinstance(new_value, list):
                dest[key] = _extend_dedupe(old_value, new_value)
                continue
        dest[key] = new_value


def _extend_dedupe(left: list[Any], right: list[Any]) -> list[Any]:
    """Concatenate two lists while deduping.

    Dedupe key:
    - For dicts: composite of ``type`` + ``detail`` when both are present,
      falling back to the frozen dict (best-effort hashable) otherwise.
    - For other hashable items: the item itself.
    - Unhashable items: appended unconditionally (best-effort — keeps the
      merge non-lossy at the cost of occasional duplicates).
    """
    out: list[Any] = []
    seen: set[Any] = set()
    for item in list(left) + list(right):
        key = _dedupe_key(item)
        if key is _UNHASHABLE:
            out.append(item)
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


_UNHASHABLE = object()


def _dedupe_key(item: Any) -> Any:
    """Best-effort hashable key for an item in a list being deduped."""
    if isinstance(item, dict):
        if "type" in item and "detail" in item:
            return ("__typed__", item["type"], item["detail"])
        try:
            return ("__frozen__", tuple(sorted(item.items())))
        except TypeError:
            return _UNHASHABLE
    try:
        hash(item)
    except TypeError:
        return _UNHASHABLE
    return item


def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp for ``enriched_at``.

    Factored into a tiny helper so tests that need a deterministic
    timestamp can monkeypatch it.
    """
    from datetime import datetime, timezone

    return datetime.now(tz=timezone.utc).isoformat()
