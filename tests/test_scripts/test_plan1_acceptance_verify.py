"""Tests for scripts/plan1_acceptance_verify.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.plan1_acceptance_verify import (  # noqa: E402
    COMPONENT_TYPES,
    PIPELINE_DECISION_TYPES,
    _extract_render_evidence,
    _render_markdown,
    main,
    run_verify,
)
from tests.test_supabase_backends.fakes import FakeSupabaseClient  # noqa: E402

CLIENT_ID = "acc-test"
STARTED_AT = "2026-04-23T00:00:00Z"
AFTER = "2026-04-23T00:00:05Z"
BEFORE = "2026-04-22T12:00:00Z"


# ── Fixture helpers ──────────────────────────────────────────────────────────

def _decision_row(
    *,
    decision_type: str,
    decision: str,
    context: dict[str, Any],
    created_at: str = AFTER,
    client_id: str = CLIENT_ID,
) -> dict[str, Any]:
    return {
        "id": f"row-{decision_type}-{decision}",
        "client_id": client_id,
        "decision_type": decision_type,
        "decision": decision,
        "context": context,
        "reasoning": "test",
        "source": "system",
        "created_at": created_at,
    }


def _complete_component_tuple(contact_id: str = "ct1") -> dict[str, Any]:
    return {
        "contact_id": contact_id,
        "niche": "agency-growth",
        "offer_label": "leads-in-30-days",
        "component_tuple": {ct: f"{ct}_v1" for ct in COMPONENT_TYPES},
        "signals_referenced": [
            {"source": "trigify", "url": "https://example.com/post/1"},
        ],
        "fills_missing": [],
        "dry_run": True,
    }


def _full_run_rows() -> list[dict[str, Any]]:
    """A realistic successful dry-run: one row per pipeline decision_type,
    render_draft has a complete component_tuple."""
    rows: list[dict[str, Any]] = []
    for dt in PIPELINE_DECISION_TYPES:
        if dt == "render_draft":
            rows.append(_decision_row(
                decision_type=dt,
                decision="render_draft:ct1:Subject preview here",
                context=_complete_component_tuple(),
            ))
        else:
            rows.append(_decision_row(
                decision_type=dt,
                decision=f"{dt}:test",
                context={"stage": dt},
            ))
    return rows


# ── _extract_render_evidence ─────────────────────────────────────────────────

def test_extract_render_evidence_complete() -> None:
    rows = [
        _decision_row(
            decision_type="render_draft",
            decision="render_draft:ct1:Subject line preview",
            context=_complete_component_tuple(),
        ),
    ]
    evidence = _extract_render_evidence(rows)
    assert len(evidence) == 1
    e = evidence[0]
    assert e.contact_id == "ct1"
    assert e.component_tuple_complete
    assert e.missing_component_types == []
    assert not e.skipped


def test_extract_render_evidence_incomplete_tuple() -> None:
    ctx = _complete_component_tuple()
    del ctx["component_tuple"]["signature"]
    rows = [
        _decision_row(
            decision_type="render_draft",
            decision="render_draft:ct1:preview",
            context=ctx,
        ),
    ]
    evidence = _extract_render_evidence(rows)
    assert not evidence[0].component_tuple_complete
    assert "signature" in evidence[0].missing_component_types


def test_extract_render_evidence_skipped() -> None:
    rows = [
        _decision_row(
            decision_type="render_draft",
            decision="render_draft:skip:ct2:no_variants_for:cta",
            context={
                "contact_id": "ct2",
                "skip_reason": "no_variants_for:cta",
            },
        ),
    ]
    evidence = _extract_render_evidence(rows)
    assert evidence[0].skipped
    assert evidence[0].skip_reason == "no_variants_for:cta"
    assert not evidence[0].component_tuple_complete


def test_extract_render_evidence_handles_stringified_jsonb() -> None:
    # Defensive: if supabase-py ever returns JSONB as a string, the
    # _context_of helper must still parse it.
    ctx = _complete_component_tuple()
    rows = [
        _decision_row(
            decision_type="render_draft",
            decision="render_draft:ct1:preview",
            context=ctx,
        ),
    ]
    rows[0]["context"] = json.dumps(rows[0]["context"])
    evidence = _extract_render_evidence(rows)
    assert evidence[0].component_tuple_complete


# ── run_verify aggregate ─────────────────────────────────────────────────────

def test_run_verify_auto_pass() -> None:
    sb = FakeSupabaseClient(tables={
        "decision_log": _full_run_rows(),
        "outreach_drafts": [],
    })
    report = run_verify(sb, CLIENT_ID, STARTED_AT)
    assert report.auto_pass
    assert report.failure_reasons == []
    assert len(report.stages_missing_evidence) == 0
    assert len(report.stages_with_evidence) == len(PIPELINE_DECISION_TYPES)


def test_run_verify_fails_when_stages_missing() -> None:
    rows = _full_run_rows()
    # Remove the render_draft + enrich_contact rows.
    rows = [
        r for r in rows
        if r["decision_type"] not in {"render_draft", "enrich_contact"}
    ]
    sb = FakeSupabaseClient(tables={
        "decision_log": rows,
        "outreach_drafts": [],
    })
    report = run_verify(sb, CLIENT_ID, STARTED_AT)
    assert not report.auto_pass
    assert "render_draft" in report.stages_missing_evidence
    assert "enrich_contact" in report.stages_missing_evidence


def test_run_verify_fails_when_render_skipped_only() -> None:
    # All stages fire but every render_draft was a skip - no complete tuple.
    rows = [
        r for r in _full_run_rows() if r["decision_type"] != "render_draft"
    ]
    rows.append(_decision_row(
        decision_type="render_draft",
        decision="render_draft:skip:ct2:no_variants_for:cta",
        context={"contact_id": "ct2", "skip_reason": "no_variants_for:cta"},
    ))
    sb = FakeSupabaseClient(tables={
        "decision_log": rows,
        "outreach_drafts": [],
    })
    report = run_verify(sb, CLIENT_ID, STARTED_AT)
    assert not report.auto_pass
    assert any(
        "complete 6-component tuple" in r for r in report.failure_reasons
    )


def test_run_verify_filters_by_started_at() -> None:
    # Rows with created_at BEFORE started_at are excluded by the
    # .gte() filter, so the run looks empty.
    rows = _full_run_rows()
    for r in rows:
        r["created_at"] = BEFORE
    sb = FakeSupabaseClient(tables={
        "decision_log": rows,
        "outreach_drafts": [],
    })
    report = run_verify(sb, CLIENT_ID, STARTED_AT)
    assert report.total_decisions == 0
    assert not report.auto_pass


def test_run_verify_decisions_by_type_counts() -> None:
    rows = _full_run_rows()
    # Add a second render_draft (skip) - count should reflect both.
    rows.append(_decision_row(
        decision_type="render_draft",
        decision="render_draft:skip:ct2:no_variants_for:cta",
        context={"contact_id": "ct2", "skip_reason": "no_variants_for:cta"},
    ))
    sb = FakeSupabaseClient(tables={
        "decision_log": rows,
        "outreach_drafts": [],
    })
    report = run_verify(sb, CLIENT_ID, STARTED_AT)
    assert report.decisions_by_type["render_draft"] == 2
    assert report.decisions_by_type["source_selection"] == 1


def test_run_verify_drafts_delta_observational() -> None:
    sb = FakeSupabaseClient(tables={
        "decision_log": _full_run_rows(),
        "outreach_drafts": [
            {"id": "d1", "client_id": CLIENT_ID, "created_at": AFTER},
            {"id": "d2", "client_id": CLIENT_ID, "created_at": AFTER},
            {"id": "d3", "client_id": CLIENT_ID, "created_at": BEFORE},
        ],
    })
    report = run_verify(sb, CLIENT_ID, STARTED_AT)
    # Only the 2 in the cycle window count (BEFORE is filtered by .gte).
    assert report.drafts_delta == 2


# ── _render_markdown ─────────────────────────────────────────────────────────

def test_render_markdown_pass_branch() -> None:
    sb = FakeSupabaseClient(tables={
        "decision_log": _full_run_rows(),
        "outreach_drafts": [],
    })
    report = run_verify(sb, CLIENT_ID, STARTED_AT)
    md = _render_markdown(report)
    assert "# Plan 1 Acceptance Report" in md
    assert CLIENT_ID in md
    # Every pipeline decision_type shows up in the trace table.
    for dt in PIPELINE_DECISION_TYPES:
        assert dt in md
    assert "NEEDS OPERATOR REVIEW" in md
    # Hallucination probe checkbox is present and unticked.
    assert "[ ]" in md


def test_render_markdown_fail_branch() -> None:
    rows = [
        r for r in _full_run_rows() if r["decision_type"] != "render_draft"
    ]
    sb = FakeSupabaseClient(tables={
        "decision_log": rows,
        "outreach_drafts": [],
    })
    report = run_verify(sb, CLIENT_ID, STARTED_AT)
    md = _render_markdown(report)
    assert "AUTO FAIL" in md
    assert "Do NOT merge" in md


# ── main() CLI ───────────────────────────────────────────────────────────────

def test_main_writes_report_and_returns_2_on_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "http://x")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "x")

    fake_client = FakeSupabaseClient(tables={
        "decision_log": _full_run_rows(),
        "outreach_drafts": [],
    })
    out = tmp_path / "report.md"
    with patch(
        "scripts.plan1_acceptance_verify._build_client",
        return_value=fake_client,
    ):
        code = main([
            "--client-id", CLIENT_ID,
            "--started-at", STARTED_AT,
            "--output", str(out),
        ])
    # Auto pass branch returns 2 - operator review still required.
    assert code == 2
    assert out.exists()
    body = out.read_text()
    assert "NEEDS OPERATOR REVIEW" in body


def test_main_returns_1_on_auto_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "http://x")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "x")

    rows = [
        r for r in _full_run_rows() if r["decision_type"] != "render_draft"
    ]
    fake_client = FakeSupabaseClient(tables={
        "decision_log": rows,
        "outreach_drafts": [],
    })
    out = tmp_path / "report.md"
    with patch(
        "scripts.plan1_acceptance_verify._build_client",
        return_value=fake_client,
    ):
        code = main([
            "--client-id", CLIENT_ID,
            "--started-at", STARTED_AT,
            "--output", str(out),
        ])
    assert code == 1
    assert out.exists()


def test_main_env_missing_returns_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    code = main([
        "--client-id", CLIENT_ID, "--started-at", STARTED_AT,
    ])
    assert code == 1
