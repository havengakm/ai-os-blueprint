"""Shared helpers for the Supabase backend implementations.

Each of the 8 backends in this package conforms to a Protocol defined in
``systems/scout/pipeline/`` or ``systems/scout/outreach/``. Helpers here
stay small and focused — anything backend-specific lives in that backend's
own module.
"""
from __future__ import annotations

from typing import Any, Protocol


class SupabaseLike(Protocol):
    """Minimal supabase.Client surface we depend on.

    Typed as a Protocol so tests can inject a FakeSupabaseClient without
    importing the real SDK. The real ``supabase.Client`` satisfies this
    structurally.
    """

    def table(self, name: str) -> Any: ...


def insert_decision_log_row(
    client: SupabaseLike,
    *,
    client_id: str,
    decision_type: str,
    decision: str,
    context: dict[str, Any],
    reasoning: str | None = None,
    confidence: float | None = None,
    source: str = "system",
) -> None:
    """Write one row to decision_log.

    All 8 backends emit decision-log entries with the same column shape.
    Centralising the insert keeps column naming consistent and means a
    future migration (e.g. a new column) touches one place.

    ``context`` is serialised as a plain dict — the Supabase client
    serialises to JSON over the wire. Callers are responsible for making
    it JSON-safe (lists/dicts/primitives only).
    """
    row = {
        "client_id": client_id,
        "decision_type": decision_type,
        "decision": decision,
        "context": context,
        "reasoning": reasoning,
        "source": source,
        "confidence": confidence,
    }
    client.table("decision_log").insert(row).execute()


def deep_merge_into(dest: dict[str, Any], patch: dict[str, Any]) -> None:
    """In-place deep merge of ``patch`` into ``dest``.

    Mirrors the semantics used by ``systems/scout/pipeline/enrich._deep_merge_into``
    but simplified for the read-modify-write path in
    ``SupabaseEnrichBackend.update_contact_enrich_data`` — we only need
    dict/list/scalar handling, not the typed-dedupe logic (the caller
    already ran that upstream before persisting).
    """
    for key, new_value in patch.items():
        if key in dest:
            old_value = dest[key]
            if isinstance(old_value, dict) and isinstance(new_value, dict):
                deep_merge_into(old_value, new_value)
                continue
            if isinstance(old_value, list) and isinstance(new_value, list):
                # Straight concatenation — caller handled dedupe in the stage layer.
                dest[key] = old_value + new_value
                continue
        dest[key] = new_value
