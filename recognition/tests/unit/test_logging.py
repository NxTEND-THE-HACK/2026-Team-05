import logging

from gesture_recognition.observability.logging import configure_logging


def test_configure_logging_accepts_level() -> None:
    configure_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG
