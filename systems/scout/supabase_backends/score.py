"""SupabaseScoreBackend — real persistence for ScoreStage.

Conforms to ``systems.scout.pipeline.score_stage.ScoreStorageBackend``.
"""
from __future__ import annotations

from typing import Any

from systems.scout.pipeline.score_stage import ContactToScore
from systems.scout.supabase_backends._base import SupabaseLike, insert_decision_log_row


class SupabaseScoreBackend:
    """Real Supabase-backed implementation of the score-stage backend."""

    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def get_client_config(self, client_id: str) -> dict[str, Any]:
        """Fetch weights + tier_thresholds + icp from client_config +
        icp_definitions. Returns a dict with the keys the scoring module
        expects (``weights``, ``tier_thresholds``, ``icp``)."""
        cfg_resp = (
            self._client.table("client_config")
            .select("weights, tier_thresholds")
            .eq("client_id", client_id)
            .limit(1)
            .execute()
        )
        cfg_rows = cfg_resp.data or []
        cfg = cfg_rows[0] if cfg_rows else {}

        # Pull a single icp_definitions row (one niche per client in Plan 1).
        icp_resp = (
            self._client.table("icp_definitions")
            .select(
                "industries, titles, employee_min, employee_max, "
                "geographies, blacklist_companies, blacklist_domains"
            )
            .eq("client_id", client_id)
            .limit(1)
            .execute()
        )
        icp_rows = icp_resp.data or []
        icp = icp_rows[0] if icp_rows else {}

        return {
            "weights": cfg.get("weights") or {},
            "tier_thresholds": cfg.get("tier_thresholds") or {},
            "icp": icp,
        }

    async def get_contacts_for_scoring(
        self,
        client_id: str,
        *,
        phase: str,
        limit: int | None = None,
    ) -> list[ContactToScore]:
        """Return contacts eligible for the given phase.

        v1: icp_score IS NULL
        v2: status = 'enriched' AND icp_score IS NOT NULL
        """
        cols = (
            "id, industry, title, employees, geography, email, email_verified, "
            "linkedin_url, phone, raw_data, research_data"
        )
        query = (
            self._client.table("contacts")
            .select(cols)
            .eq("client_id", client_id)
        )
        if phase == "v1":
            query = query.is_("icp_score", "null")
        elif phase == "v2":
            query = query.eq("status", "enriched").not_.is_("icp_score", "null")
        else:
            raise ValueError(f"unknown phase: {phase!r}")

        if limit is not None:
            query = query.limit(limit)
        resp = query.execute()

        out: list[ContactToScore] = []
        for row in resp.data or []:
            out.append(
                ContactToScore(
                    contact_id=row["id"],
                    industry=row.get("industry"),
                    title=row.get("title"),
                    employees=row.get("employees"),
                    geography=row.get("geography"),
                    email=row.get("email"),
                    email_verified=bool(row.get("email_verified") or False),
                    linkedin_url=row.get("linkedin_url"),
                    phone=row.get("phone"),
                    raw_data=row.get("raw_data") or {},
                    research_data=row.get("research_data") or {},
                )
            )
        return out

    async def update_contact_score(
        self,
        client_id: str,
        contact_id: str,
        *,
        score: int,
        tier: str,
        phase: str,
    ) -> None:
        """Persist score + tier + phase-dependent status transition."""
        payload: dict[str, Any] = {
            "icp_score": score,
            "icp_tier": tier,
        }
        if phase == "v1":
            payload["status"] = "screened"
        (
            self._client.table("contacts")
            .update(payload)
            .eq("client_id", client_id)
            .eq("id", contact_id)
            .execute()
        )

    async def archive_contact(
        self,
        client_id: str,
        contact_id: str,
        *,
        reason: str,
    ) -> None:
        """Set status='archived' and embed the reason in raw_data."""
        # Read existing raw_data so we can preserve it.
        resp = (
            self._client.table("contacts")
            .select("raw_data")
            .eq("client_id", client_id)
            .eq("id", contact_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        raw_data = (rows[0].get("raw_data") if rows else None) or {}
        raw_data["archive_reason"] = reason

        (
            self._client.table("contacts")
            .update({"status": "archived", "raw_data": raw_data})
            .eq("client_id", client_id)
            .eq("id", contact_id)
            .execute()
        )

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
        insert_decision_log_row(
            self._client,
            client_id=client_id,
            decision_type=decision_type,
            decision=decision,
            context=context,
            reasoning=reasoning,
            confidence=confidence,
        )
