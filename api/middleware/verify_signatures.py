"""Auth helpers: cron-secret header + HMAC webhook signature."""
from __future__ import annotations

import hmac
import hashlib

from fastapi import Depends, Header, HTTPException, status

from config.settings import get_settings


def require_cron_secret():
    """FastAPI Depends factory — requires X-Cron-Secret header to match CRON_SECRET env."""
    async def _verify(x_cron_secret: str | None = Header(default=None)):
        settings = get_settings()
        if not x_cron_secret or not hmac.compare_digest(x_cron_secret, settings.cron_secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing cron secret")
    return Depends(_verify)


def verify_hmac_signature(payload: bytes, received_signature: str, secret: str) -> bool:
    """Constant-time HMAC-SHA256 signature check."""
    if not received_signature or not secret:
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received_signature)
