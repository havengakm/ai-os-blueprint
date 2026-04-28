"""Weekly review job — operator-facing per-client roll-up.

Plan 2 Phase 5 Task 2.5.1. Cron-scheduled (e.g. Monday 6am operator-
local) job that produces a per-client weekly report covering:

  1. Cost analysis (reuses scripts.cost_dashboard.fetch_cost_report).
  2. Reply rate (replies / sends in window).
  3. Pending recommendations count.
  4. Open escalations count.
  5. Cool-off queue: total cooling + subset ready to re-enter.

v2 will add:
  - Variant performance (bandit win-rate breakdown)
  - Adapter ROI (which signals correlate with replies)
  - Send-time analysis (day/hour reply-rate buckets)

Each addition needs data we don't yet track at full attribution
(variant_pulls + adapter→reply correlation). The scaffolding here
makes adding sections trivial — extend ``WeeklyReviewReport`` +
``run`` + ``render_markdown``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class WeeklyReviewReport:
    client_id: str
    window_days: int
    generated_at: datetime
    cost: dict[str, Any] = field(default_factory=dict)
    reply_rate: dict[str, Any] = field(default_factory=dict)
    pending_recommendations: int = 0
    open_escalations: int = 0
    cooling_off_count: int = 0
    ready_to_re_enter_count: int = 0


# --------------------------------------------------------------------------- #
# WeeklyReview                                                                #
# --------------------------------------------------------------------------- #


class WeeklyReview:
    def __init__(self, *, client: Any) -> None:
        self._client = client

    async def run(
        self,
        client_id: str,
        *,
        days: int = 7,
        now: datetime | None = None,
    ) -> WeeklyReviewReport:
        from scripts.cost_dashboard import fetch_cost_report

        now = now or datetime.now(timezone.utc)

        cost = await fetch_cost_report(self._client, client_id, days, now=now)
        reply = await self._reply_rate(client_id, days=days, now=now)
        pending = await self._pending_recommendations(client_id)
        escalations = await self._open_escalations(client_id)
        cooling, ready = await self._cool_off_counts(client_id, now=now)

        return WeeklyReviewReport(
            client_id=client_id,
            window_days=days,
            generated_at=now,
            cost=cost,
            reply_rate=reply,
            pending_recommendations=pending,
            open_escalations=escalations,
            cooling_off_count=cooling,
            ready_to_re_enter_count=ready,
        )

    # ----- section fetchers ----------------------------------------------- #

    async def _reply_rate(
        self, client_id: str, *, days: int, now: datetime,
    ) -> dict[str, Any]:
        cutoff = (now - timedelta(days=days)).isoformat()

        sends_resp = (
            self._client.table("outreach_send_log")
            .select("contact_id, sent_at")
            .eq("client_id", client_id)
            .gte("sent_at", cutoff)
            .execute()
        )
        replies_resp = (
            self._client.table("outreach_reply")
            .select("contact_id, received_at")
            .eq("client_id", client_id)
            .gte("received_at", cutoff)
            .execute()
        )
        sends = len(sends_resp.data or [])
        replies = len(replies_resp.data or [])
        rate = (replies / sends) if sends else 0.0
        return {"sends": sends, "replies": replies, "rate": round(rate, 4)}

    async def _pending_recommendations(self, client_id: str) -> int:
        resp = (
            self._client.table("optimizer_recommendation")
            .select("id")
            .eq("client_id", client_id)
            .eq("status", "pending")
            .execute()
        )
        return len(resp.data or [])

    async def _open_escalations(self, client_id: str) -> int:
        resp = (
            self._client.table("escalations")
            .select("id")
            .eq("client_id", client_id)
            .eq("status", "open")
            .execute()
        )
        return len(resp.data or [])

    async def _cool_off_counts(
        self, client_id: str, *, now: datetime,
    ) -> tuple[int, int]:
        resp = (
            self._client.table("contacts")
            .select("id, status, cool_off_until")
            .eq("client_id", client_id)
            .eq("status", "cooling_off")
            .execute()
        )
        rows = resp.data or []
        cooling = len(rows)
        now_iso = now.isoformat()
        ready = sum(
            1 for r in rows
            if r.get("cool_off_until")
            and r["cool_off_until"] <= now_iso
        )
        return cooling, ready


# --------------------------------------------------------------------------- #
# render_markdown                                                             #
# --------------------------------------------------------------------------- #


def render_markdown(report: WeeklyReviewReport) -> str:
    lines: list[str] = []
    lines.append(f"# Optimizer Weekly Review")
    lines.append("")
    lines.append(f"client={report.client_id} window={report.window_days}d")
    lines.append(f"generated_at={report.generated_at.isoformat()}")
    lines.append("")

    # ----- Cost -------------------------------------------------------- #
    lines.append("## Cost")
    lines.append("")
    cost = report.cost
    cpac = cost.get("cost_per_active_contact_cents", 0.0)
    lines.append(
        f"- Total spend (window): {cost.get('total_cost_cents', 0)}c "
        f"across {cost.get('total_contacts_with_activity', 0)} active contacts."
    )
    lines.append(
        f"- Cost-per-active-contact: {cpac:.3f}c (target <= 0.200c)."
    )
    per_tier = cost.get("per_tier_cost_cents") or {}
    if per_tier:
        lines.append("- Per-tier:")
        for tier in sorted(per_tier.keys()):
            lines.append(f"    - Tier {tier}: {per_tier[tier]}c")
    per_adapter = cost.get("per_adapter_cost_cents") or {}
    if per_adapter:
        lines.append("- Top adapters by spend:")
        items = sorted(per_adapter.items(), key=lambda kv: -kv[1])[:5]
        for adapter, c in items:
            lines.append(f"    - {adapter}: {c}c")
    lines.append("")

    # ----- Reply rate -------------------------------------------------- #
    lines.append("## Reply Rate")
    lines.append("")
    rr = report.reply_rate
    pct = rr.get("rate", 0.0) * 100
    lines.append(
        f"- {rr.get('replies', 0)} replies / {rr.get('sends', 0)} sends "
        f"= {pct:.1f}% reply rate."
    )
    lines.append("")

    # ----- Recommendations -------------------------------------------- #
    lines.append("## Pending Recommendations")
    lines.append("")
    lines.append(
        f"- {report.pending_recommendations} pending; "
        f"approve / reject via /api/optimizer/recommendations/<id>/approve."
    )
    lines.append("")

    # ----- Escalations ------------------------------------------------- #
    lines.append("## Open Escalations")
    lines.append("")
    lines.append(
        f"- {report.open_escalations} open; triage via "
        f"/api/inbox/escalations/<id>/resolve."
    )
    lines.append("")

    # ----- Cool-off queue --------------------------------------------- #
    lines.append("## Cool-off Queue")
    lines.append("")
    lines.append(
        f"- {report.cooling_off_count} contacts in cooling_off; "
        f"{report.ready_to_re_enter_count} ready to re-enter "
        f"(cool_off_until elapsed)."
    )
    lines.append("")

    return "\n".join(lines)
