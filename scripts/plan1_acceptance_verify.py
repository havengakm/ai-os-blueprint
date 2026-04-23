"""Plan 1 acceptance verification - post-run evidence collector.

Runs AFTER ``scripts/run_daemon_once.py --dry-run`` has completed. Queries
Supabase for evidence that the dry-run exercised the full foundation
loop for every stage, composed at least one draft, and recorded
component tuples. Emits a markdown report to ``data/reports/``.

Queries only decision_log rows created at or after ``--started-at`` so
the verifier isolates this run's output from historical rows.

Usage:
    uv run python scripts/plan1_acceptance_verify.py \\
        --client-id=<id> --started-at=<ISO8601> \\
        [--output=data/reports/plan1-acceptance-{timestamp}.md]

Exit codes:
    0  AUTO PASS - every automated check green
    1  AUTO FAIL - at least one automated check failed
    2  NEEDS OPERATOR REVIEW - automated checks green but eyeball
       hallucination probe unticked (default for a successful run)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logger = logging.getLogger(__name__)


# ── Constants (kept in sync with preflight) ──────────────────────────────────

PIPELINE_DECISION_TYPES: tuple[str, ...] = (
    "source_selection",
    "score_contact",
    "screen_contact",
    "identity_lookup",
    "enrich_contact",
    "render_draft",
    "research_contact",
)

COMPONENT_TYPES: tuple[str, ...] = (
    "subject_line",
    "icebreaker",
    "pain_hook",
    "offer_frame",
    "cta",
    "signature",
)


# ── Data shapes ───────────────────────────────────────────────────────────────

@dataclass
class RenderDraftEvidence:
    """One render_draft decision's inspection payload."""

    contact_id: str
    decision: str
    component_tuple: dict[str, str]
    component_tuple_complete: bool
    missing_component_types: list[str]
    signals_referenced: list[dict[str, Any]] = field(default_factory=list)
    fills_missing: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class VerifyReport:
    """Aggregate evidence from one dry-run cycle."""

    client_id: str
    started_at: str
    completed_at: str
    decision_rows: list[dict[str, Any]] = field(default_factory=list)
    decisions_by_type: dict[str, int] = field(default_factory=dict)
    stages_with_evidence: list[str] = field(default_factory=list)
    stages_missing_evidence: list[str] = field(default_factory=list)
    render_evidence: list[RenderDraftEvidence] = field(default_factory=list)
    drafts_delta: int = 0
    auto_pass: bool = False
    failure_reasons: list[str] = field(default_factory=list)

    @property
    def total_decisions(self) -> int:
        return len(self.decision_rows)


# ── Supabase builder ──────────────────────────────────────────────────────────

def _build_client(url: str, key: str) -> Any:
    from supabase import create_client
    return create_client(url, key)


# ── Query helpers ─────────────────────────────────────────────────────────────

def _fetch_decision_rows(
    supabase: Any, client_id: str, started_at: str,
) -> list[dict[str, Any]]:
    """Return every decision_log row for client_id created at or after
    started_at. Ordered by created_at ascending."""
    resp = (
        supabase.table("decision_log")
        .select("*")
        .eq("client_id", client_id)
        .gte("created_at", started_at)
        .order("created_at", desc=False)
        .execute()
    )
    return list(resp.data or [])


def _count_drafts(supabase: Any, client_id: str, started_at: str) -> int:
    """Count outreach_drafts rows created at or after started_at."""
    try:
        resp = (
            supabase.table("outreach_drafts")
            .select("id")
            .eq("client_id", client_id)
            .gte("created_at", started_at)
            .execute()
        )
        return len(resp.data or [])
    except Exception as exc:
        logger.warning("outreach_drafts query errored: %s", exc)
        return 0


# ── Verification logic ────────────────────────────────────────────────────────

