"""Structured logging configuration.

Kept intentionally small: one consistent format for the whole backend so that
later phases (auth, realtime, security) can rely on greppable, timestamped logs.
"""

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Install a single stream handler with a consistent format."""
    root = logging.getLogger()
    if root.handlers:  # already configured (e.g. under uvicorn reload)
        return

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root.addHandler(handler)
    root.setLevel(level.upper())
