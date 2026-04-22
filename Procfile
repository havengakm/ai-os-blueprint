# AIOS Procfile
# web: the FastAPI app (public pipeline endpoints, healthcheck)
# worker (Task 16.6, pending): Scout daemon running the nightly pipeline
#     worker: uv run python -m aios.daemon
web: uvicorn api.main:app --host 0.0.0.0 --port $PORT
