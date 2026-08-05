"""Process-wide logging setup."""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure concise logs for local runs and container output."""

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logging.basicConfig(
        level=root_logger.level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
