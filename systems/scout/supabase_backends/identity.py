"""SupabaseIdentityBackend — real persistence for IdentityStage.

Conforms to ``systems.scout.pipeline.identity.IdentityStorageBackend``.
"""
from __future__ import annotations

from typing import Any

from systems.scout.pipeline.identity import ContactRow
from systems.scout.supabase_backends._base import SupabaseLike, insert_decision_log_row


_ARCHIVED_STATUSES: tuple[str, ...] = (
    "archived",
    "archived_no_decision_maker",
    "killed",
)


class SupabaseIdentityBackend:
    """Real Supabase-backed implementation of the identity-stage backend."""

    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def get_eligible_contacts(
        self,
        client_id: str,
        *,
        archive_floor: int,
        limit: int | None = None,
    ) -> list[ContactRow]:
        """Return contacts with icp_score >= archive_floor, no identity
        resolved yet, and not already archived/killed."""
        query = (
            self._client.table("contacts")
            .select("id, company, company_domain, icp_score")
            .eq("client_id", client_id)
            .gte("icp_score", archive_floor)
            .is_("first_name", "null")
            .not_.in_("status", list(_ARCHIVED_STATUSES))
        )
        if limit is not None:
            query = query.limit(limit)
        resp = query.execute()

        out: list[ContactRow] = []
        for row in resp.data or []:
            out.append(
                ContactRow(
                    contact_id=row["id"],
                    company_name=row.get("company") or "",
                    company_domain=row.get("company_domain"),
                    icp_score=int(row.get("icp_score") or 0),
                )
            )
        return out

    async def update_contact_identity(
        self,
        client_id: str,
        contact_id: str,
        *,
        first_name: str,
        last_name: str,
        title: str | None,
        email: str,
        linkedin_url: str | None,
        identity_source: str,
    ) -> None:
        """Persist resolved identity fields on a contact row."""
        payload: dict[str, Any] = {
            "first_name": first_name,
            "last_name": last_name,
            "title": title,
            "email": email,
            "linkedin_url": linkedin_url,
        }
        # Merge identity_source into raw_data so we can trace the waterfall hit.
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
        raw_data["identity_source"] = identity_source
        payload["raw_data"] = raw_data

        (
            self._client.table("contacts")
            .update(payload)
            .eq("client_id", client_id)
            .eq("id", contact_id)
            .execute()
        )

    async def archive_contact_no_decision_maker(
        self,
        client_id: str,
        contact_id: str,
    ) -> None:
        """Set contact.status = 'archived_no_decision_maker'."""
        (
            self._client.table("contacts")
            .update({"status": "archived_no_decision_maker"})
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
