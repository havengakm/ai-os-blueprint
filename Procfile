# AIOS Procfile
# web: the FastAPI app (public pipeline endpoints, healthcheck)
# worker: Scout daemon running the nightly pipeline (Task 16.6)
web: uvicorn api.main:app --host 0.0.0.0 --port $PORT
worker: uv run python -m aios.daemon
