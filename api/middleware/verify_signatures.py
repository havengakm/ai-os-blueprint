"""Auth helpers: cron-secret header + HMAC webhook signature.

Two FastAPI Depends factories live here, plus a low-level HMAC helper.

- ``cron_secret_dep()`` — gates HTTP cron-trigger endpoints on the
  ``X-Cron-Secret`` header matching ``settings.cron_secret``.
- ``verify_webhook_signature(secret_field)`` — gates ESP / LinkedIn
  webhook endpoints on the ``X-Webhook-Signature`` header matching
  HMAC-SHA256(raw_body, settings.<secret_field>).

Both factories fail closed: empty configured secret rejects all requests.

Naming note (Plan 2 Task 2.0.1): ``cron_secret_dep`` was renamed from
the prior ``require_cron_secret``. The old name read like a predicate
call (``require_cron_secret()``) but actually returned a Depends-factory
result — the rename makes the call shape explicit. Webhook factory
follows the same shape so the two endpoints stay symmetric.
"""
from __future__ import annotations

import hashlib
import hmac

from fastapi import Depends, Header, HTTPException, Request, status

from config.settings import get_settings


def cron_secret_dep():
    """FastAPI Depends factory — requires ``X-Cron-Secret`` header to match
    ``settings.cron_secret``. Fails closed when ``settings.cron_secret`` is
    empty (rejects every request)."""
    async def _verify(x_cron_secret: str | None = Header(default=None)):
        settings = get_settings()
        if not settings.cron_secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cron-secret auth disabled (server config)",
            )
        if not x_cron_secret or not hmac.compare_digest(
            x_cron_secret, settings.cron_secret,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing cron secret",
            )
    return Depends(_verify)


def verify_webhook_signature(secret_field: str):
    """FastAPI Depends factory — verifies ``X-Webhook-Signature`` header
    against hex-encoded HMAC-SHA256 of the raw request body, using
    ``settings.<secret_field>`` as the secret.

    Used by ESP webhooks (Smartlead, Instantly, PlusVibe.ai) and LinkedIn
    webhooks. The secret_field is the name of an attribute on the
    ``Settings`` model (e.g. ``"smartlead_webhook_secret"``).

    Fail-closed semantics:
      - secret_field unknown / unset / empty value → reject every request
      - missing header → reject
      - non-matching signature → reject

    The factory looks up the secret at request time (not factory-call
    time) so config changes take effect on the next request.
    """
    async def _verify(
        request: Request,
        x_webhook_signature: str | None = Header(default=None),
    ):
        settings = get_settings()
        secret = getattr(settings, secret_field, "") or ""
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Webhook auth disabled (server config: {secret_field} unset)",
            )
        body = await request.body()
        if not verify_hmac_signature(body, x_webhook_signature or "", secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing webhook signature",
            )
    return Depends(_verify)


def verify_hmac_signature(
    payload: bytes,
    received_signature: str,
    secret: str,
) -> bool:
    """Constant-time HMAC-SHA256 signature check.

    Returns False (not raising) on any auth-failure shape: empty signature,
    empty secret, length mismatch, or content mismatch. Callers raise the
    HTTP error themselves so the response body matches FastAPI conventions.
    """
    if not received_signature or not secret:
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received_signature)
