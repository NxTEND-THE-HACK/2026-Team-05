"""HTTP MJPEG input with reconnect and latest-frame semantics."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event, Lock, Thread, current_thread
from time import monotonic, sleep
from urllib.request import urlopen

from .latest import LatestFrameStore
from ..domain.models import CapturedFrame

logger = logging.getLogger(__name__)

UrlOpener = Callable[..., object]

DEFAULT_MJPEG_CHUNK_SIZE = 8 * 1024
FRAME_HANDOFF_SECONDS = 0.001


@dataclass(frozen=True, slots=True)
class MjpegSourceStatus:
    """Observable state for one Python-side MJPEG connection."""

    state: str
    last_connected_at: datetime | None
    last_frame_at: datetime | None
    last_frame_age_seconds: float | None
    receive_fps: float
    frames_received: int
    reconnect_count: int
    retry_in_seconds: float | None
    last_error: str | None
    source_type: str = "mjpeg"
    profile: str | None = None
    device_index: int | None = None
    frame_width: int | None = None
    frame_height: int | None = None
    target_fps: float | None = None
    jpeg_quality: int | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "source_type": self.source_type,
            "profile": self.profile,
            "device_index": self.device_index,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "target_fps": _rounded(self.target_fps),
            "jpeg_quality": self.jpeg_quality,
            "state": self.state,
            "last_connected_at": _isoformat(self.last_connected_at),
            "last_frame_at": _isoformat(self.last_frame_at),
            "last_frame_age_seconds": _rounded(self.last_frame_age_seconds),
            "receive_fps": round(self.receive_fps, 1),
            "frames_received": self.frames_received,
            "reconnect_count": self.reconnect_count,
            "retry_in_seconds": _rounded(self.retry_in_seconds),
            "last_error": self.last_error,
        }


def _isoformat(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def iter_jpegs(
    stream: object,
    chunk_size: int = DEFAULT_MJPEG_CHUNK_SIZE,
) -> Iterator[bytes]:
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
        stale_after_seconds: float = 3.0,
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
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")

        self.url = url
        self._initial_backoff = reconnect_initial_seconds
        self._max_backoff = reconnect_max_seconds
        self._request_timeout = request_timeout_seconds
        self._stale_after_seconds = stale_after_seconds
        self._opener = opener
        self._store = LatestFrameStore()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._status_lock = Lock()
        self._state = "STOPPED"
        self._last_connected_at: datetime | None = None
        self._last_connected_monotonic: float | None = None
        self._last_frame_at: datetime | None = None
        self._last_frame_monotonic: float | None = None
        self._frame_times: deque[float] = deque()
        self._frames_received = 0
        self._reconnect_count = 0
        self._retry_deadline: float | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        with self._status_lock:
            self._state = "CONNECTING"
            self._last_connected_at = None
            self._last_connected_monotonic = None
            self._last_frame_at = None
            self._last_frame_monotonic = None
            self._frame_times.clear()
            self._frames_received = 0
            self._reconnect_count = 0
            self._retry_deadline = None
            self._last_error = None
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
        self._set_state("STOPPED")

    def read_latest(self, after_sequence: int = 0) -> CapturedFrame | None:
        return self._store.read_latest(after_sequence)

    def get_status(self) -> MjpegSourceStatus:
        """Return a thread-safe snapshot of the camera stream status."""

        now = monotonic()
        with self._status_lock:
            last_frame_age = (
                None
                if self._last_frame_monotonic is None
                else max(0.0, now - self._last_frame_monotonic)
            )
            active_age = (
                last_frame_age
                if last_frame_age is not None
                else (
                    None
                    if self._last_connected_monotonic is None
                    else max(0.0, now - self._last_connected_monotonic)
                )
            )
            state = self._state
            if state == "CONNECTED" and (
                active_age is not None and active_age > self._stale_after_seconds
            ):
                state = "STALE"

            retry_in = (
                None
                if self._retry_deadline is None
                else max(0.0, self._retry_deadline - now)
            )
            return MjpegSourceStatus(
                state=state,
                last_connected_at=self._last_connected_at,
                last_frame_at=self._last_frame_at,
                last_frame_age_seconds=last_frame_age,
                receive_fps=self._receive_fps_locked(now),
                frames_received=self._frames_received,
                reconnect_count=self._reconnect_count,
                retry_in_seconds=retry_in,
                last_error=self._last_error,
            )

    def _run(self) -> None:
        backoff = self._initial_backoff
        while not self._stop_event.is_set():
            if self._reconnect_count:
                self._set_state("RECONNECTING")
            else:
                self._set_state("CONNECTING")
            try:
                with self._opener(self.url, timeout=self._request_timeout) as stream:  # type: ignore[union-attr]
                    self._set_state("CONNECTED")
                    backoff = self._initial_backoff
                    for jpeg in iter_jpegs(stream):
                        if self._stop_event.is_set():
                            return
                        frame = self._store.put(jpeg)
                        self._record_frame(frame)
                        # Avoid processing several JPEGs in one reader burst
                        # before the inference thread gets a chance to read.
                        sleep(FRAME_HANDOFF_SECONDS)
                raise ConnectionError("MJPEG stream ended")
            except Exception as exc:  # noqa: BLE001 - reconnect boundary
                if self._stop_event.is_set():
                    return
                self._reconnect_count_increment()
                self._set_state(
                    "RECONNECTING",
                    error=str(exc),
                    retry_seconds=backoff,
                )
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
        with self._status_lock:
            self._retry_deadline = deadline
        while not self._stop_event.is_set() and monotonic() < deadline:
            self._stop_event.wait(timeout=min(0.2, deadline - monotonic()))

    def _set_state(
        self,
        state: str,
        *,
        error: str | None = None,
        retry_seconds: float | None = None,
    ) -> None:
        now = monotonic()
        changed = False
        with self._status_lock:
            changed = self._state != state
            self._state = state
            if state == "CONNECTED":
                self._last_connected_at = datetime.now(timezone.utc)
                self._last_connected_monotonic = now
                self._retry_deadline = None
                self._last_error = None
            elif state == "RECONNECTING":
                self._last_error = error or self._last_error
                self._retry_deadline = (
                    None
                    if retry_seconds is None
                    else now + max(0.0, retry_seconds)
                )
            elif state in {"CONNECTING", "STOPPED"}:
                self._retry_deadline = None
                if state == "STOPPED":
                    self._last_error = None
        if changed:
            logger.info("MJPEG state=%s url=%s", state, self.url)

    def _record_frame(self, frame: CapturedFrame) -> None:
        now = monotonic()
        with self._status_lock:
            self._state = "CONNECTED"
            self._last_frame_at = frame.captured_at
            self._last_frame_monotonic = now
            self._frames_received += 1
            self._frame_times.append(now)
            self._trim_frame_times_locked(now)

    def _reconnect_count_increment(self) -> None:
        with self._status_lock:
            self._reconnect_count += 1

    def _receive_fps_locked(self, now: float) -> float:
        self._trim_frame_times_locked(now)
        if len(self._frame_times) < 2:
            return 0.0
        elapsed = self._frame_times[-1] - self._frame_times[0]
        return (len(self._frame_times) - 1) / elapsed if elapsed > 0 else 0.0

    def _trim_frame_times_locked(self, now: float) -> None:
        while self._frame_times and now - self._frame_times[0] > 5.0:
            self._frame_times.popleft()
