"""Component registry loader — YAML -> component_variants table sync.

Syncs operator-authored component variant YAMLs from
``data/reference/sequences/{niche}/components/{component_type}/*.yaml``
into the ``component_variants`` table. Preserves learned statistics
(``win_rate`` + ``sample_size``) across updates: the loader never sends
those columns in an update payload, so operator-edited content/metadata
can ship without clobbering Plan 2's attribution data.

Canonical per-document YAML shape:

    ---
    variant_key: "agency_growth_hook_v1"
    component_type: "icebreaker"        # must match parent folder name
    niche: "cro_growth_ugc_agency"      # must match grandparent folder
    offer_label: "pipeline_audit"
    variant_content: |
      Noticed you've been running {{ad_activity_observation}} ...
    status: "draft"                     # draft | approved | paused | killed
    metadata:
      author: "Kirsten"
      notes: "Anchored to Sapp 6-step close step 2"
    ab_epsilon: 0.1                     # optional; defaults to 0.1

Multi-document files (separated by ``---``) are supported; each document
becomes one variant.

The loader separates pure disk->object parsing (``discover_variants``)
from storage (``sync``). Tests inject an in-memory
:class:`ComponentStoreBackend`; production wires to Supabase in Task 16.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml


# --------------------------------------------------------------------------- #
# Constants                                                                     #
# --------------------------------------------------------------------------- #

VALID_COMPONENT_TYPES: frozenset[str] = frozenset({
    "subject_line", "icebreaker", "pain_hook",
    "offer_frame", "cta", "signature",
})

VALID_STATUSES: frozenset[str] = frozenset({
    "draft", "approved", "paused", "killed",
})

_VARIANT_KEY_RE = re.compile(r"^[a-z0-9_]+$")
_MAX_VARIANT_KEY_LEN = 128

# The unique-constraint tuple used to key a variant in the DB and in
# ``ComponentStoreBackend.fetch_existing``.
VariantKeyTuple = tuple[str, str, str, str]  # (component_type, variant_key, niche, offer_label)


# --------------------------------------------------------------------------- #
# Data shapes                                                                   #
# --------------------------------------------------------------------------- #

@dataclass
class ComponentVariant:
    """One parsed variant, ready to upsert.

    ``source_path`` is kept for operator error-reporting and is NOT
    persisted to the DB.
    """

    variant_key: str
    component_type: str
    niche: str
    offer_label: str
    variant_content: str
    status: str = "draft"
    metadata: dict[str, Any] = field(default_factory=dict)
    ab_epsilon: float = 0.1
    source_path: str = ""


@dataclass
class SyncSummary:
    """Outcome of a ``ComponentStore.sync`` run.

    - ``loaded``: YAML documents that parsed and validated OK.
    - ``inserted`` / ``updated`` / ``unchanged``: disposition of each
      loaded variant vs existing DB state.
    - ``skipped``: YAML documents that failed validation (see ``errors``).
    - ``errors``: human-readable per-file failure messages, prefixed with
      the source path.
    """

    loaded: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class ComponentStoreBackend(Protocol):
    """Storage contract — tests inject an in-memory fake; production
    wires to Supabase in Task 16."""

    async def fetch_existing(
        self,
        client_id: str,
        keys: list[VariantKeyTuple],
    ) -> dict[VariantKeyTuple, dict[str, Any]]:
        """Return existing rows keyed by the unique-constraint tuple.

        Values MUST include ``id``, ``variant_content``, ``status``,
        ``metadata``, ``ab_epsilon``; MAY include ``win_rate`` and
        ``sample_size``. Rows not found are simply absent from the result.
        """
        ...

    async def insert_variants(
        self,
        client_id: str,
        variants: list[ComponentVariant],
    ) -> None:
        """Insert new component variants. The backend is responsible for
        setting ``win_rate = NULL`` and ``sample_size = 0`` on new rows
        (the DB defaults already enforce this)."""
        ...

    async def update_variants(
        self,
        client_id: str,
        updates: list[tuple[str, ComponentVariant]],
    ) -> None:
        """Update ``variant_content`` / ``status`` / ``metadata`` /
        ``ab_epsilon`` on existing rows keyed by ``id``.

        The backend MUST NOT touch ``win_rate`` or ``sample_size`` —
        those are populated by Plan 2's cohort evaluator and overwriting
        them from a YAML re-sync would destroy attribution data.
        """
        ...


# --------------------------------------------------------------------------- #
# Component store                                                               #
# --------------------------------------------------------------------------- #

class ComponentStore:
    """Syncs component variant YAMLs -> ``component_variants`` table."""

    def __init__(
        self,
        backend: ComponentStoreBackend,
        sequences_root: Path,
    ) -> None:
        self._backend = backend
        self._root = sequences_root

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    async def sync(self, client_id: str) -> SyncSummary:
        """Discover + parse + validate YAMLs; upsert via the backend.

        Per-document validation errors are recorded on the summary and
        do NOT abort the run — one bad YAML never blocks a 200-variant
        refresh.
        """
        summary = SyncSummary()

        if not self._root.exists():
            # Missing directory is NOT an error. Operators may run sync
            # before authoring any sequences; return a clean summary.
            return summary

        variants = self._discover_and_parse(summary)
        if not variants:
            return summary

        summary.loaded = len(variants)

        # Fetch existing rows to decide insert-vs-update for each variant.
        keys: list[VariantKeyTuple] = [
            (v.component_type, v.variant_key, v.niche, v.offer_label)
            for v in variants
        ]
        existing = await self._backend.fetch_existing(client_id, keys)

        to_insert: list[ComponentVariant] = []
        to_update: list[tuple[str, ComponentVariant]] = []

        for variant in variants:
            key = (
                variant.component_type, variant.variant_key,
                variant.niche, variant.offer_label,
            )
            existing_row = existing.get(key)
            if existing_row is None:
                to_insert.append(variant)
                summary.inserted += 1
            elif _has_changed(variant, existing_row):
                to_update.append((existing_row["id"], variant))
                summary.updated += 1
            else:
                summary.unchanged += 1

        if to_insert:
            await self._backend.insert_variants(client_id, to_insert)
        if to_update:
            await self._backend.update_variants(client_id, to_update)

        return summary

    # ------------------------------------------------------------------ #
    # Internals                                                           #
    # ------------------------------------------------------------------ #

    def _discover_and_parse(self, summary: SyncSummary) -> list[ComponentVariant]:
        """Walk ``{root}/{niche}/components/{component_type}/*.yaml`` and
        return validated variants. Bad documents are recorded on
        ``summary.errors`` and skipped.
        """
        results: list[ComponentVariant] = []

        # We walk the tree ourselves (rather than ``root.glob(...)``) so
        # we can bind each YAML to its expected path-encoded niche + type
        # before parsing. Sorting gives deterministic order for tests.
        for niche_dir in sorted(self._root.iterdir()):
            if not niche_dir.is_dir():
                continue
            components_dir = niche_dir / "components"
            if not components_dir.is_dir():
                continue
            for type_dir in sorted(components_dir.iterdir()):
                if not type_dir.is_dir():
                    continue
                for yaml_path in sorted(type_dir.glob("*.yaml")):
                    self._load_file(
                        yaml_path,
                        expected_niche=niche_dir.name,
                        expected_component_type=type_dir.name,
                        summary=summary,
                        out=results,
                    )

        return results

    def _load_file(
        self,
        path: Path,
        *,
        expected_niche: str,
        expected_component_type: str,
        summary: SyncSummary,
        out: list[ComponentVariant],
    ) -> None:
        """Parse one YAML file (possibly multi-document) and append valid
        variants to ``out``. Failures append to ``summary.errors``.
        """
        try:
            raw = path.read_text(encoding="utf-8")
            docs = list(yaml.safe_load_all(raw))
        except (OSError, yaml.YAMLError) as exc:
            summary.skipped += 1
            summary.errors.append(f"{path}: YAML parse error: {exc}")
            return

        docs = [d for d in docs if d is not None]
        if not docs:
            summary.skipped += 1
            summary.errors.append(f"{path}: empty YAML file")
            return

        for doc in docs:
            try:
                variant = _parse_document(
                    doc,
                    source=path,
                    expected_niche=expected_niche,
                    expected_component_type=expected_component_type,
                )
            except ValueError as exc:
                summary.skipped += 1
                summary.errors.append(str(exc))
                continue
            out.append(variant)


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _parse_document(
    doc: Any,
    *,
    source: Path,
    expected_niche: str,
    expected_component_type: str,
) -> ComponentVariant:
    """Validate one parsed YAML document and return a ``ComponentVariant``.

    Raises ``ValueError`` with a ``{source}: <msg>`` prefix on any
    validation failure.
    """
    if not isinstance(doc, dict):
        raise ValueError(f"{source}: expected a mapping at document root")

    required = (
        "variant_key", "component_type", "niche",
        "offer_label", "variant_content",
    )
    missing = [k for k in required if k not in doc]
    if missing:
        raise ValueError(f"{source}: missing required fields: {missing}")

    variant_key = doc["variant_key"]
    if not isinstance(variant_key, str) or not variant_key:
        raise ValueError(f"{source}: variant_key must be a non-empty string")
    if len(variant_key) > _MAX_VARIANT_KEY_LEN:
        raise ValueError(
            f"{source}: variant_key '{variant_key}' exceeds "
            f"{_MAX_VARIANT_KEY_LEN} chars"
        )
    if not _VARIANT_KEY_RE.match(variant_key):
        raise ValueError(
            f"{source}: variant_key '{variant_key}' must be snake_case "
            f"(lowercase letters, digits, underscore)"
        )

    component_type = doc["component_type"]
    if component_type not in VALID_COMPONENT_TYPES:
        raise ValueError(
            f"{source}: component_type '{component_type}' not in "
            f"{sorted(VALID_COMPONENT_TYPES)}"
        )
    if component_type != expected_component_type:
        raise ValueError(
            f"{source}: component_type '{component_type}' does not match "
            f"parent folder '{expected_component_type}'"
        )

    niche = doc["niche"]
    if not isinstance(niche, str) or not niche:
        raise ValueError(f"{source}: niche must be a non-empty string")
    if niche != expected_niche:
        raise ValueError(
            f"{source}: niche '{niche}' does not match parent folder "
            f"'{expected_niche}'"
        )

    offer_label = doc["offer_label"]
    if not isinstance(offer_label, str) or not offer_label:
        raise ValueError(f"{source}: offer_label must be a non-empty string")

    variant_content = doc["variant_content"]
    if not isinstance(variant_content, str) or not variant_content.strip():
        raise ValueError(f"{source}: variant_content must be a non-empty string")

    status = doc.get("status", "draft")
    if status not in VALID_STATUSES:
        raise ValueError(
            f"{source}: status '{status}' not in {sorted(VALID_STATUSES)}"
        )

    metadata = doc.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError(f"{source}: metadata must be a mapping")

    ab_epsilon_raw = doc.get("ab_epsilon", 0.1)
    if isinstance(ab_epsilon_raw, bool) or not isinstance(ab_epsilon_raw, (int, float)):
        raise ValueError(f"{source}: ab_epsilon must be a number in [0, 1]")
    ab_epsilon = float(ab_epsilon_raw)
    if not 0.0 <= ab_epsilon <= 1.0:
        raise ValueError(f"{source}: ab_epsilon {ab_epsilon} must be in [0, 1]")

    return ComponentVariant(
        variant_key=variant_key,
        component_type=component_type,
        niche=niche,
        offer_label=offer_label,
        variant_content=variant_content,
        status=status,
        metadata=metadata,
        ab_epsilon=ab_epsilon,
        source_path=str(source),
    )


def _has_changed(new: ComponentVariant, existing: dict[str, Any]) -> bool:
    """True if ``variant_content``, ``status``, ``metadata``, or
    ``ab_epsilon`` differ from the DB row.

    Deliberately does NOT compare:
      - ``niche`` / ``offer_label`` / ``component_type`` / ``variant_key``
        — these are part of the UNIQUE key, so a different value would
        resolve to a different row (insert), not an update.
      - ``win_rate`` / ``sample_size`` — populated by Plan 2's cohort
        evaluator; preserving them across updates is the whole point
        of this split.

    ``metadata`` uses dict equality (recursive), so two dicts with the
    same keys in different insertion order count as equal.
    """
    if new.variant_content != existing.get("variant_content"):
        return True
    if new.status != existing.get("status"):
        return True
    if new.metadata != existing.get("metadata"):
        return True
    # Tolerate int/float representation drift (DB may return Decimal-ish
    # values depending on driver).
    existing_epsilon = existing.get("ab_epsilon")
    if existing_epsilon is None or float(existing_epsilon) != new.ab_epsilon:
        return True
    return False
