"""SupabaseComponentStoreBackend — real persistence for the YAML loader.

Conforms to ``systems.scout.outreach.component_store.ComponentStoreBackend``.

Item-62 gate lives here.  The ``update_variants`` method MUST build its
UPDATE SET clause from an explicit allow-list of columns — NEVER from a
generic dataclass iterator — so YAML re-syncs can never clobber Plan 2's
learned statistics (``win_rate`` + ``sample_size``).
"""
from __future__ import annotations

from typing import Any

from systems.scout.outreach.component_store import (
    ComponentVariant,
    VariantKeyTuple,
)
from systems.scout.supabase_backends._base import SupabaseLike


class SupabaseComponentStoreBackend:
    """Real Supabase-backed implementation of ComponentStoreBackend.

    ──────────────────────────────────────────────────────────────────
    Item-62 gate (Task 15 review, ratified by Task 16b Step 1):
    ``update_variants`` is the only sync-path mutation of
    ``component_variants``. It MUST only write to the columns in
    ``_UPDATABLE_COLUMNS``. ``win_rate`` and ``sample_size`` are
    populated by Plan 2's cohort evaluator and are the learned state
    the bandit uses — overwriting them from a YAML re-sync would
    destroy attribution data.
    ──────────────────────────────────────────────────────────────────
    """

    #: Allowed SET-clause columns on the update path. Class-level
    #: frozenset (not a mutable list inside the method) so accidental
    #: mutation during a run is impossible.
    _UPDATABLE_COLUMNS: frozenset[str] = frozenset({
        "variant_content", "status", "metadata", "ab_epsilon",
    })

    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def fetch_existing(
        self,
        client_id: str,
        keys: list[VariantKeyTuple],
    ) -> dict[VariantKeyTuple, dict[str, Any]]:
        """Return existing rows keyed by the unique-constraint tuple.

        Fetches ALL rows for (client_id, niche, offer_label) present in
        the key list, then filters by (component_type, variant_key) in
        Python. One request per unique (niche, offer_label) pair.
        """
        if not keys:
            return {}

        # Group lookups by (niche, offer_label) to minimise round-trips.
        by_pair: dict[tuple[str, str], list[VariantKeyTuple]] = {}
        for key in keys:
            _component_type, _variant_key, niche, offer_label = key
            by_pair.setdefault((niche, offer_label), []).append(key)

        out: dict[VariantKeyTuple, dict[str, Any]] = {}
        for (niche, offer_label), group_keys in by_pair.items():
            resp = (
                self._client.table("component_variants")
                .select(
                    "id, component_type, variant_key, niche, offer_label, "
                    "variant_content, status, metadata, ab_epsilon, "
                    "win_rate, sample_size"
                )
                .eq("client_id", client_id)
                .eq("niche", niche)
                .eq("offer_label", offer_label)
                .execute()
            )
            wanted = {(k[0], k[1]) for k in group_keys}
            for row in resp.data or []:
                row_key = (row["component_type"], row["variant_key"])
                if row_key not in wanted:
                    continue
                out[
                    (
                        row["component_type"],
                        row["variant_key"],
                        row["niche"],
                        row["offer_label"],
                    )
                ] = row
        return out

    async def insert_variants(
        self,
        client_id: str,
        variants: list[ComponentVariant],
    ) -> None:
        """Insert new component_variant rows.

        Does NOT send ``win_rate`` / ``sample_size`` — the DB defaults
        (``NULL`` and ``0`` respectively) apply.
        """
        if not variants:
            return
        rows = [
            {
                "client_id": client_id,
                "component_type": v.component_type,
                "variant_key": v.variant_key,
                "niche": v.niche,
                "offer_label": v.offer_label,
                "variant_content": v.variant_content,
                "status": v.status,
                "metadata": v.metadata,
                "ab_epsilon": v.ab_epsilon,
            }
            for v in variants
        ]
        self._client.table("component_variants").insert(rows).execute()

    async def update_variants(
        self,
        client_id: str,
        updates: list[tuple[str, ComponentVariant]],
    ) -> None:
        """Update existing component_variant rows by id.

        ITEM-62 GATE: payload is built from an explicit allow-list of
        four columns. The runtime assertion is defence-in-depth — if a
        future edit accidentally adds a key outside the allow-list, the
        assert fires in tests long before any Plan 2 attribution data
        can be clobbered in production.
        """
        for variant_id, variant in updates:
            payload = {
                "variant_content": variant.variant_content,
                "status": variant.status,
                "metadata": variant.metadata,
                "ab_epsilon": variant.ab_epsilon,
            }
            # Defence in depth. Must hold for every update, every row.
            extra = set(payload.keys()) - self._UPDATABLE_COLUMNS
            assert not extra, (
                f"SupabaseComponentStoreBackend.update_variants tried to "
                f"set disallowed columns: {sorted(extra)}. "
                f"Only {sorted(self._UPDATABLE_COLUMNS)} are allowed "
                f"(item-62 gate preserves learned win_rate/sample_size)."
            )

            (
                self._client.table("component_variants")
                .update(payload)
                .eq("id", variant_id)
                .execute()
            )
