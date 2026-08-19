from threading import Event
from time import monotonic, sleep

import pytest

from gesture_recognition.observability.latest_writer import LatestTaskWriter


def _wait_until(predicate, timeout: float = 1.0) -> bool:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return True
        sleep(0.005)
    return predicate()


def test_latest_task_writer_replaces_pending_work() -> None:
    first_started = Event()
    release_first = Event()
    values: list[int] = []

    def write(value: int) -> None:
        values.append(value)
        if value == 1:
            first_started.set()
            release_first.wait(1.0)

    writer = LatestTaskWriter(write, max_fps=1000.0)
    writer.start()
    try:
        assert writer.submit(1)
        assert first_started.wait(1.0)
        assert writer.submit(2)
        assert writer.submit(3)
        release_first.set()
        assert _wait_until(lambda: values == [1, 3])
    finally:
        writer.stop()

    assert values == [1, 3]


def test_latest_task_writer_rejects_invalid_rate() -> None:
    with pytest.raises(ValueError):
        LatestTaskWriter(lambda _: None, max_fps=0)
