"""ZeroBounce email-verification adapter.

Calls GET /v2/validate and returns deliverability status plus metadata.
Every paid call is recorded in EnrichResult.cost_cents so the orchestrator
can sum costs to enforce tier budget caps. No retries — failed calls
propagate immediately to avoid multiplying spend.

Pricing: $0.008/credit → rounds up to 1 cent per call.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from config.settings import get_settings
from systems.scout.enrich.base import EnrichResult


logger = logging.getLogger(__name__)

ZEROBOUNCE_VALIDATE_URL = "https://api.zerobounce.net/v2/validate"


def _map_reason(status: str) -> str:
    """Map ZeroBounce status string to a canonical reason label."""
    if status == "valid":
        return "verified"
    if status == "catch-all":
        return "catch_all_domain"
    if status in ("invalid", "spamtrap", "abuse", "do_not_mail"):
        return f"unsafe:{status}"
    if status == "unknown":
        return "indeterminate"
    if status == "disposable":
        return "disposable"
    return f"unknown_status:{status}"


class ZeroBounceAdapter:
    """ZeroBounce email-verification adapter. name='zerobounce'."""

    name: str = "zerobounce"
    cost_cents_per_call: int = 1    # $0.008/credit, rounded up

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        """http_client lets tests inject a mock; production passes None."""
        self._http_client = http_client

    async def enrich(
        self,
        contact: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> EnrichResult:
        """Verify the contact's email via ZeroBounce /v2/validate.

        Short-circuit paths (no network call, cost_cents=0):
        - dry_run=True
        - ZEROBOUNCE_API_KEY not configured
        - contact has no/blank email

        On a completed API call (any valid response), cost_cents=1.
        Infrastructure errors propagate — no retry.
        """
        contact_id = contact.get("contact_id", "<unknown>")

        # --- dry run ---
        if dry_run:
            logger.debug("zerobounce dry_run contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=True,
                data={},
                cost_cents=0,
                reason="dry_run_skipped",
            )

        # --- key guard ---
        settings = get_settings()
        api_key = settings.zerobounce_api_key
        if not api_key:
            logger.warning("zerobounce no_api_key contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=False,
                data={},
                cost_cents=0,
                reason="no_api_key",
            )

        # --- email guard ---
        email = contact.get("email") or ""
        if not email.strip():
            logger.debug("zerobounce no_email contact_id=%s", contact_id)
            return EnrichResult(
                adapter_name=self.name,
                ok=False,
                data={},
                cost_cents=0,
                reason="no_email",
            )

        # --- API call ---
        client_provided = self._http_client is not None
        client = self._http_client or httpx.AsyncClient(timeout=30.0)
        try:
            params = {"api_key": api_key, "email": email}
            response = await client.get(ZEROBOUNCE_VALIDATE_URL, params=params)
            response.raise_for_status()  # propagates on 4xx/5xx — no retry
            body: dict[str, Any] = response.json()
        finally:
            if not client_provided:
                await client.aclose()

        # --- parse response ---
        status = (body.get("status") or "").lower()
        sub_status = body.get("sub_status") or ""
        mx_raw = body.get("mx_found", "false")
        mx_found = mx_raw is True or str(mx_raw).lower() == "true"
        smtp_provider: str | None = body.get("smtp_provider") or None

        reason = _map_reason(status)
        data: dict[str, Any] = {
            "email_verified": status == "valid",
            "email_catch_all": status == "catch-all",
            "zerobounce_status": status,
            "zerobounce_sub_status": sub_status,
            "mx_found": mx_found,
            "smtp_provider": smtp_provider,
        }

        logger.info(
            "zerobounce contact_id=%s status=%s reason=%s cost_cents=%d",
            contact_id, status, reason, self.cost_cents_per_call,
        )

        return EnrichResult(
            adapter_name=self.name,
            ok=True,
            data=data,
            cost_cents=self.cost_cents_per_call,
            reason=reason,
            raw_response=body,
        )
