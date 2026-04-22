"""``python -m aios.daemon`` entry point (Task 16.6).

Wires logging, runs ``run_daemon()`` on the asyncio event loop, and exits
cleanly on SIGTERM / SIGINT. Signal handling is installed inside
``run_daemon``; ``KeyboardInterrupt`` at this layer just falls through to
exit code 0 if raised outside the async loop.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from aios.daemon.main import run_daemon


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> int:
    _configure_logging()
    try:
        asyncio.run(run_daemon())
    except KeyboardInterrupt:
        # Defensive: run_daemon catches SIGINT via event, but a Ctrl-C
        # before the loop installs its handler reaches here.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
