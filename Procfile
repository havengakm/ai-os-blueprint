# AIOS Procfile — CANONICAL source of truth for Railway multi-process deploy.
# Railway's Nixpacks builder reads this file to spawn one service per line.
# The `[[services]]` block in `railway.toml` is intentionally commented out
# (see note there) because running both sources caused the worker to silently
# not materialise on first deploy.
#
# web:    FastAPI app (public pipeline endpoints, healthcheck)
# worker: Scout daemon running the nightly pipeline (Task 16.6)
web: uvicorn api.asgi:app --host 0.0.0.0 --port $PORT
worker: uv run python -m aios.daemon
