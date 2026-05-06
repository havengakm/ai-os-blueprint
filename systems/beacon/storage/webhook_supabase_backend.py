"""SupabaseWebhookBackend — real persistence for Beacon webhook ingest.

Conforms to ``systems.beacon.pipeline.webhook_handler.BeaconWebhookBackend``.

Three operations:
- ``find_send_log_by_esp_message_id`` — correlate inbound webhook events
  to an existing ``outreach_send_log`` row via ``esp_message_id``.
- ``update_send_log_status`` — patch status / error / raw_data when an
  ESP delivery event arrives.
- ``insert_reply`` — append to ``outreach_reply`` for ``reply_received``
  events. ``classification`` is left NULL — Phase 3's Haiku classifier
  picks up unclassified rows via the partial index
  ``idx_reply_pending_classification``.
"""
from __future__ import annotations

from uuid import uuid4

from systems.beacon.pipeline.webhook_handler import SendLogRef
from aios.foundation.storage import SupabaseLike


class SupabaseWebhookBackend:
    def __init__(self, client: SupabaseLike) -> None:
        self._client = client

    async def find_send_log_by_esp_message_id(
        self, esp_message_id: str
    ) -> SendLogRef | None:
        resp = (
            self._client.table("outreach_send_log")
            .select("id, client_id, contact_id")
            .eq("esp_message_id", esp_message_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        row = rows[0]
        return SendLogRef(
            send_log_id=row["id"],
            contact_id=row["contact_id"],
            client_id=row["client_id"],
        )

    async def update_send_log_status(
        self,
        send_log_id: str,
        status: str,
        error: str | None,
        raw_data: dict,
    ) -> None:
        (
            self._client.table("outreach_send_log")
            .update(
                {
                    "status": status,
                    "error": error,
                    "raw_data": raw_data,
                }
            )
            .eq("id", send_log_id)
            .execute()
        )

    async def insert_reply(
        self,
        client_id: str,
        contact_id: str,
        send_log_id: str | None,
        from_email: str,
        subject: str | None,
        body: str,
        replied_to_message_id: str | None,
        raw_data: dict,
    ) -> str:
        new_id = str(uuid4())
        (
            self._client.table("outreach_reply")
            .insert(
                {
                    "id": new_id,
                    "client_id": client_id,
                    "contact_id": contact_id,
                    "send_log_id": send_log_id,
                    "from_email": from_email,
                    "subject": subject,
                    "body": body,
                    "replied_to_message_id": replied_to_message_id,
                    "raw_data": raw_data,
                    "classification": None,
                }
            )
            .execute()
        )
        return new_id