def _context_of(row: dict[str, Any]) -> dict[str, Any]:
    """Coerce decision_log.context to a dict (it's JSONB; supabase-py
    returns dict, but defensively handle stringified JSON)."""
    ctx = row.get("context")
    if isinstance(ctx, dict):
        return ctx
    if isinstance(ctx, str):
        try:
            parsed = json.loads(ctx)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _extract_render_evidence(
    render_rows: list[dict[str, Any]],
) -> list[RenderDraftEvidence]:
    """Every render_draft row → RenderDraftEvidence. Skips (ComposerSkip)
    are kept for the report but flagged."""
    out: list[RenderDraftEvidence] = []
    for row in render_rows:
        ctx = _context_of(row)
        decision_text = row.get("decision") or ""
        contact_id = ctx.get("contact_id") or "<unknown>"
        component_tuple = ctx.get("component_tuple") or {}
        if not isinstance(component_tuple, dict):
            component_tuple = {}
        missing = [
            ct for ct in COMPONENT_TYPES if ct not in component_tuple
        ]
        skipped = decision_text.startswith("render_draft:skip:")
        out.append(RenderDraftEvidence(
            contact_id=contact_id,
            decision=decision_text,
            component_tuple=dict(component_tuple),
            component_tuple_complete=(not missing) and (not skipped),
            missing_component_types=missing,
            signals_referenced=ctx.get("signals_referenced") or [],
            fills_missing=ctx.get("fills_missing") or [],
            skipped=skipped,
            skip_reason=ctx.get("skip_reason") if skipped else None,
        ))
    return out


def run_verify(
    supabase: Any,
    client_id: str,
    started_at: str,
) -> VerifyReport:
    """Query decision_log + outreach_drafts, assemble VerifyReport, set
    auto_pass + failure_reasons based on automated checks."""
    completed_at = datetime.now(timezone.utc).isoformat()
    report = VerifyReport(
        client_id=client_id,
        started_at=started_at,
        completed_at=completed_at,
    )

    rows = _fetch_decision_rows(supabase, client_id, started_at)
    report.decision_rows = rows

    by_type: dict[str, int] = {}
    for r in rows:
        t = r.get("decision_type") or "<unknown>"
        by_type[t] = by_type.get(t, 0) + 1
    report.decisions_by_type = by_type

    # Stage-level foundation-loop evidence.
    # The code path for every Scout.run_<stage> calls _prime_foundation
    # first (load_foundation + check_autonomy + find_similar_decisions),
    # then dispatches the inner stage, which emits its decision_log row.
    # So: presence of any decision_log row of the stage's decision_type,
    # within the window, is the proxy for "foundation loop fired".
    #
    # (There is no `foundation_loaded=true` or `memory_context_summary`
    # key in the current _prime_foundation / BaseSystem code - see the
    # DEVIATION note in the SOP. Proxy-by-presence is the best signal
    # available without refactoring production code.)
    for stage_type in PIPELINE_DECISION_TYPES:
        if by_type.get(stage_type, 0) >= 1:
            report.stages_with_evidence.append(stage_type)
        else:
            report.stages_missing_evidence.append(stage_type)

    # Render-draft detail (component tuple completeness).
    render_rows = [r for r in rows if r.get("decision_type") == "render_draft"]
    report.render_evidence = _extract_render_evidence(render_rows)

    # Drafts delta (0 in dry-run since composer.persist_draft is guarded by
    # `if not dry_run`). Kept observational - the real evidence is the
    # render_draft decision_log rows.
    report.drafts_delta = _count_drafts(supabase, client_id, started_at)

    # ── Failure evaluation ──────────────────────────────────────────────

    reasons: list[str] = []

    if report.total_decisions < len(PIPELINE_DECISION_TYPES):
        reasons.append(
            f"only {report.total_decisions} decision_log rows "
            f"(expected >= {len(PIPELINE_DECISION_TYPES)})"
        )

    if report.stages_missing_evidence:
        reasons.append(
            "missing foundation-loop evidence for stages: "
            f"{report.stages_missing_evidence}"
        )

    # A single successful render_draft with a complete component_tuple is
    # enough: the composer fans out per-contact, some may skip, but at
    # least one must produce a full tuple.
    successful_renders = [
        e for e in report.render_evidence
        if e.component_tuple_complete and not e.skipped
    ]
    if not successful_renders:
        reasons.append(
            "no render_draft decision has a complete 6-component tuple "
            "(every render was skipped or missing component_types)"
        )

    report.failure_reasons = reasons
    report.auto_pass = not reasons

    return report


