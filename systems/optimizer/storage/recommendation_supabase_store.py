"""SupabaseRecommendationStore — real persistence for the optimizer
recommendation engine.

Conforms to ``systems.optimizer.recommendations.RecommendationStore``.
Backed by the migration 022 ``optimizer_recommendation`` table.

ISO-string timestamp conversion: the Supabase client returns timestamp
columns as ISO-8601 strings; this store parses them back to ``datetime``
on read so callers always get a typed value.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from systems.optimizer.recommendations import RecommendationRow
from aios.foundation.storage import SupabaseLike


def _parse_iso(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # supabase returns "+00:00" or "Z" — fromisoformat handles +00:00
        # natively in 3.11+; normalise trailing 'Z'.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def _to_row(payload: dict) -> RecommendationRow:
    return RecommendationRow(
        id=payload["id"],
        client_id=payload["client_id"],
        category=payload["category"],
        payload=payload.get("payload") or {},
        reasoning=payload.get("reasoning") or "",
        confidence=(
            float(payload["confidence"])
            if payload.get("confidence") is not None
            else None
        ),
        status=payload["status"],
        created_at=_parse_iso(payload.get("created_at")) or datetime.min,
        reviewed_by=payload.get("reviewed_by"),
        reviewed_at=_parse_iso(payload.get("reviewed_at")),
        applied_at=_parse_iso(payload.get("applied_at")),
        apply_error=payload.get("apply_error"),
    )


class SupabaseRecommendationStore:
    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def insert(self, row: RecommendationRow) -> str:
        (
            self._client.table("optimizer_recommendation")
            .insert(
                {
                    "id": row.id,
                    "client_id": row.client_id,
                    "category": row.category,
                    "payload": row.payload,
                    "reasoning": row.reasoning,
                    "confidence": row.confidence,
                    "status": row.status,
                    "created_at": row.created_at.isoformat(),
                }
            )
            .execute()
        )
        return row.id

    async def get(self, rec_id: str) -> RecommendationRow | None:
        resp = (
            self._client.table("optimizer_recommendation")
            .select(
                "id, client_id, category, payload, reasoning, confidence, "
                "status, created_at, reviewed_by, reviewed_at, applied_at, "
                "apply_error"
            )
            .eq("id", rec_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        return _to_row(rows[0])

    async def update_status(
        self,
        rec_id: str,
        *,
        status: str,
        reviewed_by: str | None = None,
        reviewed_at: datetime | None = None,
        applied_at: datetime | None = None,
        apply_error: str | None = None,
    ) -> None:
        patch: dict[str, Any] = {"status": status}
        if reviewed_by is not None:
            patch["reviewed_by"] = reviewed_by
        if reviewed_at is not None:
            patch["reviewed_at"] = reviewed_at.isoformat()
        if applied_at is not None:
            patch["applied_at"] = applied_at.isoformat()
        if apply_error is not None:
            patch["apply_error"] = apply_error
        (
            self._client.table("optimizer_recommendation")
            .update(patch)
            .eq("id", rec_id)
            .execute()
        )

    async def list_pending(self, client_id: str) -> list[RecommendationRow]:
        resp = (
            self._client.table("optimizer_recommendation")
            .select(
                "id, client_id, category, payload, reasoning, confidence, "
                "status, created_at, reviewed_by, reviewed_at, applied_at, "
                "apply_error"
            )
            .eq("client_id", client_id)
            .eq("status", "pending")
            .order("created_at", desc=True)
            .execute()
        )
        return [_to_row(r) for r in (resp.data or [])]

    async def list_pending_older_than(
        self, *, cutoff: datetime,
    ) -> list[RecommendationRow]:
        resp = (
            self._client.table("optimizer_recommendation")
            .select(
                "id, client_id, category, payload, reasoning, confidence, "
                "status, created_at, reviewed_by, reviewed_at, applied_at, "
                "apply_error"
            )
            .eq("status", "pending")
            .lt("created_at", cutoff.isoformat())
            .execute()
        )
        return [_to_row(r) for r in (resp.data or [])]
