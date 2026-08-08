"""
Worker application entry point.
"""

from __future__ import annotations

import signal
import sys

from shared.logging import get_logger

from worker.app.worker import Worker

logger = get_logger("worker.main")

worker = Worker()


def shutdown(
    signum: int,
    frame,
) -> None:
    """
    Handle graceful shutdown.
    """

    logger.info(
        "Received signal %s. Shutting down Worker...",
        signum,
    )

    worker.stop()

    sys.exit(0)


def main() -> None:
    """
    Start the Worker service.
    """

    signal.signal(
        signal.SIGINT,
        shutdown,
    )

    signal.signal(
        signal.SIGTERM,
        shutdown,
    )

    logger.info("Starting Worker...")

    worker.start()


if __name__ == "__main__":
    main()