# ── Markdown report rendering ─────────────────────────────────────────────────

_HALLUCINATION_CHECKBOX = "[ ] I have inspected every draft below and every citable fact traces back to raw_data / research_data. No fabrication found."


def _render_markdown(report: VerifyReport) -> str:
    lines: list[str] = []
    ts = report.completed_at
    lines.append(f"# Plan 1 Acceptance Report - {report.client_id} - {ts}")
    lines.append("")

    # Summary.
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Cycle window start: `{report.started_at}`")
    lines.append(f"- Cycle window end:   `{report.completed_at}`")
    lines.append(f"- Decisions logged: {report.total_decisions}")
    lines.append(f"- Drafts persisted to outreach_drafts: {report.drafts_delta}")
    foundation_mark = "PASS" if not report.stages_missing_evidence else "FAIL"
    lines.append(
        f"- Foundation loop fired on all stages: {foundation_mark} "
        f"(stages with evidence: {len(report.stages_with_evidence)}/"
        f"{len(PIPELINE_DECISION_TYPES)})"
    )
    lines.append(f"- Automated checks: {'PASS' if report.auto_pass else 'FAIL'}")
    if report.failure_reasons:
        lines.append("")
        lines.append("Failure reasons:")
        for r in report.failure_reasons:
            lines.append(f"  - {r}")
    lines.append("")

    # Decision breakdown.
    lines.append("## Decision breakdown by type")
    lines.append("")
    lines.append("| decision_type | count |")
    lines.append("|---|---|")
    for t in sorted(report.decisions_by_type):
        lines.append(f"| {t} | {report.decisions_by_type[t]} |")
    if not report.decisions_by_type:
        lines.append("| _(none)_ | 0 |")
    lines.append("")

    # Stage trace.
    lines.append("## Foundation-loop trace (per pipeline stage)")
    lines.append("")
    lines.append(
        "> Note: this section proves `_prime_foundation` dispatched for "
        "each stage. `BaseSystem.load_foundation` degrades silently if "
        "`memory_store` is not wired (returns empty context), so the "
        "proxy is necessary but not sufficient. Cross-check with the "
        "preflight's context + knowledge + autonomy row-count results "
        "to confirm data actually loaded."
    )
    lines.append("")
    lines.append(
        "Each row below is a pipeline decision_type. "
        "Presence of at least one decision_log row of that type within "
        "the cycle window is proxy evidence that `_prime_foundation` + "
        "the inner stage both ran (Scout.run_<stage> gates every stage "
        "through the foundation loop before dispatch)."
    )
    lines.append("")
    lines.append("| stage (decision_type) | rows logged | evidence |")
    lines.append("|---|---|---|")
    for stage_type in PIPELINE_DECISION_TYPES:
        count = report.decisions_by_type.get(stage_type, 0)
        marker = "ok" if count >= 1 else "FAIL"
        lines.append(f"| {stage_type} | {count} | {marker} |")
    lines.append("")

    # Render drafts.
    lines.append("## Drafts composed (render_draft decisions)")
    lines.append("")
    if not report.render_evidence:
        lines.append("_(no render_draft decisions logged)_")
    else:
        for idx, e in enumerate(report.render_evidence, start=1):
            lines.append(f"### Draft {idx} - contact_id `{e.contact_id}`")
            lines.append("")
            if e.skipped:
                lines.append(
                    f"**SKIPPED** - reason: `{e.skip_reason}`. "
                    "Composer could not produce a draft for this contact."
                )
                lines.append("")
                continue
            lines.append(f"- decision: `{e.decision}`")
            lines.append(
                f"- component tuple complete: "
                f"{'yes' if e.component_tuple_complete else 'no'}"
            )
            if e.missing_component_types:
                lines.append(
                    f"- missing component types: {e.missing_component_types}"
                )
            lines.append("- component_tuple:")
            for ct in COMPONENT_TYPES:
                vk = e.component_tuple.get(ct, "<MISSING>")
                lines.append(f"    - {ct}: `{vk}`")
            if e.fills_missing:
                lines.append(f"- unfilled placeholders: {e.fills_missing}")
            lines.append(
                f"- signals referenced: {len(e.signals_referenced)}"
            )
            lines.append("")

    # Hallucination probe.
    lines.append("## Hallucination probe (operator inspects)")
    lines.append("")
    lines.append(
        "The dry-run does not persist outreach_drafts rows "
        "(`composer.persist_draft` is guarded by `if not dry_run`), so the "
        "full subject + body text is not stored. The decision_log rows "
        "above include the component variant_keys used; operator must "
        "cross-reference against the YAML source files + each contact's "
        "`raw_data` / `research_data` in Supabase to confirm every "
        "citable fact traces back."
    )
    lines.append("")
    lines.append("For each draft above, verify:")
    lines.append("")
    lines.append("1. Every variant_key exists in the matching YAML under")
    lines.append("   `data/knowledge/components/` (or wherever components")
    lines.append("   live for this deployment).")
    lines.append("2. Every `signals_referenced.source` is a real enrichment")
    lines.append("   adapter that ran for this contact (ZeroBounce / Trigify")
    lines.append("   / etc.) - not an invented source.")
    lines.append("3. No `fills_missing` placeholder is a citable fact")
    lines.append("   (unfilled ICEBREAKER placeholders rendered as empty")
    lines.append("   string are acceptable; unfilled PAIN_EVIDENCE is not).")
    lines.append("")
    lines.append(f"- {_HALLUCINATION_CHECKBOX}")
    lines.append("")

    # Recommendation.
    lines.append("## Recommendation")
    lines.append("")
    if not report.auto_pass:
        lines.append(
            "**AUTO FAIL** - automated checks did not pass. "
            "See failure reasons above. Do NOT merge Plan 1. File a "
            "backlog item, fix the root cause, re-run acceptance."
        )
    else:
        lines.append(
            "**NEEDS OPERATOR REVIEW** - automated checks green. "
            "Operator must tick the hallucination-probe checkbox above "
            "after spot-checking every draft. Once ticked: PASS → "
            "merge Plan 1 to main. Until ticked: HOLD."
        )
    lines.append("")
    return "\n".join(lines)


