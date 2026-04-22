"""AIOS autonomous daemon (Task 16.6).

Long-running worker that iterates over active clients and runs the nightly
pipeline without human intervention. Entry point: ``aios.daemon.main.run_daemon``.
See ``python -m aios.daemon`` for the CLI.
"""
from __future__ import annotations

from aios.daemon.main import run_daemon

__all__ = ["run_daemon"]
