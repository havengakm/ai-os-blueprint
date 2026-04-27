"""FastAPI app factory.

Plan 2 Task 2.0.4: this module is the FACTORY ONLY. The module-level
``app = create_app()`` was moved to ``api/asgi.py`` to remove a
test-time foot-gun: any test that imported ``api.main`` at the top
level would trigger ``create_app()`` → ``get_settings()`` before any
monkeypatch fired, which raised ``ValidationError`` on missing env.

If you're adding deployment configuration, point at ``api.asgi:app``
(see ``Procfile`` and ``railway.toml``). If you're constructing an app
in tests, call ``create_app()`` from inside a fixture so env is already
patched.
"""
from __future__ import annotations

import logging

import structlog
from fastapi import FastAPI

from api.deps import get_beacon_webhook_handler, get_escalation_runtime
from api.routers import beacon_webhooks, health, inbox, pipeline
from config.settings import get_settings


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=level.upper())
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ]
    )


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging(settings.log_level)

    app = FastAPI(
        title="AI OS Blueprint",
        description="Productised AI Operating System",
        version="0.1.0",
    )

    app.include_router(health.router)
    app.include_router(pipeline.router)
    app.include_router(beacon_webhooks.router)
    app.include_router(inbox.router)

    # Beacon webhook handler — production wiring. The router's default
    # ``get_webhook_handler`` raises so unwired deployments fail loud;
    # this override points it at the real Supabase-backed handler.
    # Tests replace this with a fake-backed handler via the same dict.
    app.dependency_overrides[beacon_webhooks.get_webhook_handler] = (
        get_beacon_webhook_handler
    )
    app.dependency_overrides[inbox.get_escalation_runtime] = (
        get_escalation_runtime
    )

    return app
