import logging
import os
import sys


def get_logger(name: str) -> logging.Logger:
    """
    Return a configured logger.

    Each service (Gateway, Worker, CLI, Mongo Init)
    calls this once.
    """

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    level = os.getenv("LOG_LEVEL", "INFO").upper()

    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-18s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)

    handler.setFormatter(formatter)

    logger.addHandler(handler)

    logger.propagate = False

    return logger