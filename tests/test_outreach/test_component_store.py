"""Tests for ComponentStore — YAML discovery, validation, sync semantics.

The fake backend mimics the Supabase unique-key contract: it stores rows
keyed by (client_id, component_type, variant_key, niche, offer_label)
and records every insert/update call so the tests can assert the exact
payload shape.
"""
from __future__ import annotations

import textwrap
import uuid
from pathlib import Path
from typing import Any

import pytest

from systems.scout.outreach.component_store import (
    ComponentStore,
    ComponentStoreBackend,
    ComponentVariant,
    SyncSummary,
    VariantKeyTuple,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

_BASELINE_YAML = textwrap.dedent(
    """\
    ---
    variant_key: "v1_happy_path"
    component_type: "icebreaker"
    niche: "cro_growth_ugc_agency"
    offer_label: "pipeline_audit"
    variant_content: |
      Hello {{first_name}}, noticed {{observation}}.
    status: "draft"
    metadata:
      author: "Test"
    ab_epsilon: 0.1
    """
)


def _write(path: Path, body: str) -> None:
    """Write ``body`` to ``path``, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _variant_path(
    root: Path,
    niche: str,
    component_type: str,
    filename: str,
) -> Path:
    return root / niche / "components" / component_type / filename


def _write_variant(
    root: Path,
    *,
    niche: str = "cro_growth_ugc_agency",
    component_type: str = "icebreaker",
    variant_key: str = "v1_default",
    offer_label: str = "pipeline_audit",
    content: str = "Hello {{first_name}}.",
    status: str = "draft",
    metadata: dict[str, Any] | None = None,
    ab_epsilon: float = 0.1,
    filename: str | None = None,
) -> Path:
    """Write one YAML variant under the proper path layout and return
    the resulting path."""
    md_block = ""
    if metadata:
        import json
        md_block = f"metadata: {json.dumps(metadata)}\n"
    else:
        md_block = "metadata: {}\n"

    body = textwrap.dedent(
        f"""\
        variant_key: "{variant_key}"
        component_type: "{component_type}"
        niche: "{niche}"
        offer_label: "{offer_label}"
        variant_content: |
          {content}
        status: "{status}"
        ab_epsilon: {ab_epsilon}
        """
    ) + md_block
    path = _variant_path(
        root, niche, component_type, filename or f"{variant_key}.yaml",
    )
    _write(path, body)
    return path


# --------------------------------------------------------------------------- #
# Fake backend                                                                 #
# --------------------------------------------------------------------------- #

class FakeBackend:
    """In-memory ComponentStoreBackend.

    Seed existing rows with :meth:`seed_row`. Inspect the call log via
    ``insert_calls`` / ``update_calls`` — each is a list of (client_id,
    variants-or-updates) tuples matching what ``sync()`` passed us.
    """

    def __init__(self) -> None:
        # Keyed (client_id, component_type, variant_key, niche, offer_label)
        # -> row dict (mirrors the DB schema columns the loader cares about).
        self._rows: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
        self.insert_calls: list[tuple[str, list[ComponentVariant]]] = []
        self.update_calls: list[tuple[str, list[tuple[str, ComponentVariant]]]] = []

    # -- seeding helpers ------------------------------------------------- #
    def seed_row(
        self,
        client_id: str,
        *,
        component_type: str,
        variant_key: str,
        niche: str,
        offer_label: str,
        variant_content: str,
        status: str = "draft",
        metadata: dict[str, Any] | None = None,
        ab_epsilon: float = 0.1,
        win_rate: float | None = None,
        sample_size: int = 0,
    ) -> str:
        row_id = str(uuid.uuid4())
        full_key = (client_id, component_type, variant_key, niche, offer_label)
        self._rows[full_key] = {
            "id": row_id,
            "variant_content": variant_content,
            "status": status,
            "metadata": metadata if metadata is not None else {},
            "ab_epsilon": ab_epsilon,
            "win_rate": win_rate,
            "sample_size": sample_size,
        }
        return row_id

    def get_row(
        self,
        client_id: str,
        component_type: str,
        variant_key: str,
        niche: str,
        offer_label: str,
    ) -> dict[str, Any] | None:
        return self._rows.get(
            (client_id, component_type, variant_key, niche, offer_label)
        )

    # -- ComponentStoreBackend impl -------------------------------------- #
    async def fetch_existing(
        self,
        client_id: str,
        keys: list[VariantKeyTuple],
    ) -> dict[VariantKeyTuple, dict[str, Any]]:
        out: dict[VariantKeyTuple, dict[str, Any]] = {}
        for key in keys:
            full_key = (client_id,) + key
            row = self._rows.get(full_key)
            if row is not None:
                out[key] = dict(row)  # return a copy so caller can't mutate us
        return out

    async def insert_variants(
        self,
        client_id: str,
        variants: list[ComponentVariant],
    ) -> None:
        self.insert_calls.append((client_id, list(variants)))
        for v in variants:
            full_key = (client_id, v.component_type, v.variant_key, v.niche, v.offer_label)
            self._rows[full_key] = {
                "id": str(uuid.uuid4()),
                "variant_content": v.variant_content,
                "status": v.status,
                "metadata": dict(v.metadata),
                "ab_epsilon": v.ab_epsilon,
                "win_rate": None,
                "sample_size": 0,
            }

    async def update_variants(
        self,
        client_id: str,
        updates: list[tuple[str, ComponentVariant]],
    ) -> None:
        self.update_calls.append((client_id, list(updates)))
        # Mutate the stored rows so subsequent fetch_existing returns the
        # updated content (simulates the Supabase side of the world).
        for row_id, v in updates:
            for full_key, row in self._rows.items():
                if row["id"] == row_id:
                    row["variant_content"] = v.variant_content
                    row["status"] = v.status
                    row["metadata"] = dict(v.metadata)
                    row["ab_epsilon"] = v.ab_epsilon
                    # Deliberately DO NOT touch win_rate / sample_size.
                    break


# --------------------------------------------------------------------------- #
# 1. Missing root                                                              #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_sync_missing_root_returns_empty_summary(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    store = ComponentStore(backend=FakeBackend(), sequences_root=missing)

    summary = await store.sync(client_id="c1")

    assert summary == SyncSummary()
    assert summary.loaded == 0
    assert summary.errors == []


# --------------------------------------------------------------------------- #
# 2. Empty root                                                                #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_sync_empty_root_returns_empty_summary(tmp_path: Path) -> None:
    # tmp_path exists but has no sequences in it.
    backend = FakeBackend()
    store = ComponentStore(backend=backend, sequences_root=tmp_path)

    summary = await store.sync(client_id="c1")

    assert summary.loaded == 0
    assert summary.inserted == 0
    assert summary.errors == []
    assert backend.insert_calls == []
    assert backend.update_calls == []


# --------------------------------------------------------------------------- #
# 3. Happy path — insert 3 new variants                                        #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_sync_inserts_three_new_variants(tmp_path: Path) -> None:
    _write_variant(tmp_path, component_type="subject_line", variant_key="subj_v1")
    _write_variant(tmp_path, component_type="icebreaker",   variant_key="ice_v1")
    _write_variant(tmp_path, component_type="cta",          variant_key="cta_v1")

    backend = FakeBackend()
    store = ComponentStore(backend=backend, sequences_root=tmp_path)

    summary = await store.sync(client_id="c1")

    assert summary.loaded == 3
    assert summary.inserted == 3
    assert summary.updated == 0
    assert summary.unchanged == 0
    assert summary.skipped == 0
    assert summary.errors == []

    assert len(backend.insert_calls) == 1
    client_id, variants = backend.insert_calls[0]
    assert client_id == "c1"
    assert {v.variant_key for v in variants} == {"subj_v1", "ice_v1", "cta_v1"}
    assert backend.update_calls == []


# --------------------------------------------------------------------------- #
# 4. Happy path — update on content change                                     #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_sync_updates_changed_content(tmp_path: Path) -> None:
    backend = FakeBackend()
    backend.seed_row(
        "c1",
        component_type="icebreaker",
        variant_key="ice_v1",
        niche="cro_growth_ugc_agency",
        offer_label="pipeline_audit",
        variant_content="OLD CONTENT",
        status="draft",
        metadata={"author": "Test"},
        ab_epsilon=0.1,
    )

    _write_variant(
        tmp_path,
        component_type="icebreaker",
        variant_key="ice_v1",
        content="NEW CONTENT",
        metadata={"author": "Test"},
    )

    store = ComponentStore(backend=backend, sequences_root=tmp_path)
    summary = await store.sync(client_id="c1")

    assert summary.loaded == 1
    assert summary.updated == 1
    assert summary.inserted == 0
    assert summary.unchanged == 0
    assert backend.insert_calls == []
    assert len(backend.update_calls) == 1
    _, updates = backend.update_calls[0]
    assert len(updates) == 1
    row_id, payload = updates[0]
    assert "NEW CONTENT" in payload.variant_content


# --------------------------------------------------------------------------- #
# 5. Unchanged — no-op                                                         #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_sync_unchanged_is_noop(tmp_path: Path) -> None:
    content = "Hello {{first_name}}."
    metadata = {"author": "Test"}

    backend = FakeBackend()
    backend.seed_row(
        "c1",
        component_type="icebreaker",
        variant_key="ice_v1",
        niche="cro_growth_ugc_agency",
        offer_label="pipeline_audit",
        variant_content=content + "\n",  # YAML block-scalar adds a trailing newline
        status="draft",
        metadata=metadata,
        ab_epsilon=0.1,
    )

    _write_variant(
        tmp_path,
        component_type="icebreaker",
        variant_key="ice_v1",
        content=content,
        metadata=metadata,
    )

    store = ComponentStore(backend=backend, sequences_root=tmp_path)
    summary = await store.sync(client_id="c1")

    assert summary.loaded == 1
    assert summary.unchanged == 1
    assert summary.updated == 0
    assert summary.inserted == 0
    assert backend.insert_calls == []
    assert backend.update_calls == []


# --------------------------------------------------------------------------- #
# 6. Invalid YAML syntax                                                       #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_sync_skips_malformed_yaml(tmp_path: Path) -> None:
    path = _variant_path(
        tmp_path, "cro_growth_ugc_agency", "icebreaker", "broken.yaml",
    )
    _write(path, "variant_key: [this is not valid\n  yaml at all:")

    store = ComponentStore(backend=FakeBackend(), sequences_root=tmp_path)
    summary = await store.sync(client_id="c1")

    assert summary.loaded == 0
    assert summary.skipped == 1
    assert len(summary.errors) == 1
    assert str(path) in summary.errors[0]


# --------------------------------------------------------------------------- #
# 7. Missing required field                                                    #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_sync_skips_missing_required_field(tmp_path: Path) -> None:
    # Drop variant_key from the baseline.
    body = _BASELINE_YAML.replace('variant_key: "v1_happy_path"\n', "")
    _write(
        _variant_path(tmp_path, "cro_growth_ugc_agency", "icebreaker", "bad.yaml"),
        body,
    )

    store = ComponentStore(backend=FakeBackend(), sequences_root=tmp_path)
    summary = await store.sync(client_id="c1")

    assert summary.loaded == 0
    assert summary.skipped == 1
    assert any("missing required fields" in e for e in summary.errors)
    assert any("variant_key" in e for e in summary.errors)


# --------------------------------------------------------------------------- #
# 8. Invalid component_type                                                    #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_sync_skips_invalid_component_type(tmp_path: Path) -> None:
    # Folder name is also the bogus type (so we hit the VALID_* check, not
    # the mismatch check). We can't actually create a folder named
    # "not_a_real_type" that contains a matching YAML without the enum
    # rejecting it, so we place a YAML in a valid folder and make its
    # internal component_type the bogus value — this fires both checks,
    # and the test just asserts the YAML was skipped with an error.
    body = _BASELINE_YAML.replace(
        'component_type: "icebreaker"',
        'component_type: "not_a_real_type"',
    )
    _write(
        _variant_path(tmp_path, "cro_growth_ugc_agency", "icebreaker", "bad.yaml"),
        body,
    )

    store = ComponentStore(backend=FakeBackend(), sequences_root=tmp_path)
    summary = await store.sync(client_id="c1")

    assert summary.loaded == 0
    assert summary.skipped == 1
    assert any("not_a_real_type" in e for e in summary.errors)


# --------------------------------------------------------------------------- #
# 9. Path-vs-YAML niche mismatch                                               #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_sync_rejects_niche_mismatch(tmp_path: Path) -> None:
    # Folder: tech_consulting; YAML says niche: consulting.
    body = _BASELINE_YAML.replace(
        'niche: "cro_growth_ugc_agency"',
        'niche: "consulting"',
    )
    _write(
        _variant_path(tmp_path, "tech_consulting", "icebreaker", "bad.yaml"),
        body,
    )

    store = ComponentStore(backend=FakeBackend(), sequences_root=tmp_path)
    summary = await store.sync(client_id="c1")

    assert summary.loaded == 0
    assert summary.skipped == 1
    assert any("niche" in e and "does not match" in e for e in summary.errors)


# --------------------------------------------------------------------------- #
# 10. Path-vs-YAML component_type mismatch                                     #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_sync_rejects_component_type_folder_mismatch(tmp_path: Path) -> None:
    # Folder: cta; YAML says component_type: icebreaker.
    body = _BASELINE_YAML  # says icebreaker
    _write(
        _variant_path(tmp_path, "cro_growth_ugc_agency", "cta", "bad.yaml"),
        body,
    )

    store = ComponentStore(backend=FakeBackend(), sequences_root=tmp_path)
    summary = await store.sync(client_id="c1")

    assert summary.loaded == 0
    assert summary.skipped == 1
    assert any("component_type" in e and "does not match" in e for e in summary.errors)


# --------------------------------------------------------------------------- #
# 11. Preserve win_rate + sample_size on update                                #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_sync_preserves_learned_stats_on_update(tmp_path: Path) -> None:
    """Updating content MUST NOT clobber win_rate / sample_size.

    The loader's contract with the backend: update_variants sends only
    content/status/metadata/ab_epsilon. The FakeBackend mirrors the
    production Supabase behaviour — it mutates only those columns and
    leaves the learned stats alone.
    """
    backend = FakeBackend()
    row_id = backend.seed_row(
        "c1",
        component_type="icebreaker",
        variant_key="ice_v1",
        niche="cro_growth_ugc_agency",
        offer_label="pipeline_audit",
        variant_content="OLD",
        status="draft",
        metadata={},
        ab_epsilon=0.1,
        win_rate=0.42,
        sample_size=100,
    )

    _write_variant(
        tmp_path,
        component_type="icebreaker",
        variant_key="ice_v1",
        content="NEW",
    )

    store = ComponentStore(backend=backend, sequences_root=tmp_path)
    summary = await store.sync(client_id="c1")

    assert summary.updated == 1
    # The sync path constructs ComponentVariant from YAML and never populates
    # learned stats — the fields keep their defaults (None, 0). The backend
    # mirrors production Supabase behaviour: update_variants only writes
    # content/status/metadata/ab_epsilon and leaves the DB's win_rate /
    # sample_size untouched (verified by the DB row assertion below).
    _, updates = backend.update_calls[0]
    _, payload = updates[0]
    assert payload.win_rate is None
    assert payload.sample_size == 0

    # And the DB row still holds the original learned stats.
    row = backend.get_row(
        "c1", "icebreaker", "ice_v1",
        "cro_growth_ugc_agency", "pipeline_audit",
    )
    assert row is not None
    assert row["id"] == row_id
    assert row["win_rate"] == 0.42
    assert row["sample_size"] == 100
    assert "NEW" in row["variant_content"]


# --------------------------------------------------------------------------- #
# 12. Metadata equality — dict order independence                              #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_sync_metadata_order_independent(tmp_path: Path) -> None:
    """Metadata compares as dicts, so same keys in different order must
    count as unchanged."""
    backend = FakeBackend()
    backend.seed_row(
        "c1",
        component_type="icebreaker",
        variant_key="ice_v1",
        niche="cro_growth_ugc_agency",
        offer_label="pipeline_audit",
        variant_content="hello\n",
        status="draft",
        metadata={"author": "Kirsten", "framework": "saraev"},
        ab_epsilon=0.1,
    )

    # Same metadata keys, different insertion order in YAML — still unchanged.
    _write_variant(
        tmp_path,
        component_type="icebreaker",
        variant_key="ice_v1",
        content="hello",
        metadata={"framework": "saraev", "author": "Kirsten"},
    )

    store = ComponentStore(backend=backend, sequences_root=tmp_path)
    summary = await store.sync(client_id="c1")

    assert summary.unchanged == 1
    assert summary.updated == 0
    assert backend.update_calls == []


# --------------------------------------------------------------------------- #
# Protocol conformance                                                         #
# --------------------------------------------------------------------------- #

def test_fake_backend_satisfies_protocol() -> None:
    """Static + runtime check that FakeBackend is a ComponentStoreBackend."""
    backend: ComponentStoreBackend = FakeBackend()  # type: ignore[assignment]
    assert hasattr(backend, "fetch_existing")
    assert hasattr(backend, "insert_variants")
    assert hasattr(backend, "update_variants")


# --------------------------------------------------------------------------- #
# 13. v2 component types — who_i_am + credibility accepted                     #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
@pytest.mark.parametrize("component_type", ["who_i_am", "credibility"])
async def test_sync_accepts_new_v2_component_types(
    tmp_path: Path, component_type: str,
) -> None:
    """v2 creative_branding introduces who_i_am + credibility. The YAML
    validator must accept these as first-class component types."""
    _write_variant(
        tmp_path,
        component_type=component_type,
        variant_key="v1_sample",
        content="sample body line.",
    )

    backend = FakeBackend()
    store = ComponentStore(backend=backend, sequences_root=tmp_path)
    summary = await store.sync(client_id="c1")

    assert summary.loaded == 1
    assert summary.inserted == 1
    assert summary.errors == []
    _, variants = backend.insert_calls[0]
    assert variants[0].component_type == component_type
