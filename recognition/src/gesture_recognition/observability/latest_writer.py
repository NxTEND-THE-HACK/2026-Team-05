"""Asynchronous latest-only writers for non-critical monitor output."""

from __future__ import annotations

import logging
from collections.abc import Callable
from threading import Condition, Thread, current_thread
from time import monotonic
from typing import Generic, TypeVar


logger = logging.getLogger(__name__)
Task = TypeVar("Task")


class LatestTaskWriter(Generic[Task]):
    """Write only the newest pending task on a rate-limited daemon thread.

    The producer never waits for the writer. Submitting a task replaces any
    older task that has not started yet, so a slow output sink cannot create an
    unbounded backlog or block the recognition loop.
    """

    def __init__(
        self,
        writer: Callable[[Task], None],
        *,
        max_fps: float,
    ) -> None:
        if max_fps <= 0:
            raise ValueError("max_fps must be positive")
        self._writer = writer
        self._interval_seconds = 1.0 / max_fps
        self._condition = Condition()
        self._pending: Task | None = None
        self._stopping = False
        self._thread: Thread | None = None

    def start(self) -> None:
        """Start the writer thread if it is not already running."""

        with self._condition:
            if self._thread is not None and self._thread.is_alive():
                return
            self._pending = None
            self._stopping = False
            self._thread = Thread(
                target=self._run,
                name="latest-task-writer",
                daemon=True,
            )
            self._thread.start()

    def submit(self, task: Task) -> bool:
        """Replace the pending task, returning false when not running."""

        with self._condition:
            if self._stopping or self._thread is None or not self._thread.is_alive():
                return False
            self._pending = task
            self._condition.notify()
            return True

    def stop(self) -> None:
        """Stop the thread and discard work that has not started yet."""

        with self._condition:
            thread = self._thread
            if thread is None:
                return
            self._stopping = True
            self._pending = None
            self._condition.notify_all()
        if thread is not current_thread():
            thread.join()
        with self._condition:
            if self._thread is thread:
                self._thread = None

    def _run(self) -> None:
        next_write_at = 0.0
        while True:
            with self._condition:
                while True:
                    if self._stopping:
                        return
                    if self._pending is None:
                        self._condition.wait()
                        continue
                    wait_seconds = next_write_at - monotonic()
                    if wait_seconds > 0:
                        self._condition.wait(timeout=wait_seconds)
                        continue
                    task = self._pending
                    self._pending = None
                    break
            try:
                self._writer(task)
            except Exception:  # noqa: BLE001 - output must not stop recognition
                logger.exception("latest task writer failed")
            next_write_at = monotonic() + self._interval_seconds
