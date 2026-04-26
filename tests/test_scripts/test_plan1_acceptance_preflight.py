"""Tests for scripts/plan1_acceptance_preflight.py."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.plan1_acceptance_preflight import (  # noqa: E402
    COMPONENT_TYPES,
    MIN_CONTACTS_FOR_MEANINGFUL_RUN,
    PIPELINE_DECISION_TYPES,
    PIPELINE_ELIGIBLE_STATUSES,
    REQUIRED_ENV,
    SCHEMA_TABLES,
    check_autonomy_rules,
    check_client_exists,
    check_component_variants,
    check_contact_count,
    check_context_seeded,
    check_env,
    check_knowledge_seeded,
    check_schema,
    main,
    run_preflight,
)
from tests.test_supabase_backends.fakes import FakeSupabaseClient  # noqa: E402

CLIENT_ID = "acc-test"


# ── Fixture helpers ──────────────────────────────────────────────────────────

def _full_seed(client_id: str = CLIENT_ID) -> dict[str, list[dict[str, Any]]]:
    """Seed every table the preflight inspects so every check passes."""
    autonomy_rows = [
        {"client_id": client_id, "action_type": t, "autonomy_level": "suggest"}
        for t in PIPELINE_DECISION_TYPES
    ]
    component_rows = [
        {
            "client_id": client_id,
            "niche": "agency-growth",
            "offer_label": "leads-in-30-days",
            "component_type": ct,
            "variant_key": f"{ct}_v1",
            "status": "approved",
        }
        for ct in COMPONENT_TYPES
    ]
    contact_rows = [
        {
            "id": f"c{i}",
            "client_id": client_id,
            "status": "new" if i % 2 == 0 else "enriched",
        }
        for i in range(MIN_CONTACTS_FOR_MEANINGFUL_RUN + 2)
    ]
    # information_schema view (migration 013) — populated with every
    # required table so the schema cross-check passes by default.
    information_schema_rows = [
        {"table_name": t} for t in SCHEMA_TABLES
    ]
    return {
        # Schema probe targets. SELECT on missing tables returns [] in the
        # fake, but check_schema also cross-checks against the
        # preflight_existing_tables view below.
        "clients": [{"id": client_id, "status": "active"}],
        "client_config": [{"client_id": client_id}],
        "contacts": contact_rows,
        "outreach_drafts": [],
        "decision_log": [],
        "business_context": [{"id": "bc1", "client_id": client_id}],
        "client_facts": [{"id": "cf1", "client_id": client_id}],
        "knowledge_base": [{"id": "kb1"}],
        "autonomy_rules": autonomy_rows,
        "component_variants": component_rows,
        "preflight_existing_tables": information_schema_rows,
    }


# ── check_env ────────────────────────────────────────────────────────────────

def test_check_env_all_present(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED_ENV:
        monkeypatch.setenv(name, "x")
    assert check_env() == []


def test_check_env_missing_some(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SUPABASE_URL", "http://x")
    missing = check_env()
    assert "SUPABASE_URL" not in missing
    assert "SUPABASE_SERVICE_ROLE_KEY" in missing
    assert "VOYAGE_API_KEY" in missing
    assert "ANTHROPIC_API_KEY" in missing


# ── check_schema ─────────────────────────────────────────────────────────────

def test_check_schema_all_tables_reachable_when_seeded() -> None:
    sb = FakeSupabaseClient(tables=_full_seed())
    results = check_schema(sb)
    assert len(results) == len(SCHEMA_TABLES)
    assert all(r.passed for r in results)


def test_check_schema_empty_tables_still_reachable() -> None:
    # A table with no rows still counts as "reachable" - SELECT returns [].
    sb = FakeSupabaseClient(tables={t: [] for t in SCHEMA_TABLES})
    # Seed the information_schema view with all tables so check_schema cross-
    # check passes too (this test is about empty tables, not missing schema).
    sb._tables["preflight_existing_tables"] = [
        {"table_name": t} for t in SCHEMA_TABLES
    ]
    results = check_schema(sb)
    assert all(r.passed for r in results)


def test_check_schema_detects_postgrest_false_positive() -> None:
    """check_schema must cross-check against information_schema, not just rely
    on PostgREST returning 200. Reproduces follow-up item 1: PostgREST permission
    cache reports tables reachable when information_schema disagrees."""
    seed = _full_seed()
    # PostgREST sees all tables as reachable (every required table is in seed),
    # but information_schema reports business_context + autonomy_rules MISSING.
    seed["preflight_existing_tables"] = [
        {"table_name": t} for t in SCHEMA_TABLES
        if t not in ("business_context", "autonomy_rules")
    ]
    sb = FakeSupabaseClient(tables=seed)
    results = check_schema(sb)
    by_name = {r.name: r for r in results}

    # Both must be flagged as failing despite SELECT working.
    assert not by_name["schema:business_context"].passed
    assert "information_schema" in by_name["schema:business_context"].detail.lower()
    assert not by_name["schema:autonomy_rules"].passed
    assert "information_schema" in by_name["schema:autonomy_rules"].detail.lower()

    # Tables in both PostgREST and information_schema should pass.
    for t in SCHEMA_TABLES:
        if t in ("business_context", "autonomy_rules"):
            continue
        assert by_name[f"schema:{t}"].passed, (
            f"{t} should pass: present in both PostgREST and information_schema"
        )


def test_check_schema_fix_message_points_at_migration_when_view_missing() -> None:
    """If the preflight_existing_tables view query returns nothing for ALL
    required tables, the fix message should suggest applying migration 013."""
    seed = _full_seed()
    # View returns empty: every required table appears MISSING from
    # information_schema.
    seed["preflight_existing_tables"] = []
    sb = FakeSupabaseClient(tables=seed)
    results = check_schema(sb)

    # Every check fails because nothing is in information_schema.
    assert all(not r.passed for r in results)
    # At least one fix mentions the migration that creates the view.
    assert any(
        "013" in (r.fix or "") or "preflight_existing_tables" in (r.fix or "")
        for r in results
    )


# ── check_client_exists ──────────────────────────────────────────────────────

def test_check_client_exists_happy_path() -> None:
    sb = FakeSupabaseClient(tables=_full_seed())
    res = check_client_exists(sb, CLIENT_ID)
    assert res.passed
    assert "active" in res.detail


def test_check_client_exists_no_clients_row() -> None:
    seed = _full_seed()
    seed["clients"] = []
    sb = FakeSupabaseClient(tables=seed)
    res = check_client_exists(sb, CLIENT_ID)
    assert not res.passed
    assert "no clients row" in res.detail
    assert res.fix is not None


def test_check_client_exists_status_not_active() -> None:
    seed = _full_seed()
    seed["clients"] = [{"id": CLIENT_ID, "status": "paused"}]
    sb = FakeSupabaseClient(tables=seed)
    res = check_client_exists(sb, CLIENT_ID)
    assert not res.passed
    assert "paused" in res.detail


def test_check_client_exists_no_client_config_row() -> None:
    seed = _full_seed()
    seed["client_config"] = []
    sb = FakeSupabaseClient(tables=seed)
    res = check_client_exists(sb, CLIENT_ID)
    assert not res.passed
    assert "client_config" in res.detail


# ── check_context_seeded ─────────────────────────────────────────────────────

def test_check_context_both_seeded() -> None:
    sb = FakeSupabaseClient(tables=_full_seed())
    results = check_context_seeded(sb, CLIENT_ID)
    assert len(results) == 2
    assert all(r.passed for r in results)


def test_check_context_missing_business_context() -> None:
    seed = _full_seed()
    seed["business_context"] = []
    sb = FakeSupabaseClient(tables=seed)
    results = check_context_seeded(sb, CLIENT_ID)
    by_name = {r.name: r for r in results}
    assert not by_name["context:business_context"].passed
    assert by_name["context:client_facts"].passed


def test_check_context_missing_client_facts() -> None:
    seed = _full_seed()
    seed["client_facts"] = []
    sb = FakeSupabaseClient(tables=seed)
    results = check_context_seeded(sb, CLIENT_ID)
    by_name = {r.name: r for r in results}
    assert not by_name["context:client_facts"].passed
    assert by_name["context:business_context"].passed


# ── check_knowledge_seeded ───────────────────────────────────────────────────

def test_check_knowledge_seeded_happy() -> None:
    sb = FakeSupabaseClient(tables=_full_seed())
    res = check_knowledge_seeded(sb)
    assert res.passed


def test_check_knowledge_seeded_empty_fails() -> None:
    seed = _full_seed()
    seed["knowledge_base"] = []
    sb = FakeSupabaseClient(tables=seed)
    res = check_knowledge_seeded(sb)
    assert not res.passed
    assert res.fix is not None


# ── check_autonomy_rules ─────────────────────────────────────────────────────

def test_check_autonomy_rules_all_present() -> None:
    sb = FakeSupabaseClient(tables=_full_seed())
    res = check_autonomy_rules(sb, CLIENT_ID)
    assert res.passed


def test_check_autonomy_rules_missing_some() -> None:
    seed = _full_seed()
    # Drop 2 of the pipeline decision_types.
    seed["autonomy_rules"] = [
        r for r in seed["autonomy_rules"]
        if r["action_type"] not in {"render_draft", "source_selection"}
    ]
    sb = FakeSupabaseClient(tables=seed)
    res = check_autonomy_rules(sb, CLIENT_ID)
    assert not res.passed
    assert "render_draft" in res.detail
    assert "source_selection" in res.detail


# ── check_component_variants ─────────────────────────────────────────────────

def test_check_component_variants_complete_pairing() -> None:
    sb = FakeSupabaseClient(tables=_full_seed())
    res = check_component_variants(sb, CLIENT_ID)
    assert res.passed


def test_check_component_variants_incomplete_pairing() -> None:
    seed = _full_seed()
    # Drop the CTA - pairing is no longer complete.
    seed["component_variants"] = [
        r for r in seed["component_variants"] if r["component_type"] != "cta"
    ]
    sb = FakeSupabaseClient(tables=seed)
    res = check_component_variants(sb, CLIENT_ID)
    assert not res.passed


def test_check_component_variants_draft_status_ignored() -> None:
    # Only 'approved' counts - if every variant is 'draft' the check fails.
    seed = _full_seed()
    for r in seed["component_variants"]:
        r["status"] = "draft"
    sb = FakeSupabaseClient(tables=seed)
    res = check_component_variants(sb, CLIENT_ID)
    assert not res.passed


# ── check_contact_count ──────────────────────────────────────────────────────

def test_check_contact_count_sufficient() -> None:
    sb = FakeSupabaseClient(tables=_full_seed())
    res = check_contact_count(sb, CLIENT_ID)
    assert res.passed


def test_check_contact_count_too_few() -> None:
    seed = _full_seed()
    seed["contacts"] = seed["contacts"][:3]
    sb = FakeSupabaseClient(tables=seed)
    res = check_contact_count(sb, CLIENT_ID)
    assert not res.passed
    assert "pipeline-eligible" in res.detail


def test_check_contact_count_all_sent_hint() -> None:
    seed = _full_seed()
    seed["contacts"] = [
        {"id": f"c{i}", "client_id": CLIENT_ID, "status": "sent"}
        for i in range(5)
    ]
    sb = FakeSupabaseClient(tables=seed)
    res = check_contact_count(sb, CLIENT_ID)
    assert not res.passed
    assert "all in status='sent'" in res.detail


def test_pipeline_eligible_statuses_cover_expected() -> None:
    # Matches what score.py + enrich.py + pull.py emit.
    assert set(PIPELINE_ELIGIBLE_STATUSES) == {
        "new", "screened", "ready", "enriched",
    }


# ── run_preflight aggregate ──────────────────────────────────────────────────

def test_run_preflight_all_pass() -> None:
    sb = FakeSupabaseClient(tables=_full_seed())
    report = run_preflight(sb, CLIENT_ID)
    assert report.all_passed
    # 10 schema checks + 1 client_exists + 2 context + 1 knowledge +
    # 1 autonomy + 1 component + 1 contact = 17
    assert len(report.checks) == len(SCHEMA_TABLES) + 7


def test_run_preflight_fail_with_missing_knowledge() -> None:
    seed = _full_seed()
    seed["knowledge_base"] = []
    sb = FakeSupabaseClient(tables=seed)
    report = run_preflight(sb, CLIENT_ID)
    assert not report.all_passed
    assert any(not c.passed and c.name == "knowledge_seeded" for c in report.checks)


def test_to_dict_roundtrip() -> None:
    sb = FakeSupabaseClient(tables=_full_seed())
    report = run_preflight(sb, CLIENT_ID)
    as_dict = report.to_dict()
    assert as_dict["client_id"] == CLIENT_ID
    assert as_dict["all_passed"] is True
    assert len(as_dict["checks"]) == len(report.checks)


# ── main() CLI ───────────────────────────────────────────────────────────────

def test_main_env_missing_returns_2(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    code = main(["--client-id", CLIENT_ID])
    assert code == 2


def test_main_all_pass_returns_0(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED_ENV:
        monkeypatch.setenv(name, "fake-value")

    fake_client = FakeSupabaseClient(tables=_full_seed())
    with patch(
        "scripts.plan1_acceptance_preflight._build_client",
        return_value=fake_client,
    ):
        code = main(["--client-id", CLIENT_ID])
    assert code == 0


def test_main_failing_check_returns_1(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED_ENV:
        monkeypatch.setenv(name, "fake-value")

    seed = _full_seed()
    seed["knowledge_base"] = []
    fake_client = FakeSupabaseClient(tables=seed)
    with patch(
        "scripts.plan1_acceptance_preflight._build_client",
        return_value=fake_client,
    ):
        code = main(["--client-id", CLIENT_ID])
    assert code == 1


def test_main_json_mode_emits_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in REQUIRED_ENV:
        monkeypatch.setenv(name, "fake-value")

    fake_client = FakeSupabaseClient(tables=_full_seed())
    with patch(
        "scripts.plan1_acceptance_preflight._build_client",
        return_value=fake_client,
    ):
        code = main(["--client-id", CLIENT_ID, "--json"])
    assert code == 0
    out = capsys.readouterr().out
    # Output is JSON - first char after stripping leading whitespace is '{'.
    assert out.lstrip().startswith("{")
    assert '"all_passed": true' in out
