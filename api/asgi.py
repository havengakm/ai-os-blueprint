"""ASGI module-level app for production deployment.

Plan 2 Task 2.0.4: this module exists to keep ``api/main.py`` import-side-
effect-free for tests. Production servers (uvicorn, gunicorn, Railway) point
at ``api.asgi:app``. Tests import ``api.main.create_app`` from inside
a fixture so env is patched first.
"""
from __future__ import annotations

from api.main import create_app

app = create_app()
