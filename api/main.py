"""FastAPI app factory + entrypoint."""
from __future__ import annotations

import logging

import structlog
from fastapi import FastAPI

from config.settings import get_settings
from api.routers import health


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

    return app


app = create_app()
