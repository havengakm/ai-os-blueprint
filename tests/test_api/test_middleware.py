import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_middleware(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "the-secret")

    from config.settings import get_settings
    get_settings.cache_clear()

    from api.middleware.verify_signatures import cron_secret_dep

    app = FastAPI()

    @app.post("/protected", dependencies=[cron_secret_dep()])
    async def protected():
        return {"ok": True}

    return app


def test_rejects_missing_secret(app_with_middleware):
    client = TestClient(app_with_middleware)
    r = client.post("/protected")
    assert r.status_code == 401


def test_rejects_wrong_secret(app_with_middleware):
    client = TestClient(app_with_middleware)
    r = client.post("/protected", headers={"X-Cron-Secret": "wrong"})
    assert r.status_code == 401


def test_accepts_correct_secret(app_with_middleware):
    client = TestClient(app_with_middleware)
    r = client.post("/protected", headers={"X-Cron-Secret": "the-secret"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@pytest.fixture
def app_with_empty_cron_secret(monkeypatch):
    """Daemon-only deployment shape (Plan 1.5 Task 1.5.4): CRON_SECRET unset."""
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    # CRON_SECRET deliberately unset; the autouse env-isolation fixture
    # already delenv'd every Settings field, so cron_secret defaults to "".

    from config.settings import get_settings
    get_settings.cache_clear()

    from api.middleware.verify_signatures import cron_secret_dep

    app = FastAPI()

    @app.post("/protected", dependencies=[cron_secret_dep()])
    async def protected():
        return {"ok": True}

    return app


def test_rejects_all_requests_when_cron_secret_empty(app_with_empty_cron_secret):
    """When cron_secret defaults to '' (daemon-only deployment), the HTTP
    cron-trigger endpoint must reject every request, even ones bearing an
    empty header. Locks down the security surface introduced by making
    cron_secret optional."""
    client = TestClient(app_with_empty_cron_secret)

    # No header.
    assert client.post("/protected").status_code == 401
    # Empty header.
    assert client.post(
        "/protected", headers={"X-Cron-Secret": ""}
    ).status_code == 401
    # Anything-non-empty header.
    assert client.post(
        "/protected", headers={"X-Cron-Secret": "anything"}
    ).status_code == 401


# --------------------------------------------------------------------------- #
# verify_webhook_signature — Plan 2 Task 2.0.1                                 #
# --------------------------------------------------------------------------- #
#
# Sibling to cron_secret_dep used by ESP webhooks (Smartlead, Instantly,
# PlusVibe.ai) and LinkedIn webhooks. Verifies hex-encoded HMAC-SHA256 of
# the raw request body against settings.<secret_field>.

import hashlib
import hmac


def _hmac_hex(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@pytest.fixture
def app_with_webhook(monkeypatch):
    """Spin up an app whose /webhook route is gated by verify_webhook_signature
    against settings.smartlead_webhook_secret. settings.smartlead_webhook_secret
    is set to "wh-secret" via env."""
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("SMARTLEAD_WEBHOOK_SECRET", "wh-secret")

    from config.settings import get_settings
    get_settings.cache_clear()

    from api.middleware.verify_signatures import verify_webhook_signature

    app = FastAPI()

    @app.post(
        "/webhook",
        dependencies=[verify_webhook_signature("smartlead_webhook_secret")],
    )
    async def webhook():
        return {"received": True}

    return app


def test_webhook_accepts_valid_signature(app_with_webhook):
    client = TestClient(app_with_webhook)
    payload = b'{"event":"sent","message_id":"abc-123"}'
    signature = _hmac_hex(payload, "wh-secret")
    r = client.post(
        "/webhook",
        content=payload,
        headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json() == {"received": True}


def test_webhook_rejects_missing_signature(app_with_webhook):
    client = TestClient(app_with_webhook)
    r = client.post("/webhook", content=b'{"x":1}')
    assert r.status_code == 401


def test_webhook_rejects_wrong_signature(app_with_webhook):
    client = TestClient(app_with_webhook)
    payload = b'{"x":1}'
    r = client.post(
        "/webhook",
        content=payload,
        headers={"X-Webhook-Signature": "deadbeef", "Content-Type": "application/json"},
    )
    assert r.status_code == 401


def test_webhook_rejects_signature_computed_with_wrong_secret(app_with_webhook):
    """The signature is computed correctly but with a secret that doesn't
    match the env value — verifies the secret is actually being looked up
    from settings, not just any provided HMAC hex."""
    client = TestClient(app_with_webhook)
    payload = b'{"x":1}'
    signature = _hmac_hex(payload, "wrong-secret")  # not "wh-secret"
    r = client.post(
        "/webhook",
        content=payload,
        headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"},
    )
    assert r.status_code == 401


@pytest.fixture
def app_with_webhook_empty_secret(monkeypatch):
    """Deployment shape where SMARTLEAD_WEBHOOK_SECRET is unset — secret
    defaults to ''. The webhook endpoint must reject every request."""
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    # SMARTLEAD_WEBHOOK_SECRET deliberately unset.

    from config.settings import get_settings
    get_settings.cache_clear()

    from api.middleware.verify_signatures import verify_webhook_signature

    app = FastAPI()

    @app.post(
        "/webhook",
        dependencies=[verify_webhook_signature("smartlead_webhook_secret")],
    )
    async def webhook():
        return {"received": True}

    return app


def test_webhook_rejects_all_when_secret_unset(app_with_webhook_empty_secret):
    """Mirrors test_rejects_all_requests_when_cron_secret_empty: when the
    configured secret is '', every request is rejected, even one bearing
    an empty signature header."""
    client = TestClient(app_with_webhook_empty_secret)

    payload = b'{"x":1}'
    # No header.
    assert client.post("/webhook", content=payload).status_code == 401
    # Empty header.
    assert client.post(
        "/webhook",
        content=payload,
        headers={"X-Webhook-Signature": ""},
    ).status_code == 401
    # Anything-non-empty header.
    assert client.post(
        "/webhook",
        content=payload,
        headers={"X-Webhook-Signature": "deadbeef"},
    ).status_code == 401


def test_webhook_signature_factory_rejects_typo_secret_field():
    """Calling verify_webhook_signature with a secret_field that doesn't
    exist on Settings raises a clear error at request time (not a silent
    pass). Locks the typo footgun."""
    import os
    os.environ["CLIENT_ID"] = "test"
    os.environ["SUPABASE_URL"] = "https://test.supabase.co"
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test"
    os.environ["ANTHROPIC_API_KEY"] = "test"

    from config.settings import get_settings
    get_settings.cache_clear()

    from api.middleware.verify_signatures import verify_webhook_signature

    app = FastAPI()

    @app.post(
        "/webhook",
        dependencies=[verify_webhook_signature("nonexistent_field")],
    )
    async def webhook():
        return {"received": True}

    client = TestClient(app)
    payload = b'{"x":1}'
    signature = _hmac_hex(payload, "anything")
    r = client.post(
        "/webhook",
        content=payload,
        headers={"X-Webhook-Signature": signature},
    )
    # Either 401 (treated as empty secret -> reject all) or 500 — both lock
    # the typo footgun. We accept 401 since that's the safer fail-closed path.
    assert r.status_code in (401, 500)
