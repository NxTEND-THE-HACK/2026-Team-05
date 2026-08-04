"""Recognition worker entrypoint."""

from __future__ import annotations

import logging

from .config import Settings
from .observability.logging import configure_logging


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    logging.getLogger(__name__).info(
        "recognition worker configured camera_id=%s source=%s",
        settings.camera_id,
        settings.camera_source,
    )


if __name__ == "__main__":
    main()
