"""HTTP MJPEG input with reconnect and latest-frame semantics."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from threading import Event, Thread, current_thread
from time import monotonic
from urllib.request import urlopen

from .latest import LatestFrameStore
from ..domain.models import CapturedFrame

logger = logging.getLogger(__name__)

UrlOpener = Callable[..., object]


def iter_jpegs(stream: object, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    """Extract JPEG images from an MJPEG byte stream.

    The camera may include multipart boundaries or omit them. JPEG start/end
    markers are therefore used as the framing fallback supported by the MVP.
    """

    buffer = bytearray()
    while True:
        chunk = stream.read(chunk_size)  # type: ignore[attr-defined]
        if not chunk:
            return
        buffer.extend(chunk)

        while True:
            start = buffer.find(b"\xff\xd8")
            if start < 0:
                if len(buffer) > 1:
                    del buffer[:-1]
                break

            end = buffer.find(b"\xff\xd9", start + 2)
            if end < 0:
                if start:
                    del buffer[:start]
                break

            finish = end + 2
            yield bytes(buffer[start:finish])
            del buffer[:finish]


class MjpegFrameSource:
    """Read an HTTP MJPEG stream on a background thread."""

    def __init__(
        self,
        url: str,
        *,
        reconnect_initial_seconds: float = 1.0,
        reconnect_max_seconds: float = 30.0,
        request_timeout_seconds: float = 5.0,
        opener: UrlOpener = urlopen,
    ) -> None:
        if not url:
            raise ValueError("MJPEG URL must not be empty")
        if reconnect_initial_seconds <= 0:
            raise ValueError("reconnect_initial_seconds must be positive")
        if reconnect_max_seconds < reconnect_initial_seconds:
            raise ValueError(
                "reconnect_max_seconds must be greater than or equal to "
                "reconnect_initial_seconds"
            )
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")

        self.url = url
        self._initial_backoff = reconnect_initial_seconds
        self._max_backoff = reconnect_max_seconds
        self._request_timeout = request_timeout_seconds
        self._opener = opener
        self._store = LatestFrameStore()
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run,
            name=f"mjpeg-{self.url}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread is not current_thread():
            self._thread.join(timeout=2.0)
        self._thread = None

    def read_latest(self, after_sequence: int = 0) -> CapturedFrame | None:
        return self._store.read_latest(after_sequence)

    def _run(self) -> None:
        backoff = self._initial_backoff
        while not self._stop_event.is_set():
            try:
                with self._opener(self.url, timeout=self._request_timeout) as stream:  # type: ignore[union-attr]
                    logger.info("MJPEG connected url=%s", self.url)
                    for jpeg in iter_jpegs(stream):
                        if self._stop_event.is_set():
                            return
                        self._store.put(jpeg)
                raise ConnectionError("MJPEG stream ended")
            except Exception as exc:  # noqa: BLE001 - reconnect boundary
                if self._stop_event.is_set():
                    return
                logger.warning(
                    "MJPEG disconnected url=%s error=%s retry_in=%.1fs",
                    self.url,
                    exc,
                    backoff,
                )
                self._wait(backoff)
                backoff = min(backoff * 2, self._max_backoff)
            else:
                backoff = self._initial_backoff

    def _wait(self, seconds: float) -> None:
        deadline = monotonic() + seconds
        while not self._stop_event.is_set() and monotonic() < deadline:
            self._stop_event.wait(timeout=min(0.2, deadline - monotonic()))