# ── Output path resolution ────────────────────────────────────────────────────

def _default_output_path() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _REPO_ROOT / "data" / "reports" / f"plan1-acceptance-{ts}.md"


def _write_report(markdown: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Post-run verification for Plan 1 acceptance. Queries "
            "decision_log for evidence that every pipeline stage ran "
            "under the foundation loop + composer produced at least one "
            "complete component tuple. Emits markdown to data/reports/."
        ),
    )
    parser.add_argument(
        "--client-id", required=True,
        help="Client ID to verify.",
    )
    parser.add_argument(
        "--started-at", required=True,
        help=(
            "ISO 8601 timestamp of when the dry-run cycle started. "
            "Verify queries rows created at or after this timestamp."
        ),
    )
    parser.add_argument(
        "--output", default=None,
        help=(
            "Optional output path for the markdown report. "
            "Default: data/reports/plan1-acceptance-{timestamp}.md"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print(
            "ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.",
            file=sys.stderr,
        )
        return 1

    try:
        supabase = _build_client(url, key)
    except Exception as exc:
        print(f"ERROR: could not build Supabase client: {exc}", file=sys.stderr)
        return 1

    report = run_verify(supabase, args.client_id, args.started_at)
    markdown = _render_markdown(report)

    output = Path(args.output) if args.output else _default_output_path()
    _write_report(markdown, output)

    print(f"report written: {output}")
    print(f"decisions logged: {report.total_decisions}")
    print(
        f"stages with evidence: {len(report.stages_with_evidence)}/"
        f"{len(PIPELINE_DECISION_TYPES)}"
    )
    if not report.auto_pass:
        print("recommendation: AUTO FAIL")
        for r in report.failure_reasons:
            print(f"  - {r}")
        return 1
    print("recommendation: NEEDS OPERATOR REVIEW")
    return 2


if __name__ == "__main__":
    sys.exit(main())
