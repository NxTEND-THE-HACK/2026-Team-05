"""Receive newline-delimited sound events from one microcontroller."""

from __future__ import annotations

import json
import logging
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event, Lock, Thread, current_thread
from time import monotonic
from typing import Protocol
from urllib.request import urlopen

logger = logging.getLogger(__name__)

UrlOpener = Callable[..., object]
DEFAULT_READ_CHUNK_SIZE = 1024
MAX_PENDING_EVENTS = 64


@dataclass(frozen=True, slots=True)
class SoundEvent:
    """One threshold-crossing event reported by the microcontroller."""

    sequence: int
    uptime_ms: int
    received_at: datetime

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sound sequence must not be negative")
        if self.uptime_ms < 0:
            raise ValueError("sound uptime_ms must not be negative")


@dataclass(frozen=True, slots=True)
class SoundSourceStatus:
    """Thread-safe observable state for the sound-event connection."""

    state: str
    last_connected_at: datetime | None
    last_message_at: datetime | None
    last_message_age_seconds: float | None
    last_event_at: datetime | None
    last_event_age_seconds: float | None
    last_event_sequence: int | None
    last_event_uptime_ms: int | None
    events_received: int
    events_dropped: int
    reconnect_count: int
    retry_in_seconds: float | None
    last_error: str | None
    source_type: str = "sound-events"

    @property
    def available(self) -> bool:
        return self.state == "CONNECTED"

    def to_payload(self) -> dict[str, object]:
        return {
            "source_type": self.source_type,
            "state": self.state,
            "last_connected_at": _isoformat(self.last_connected_at),
            "last_message_at": _isoformat(self.last_message_at),
            "last_message_age_seconds": _rounded(self.last_message_age_seconds),
            "last_event_at": _isoformat(self.last_event_at),
            "last_event_age_seconds": _rounded(self.last_event_age_seconds),
            "last_event_sequence": self.last_event_sequence,
            "last_event_uptime_ms": self.last_event_uptime_ms,
            "events_received": self.events_received,
            "events_dropped": self.events_dropped,
            "reconnect_count": self.reconnect_count,
            "retry_in_seconds": _rounded(self.retry_in_seconds),
            "last_error": self.last_error,
        }


class SoundEventSource(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def read_events(self) -> tuple[SoundEvent, ...]: ...

    def get_status(self) -> SoundSourceStatus: ...


def _isoformat(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def iter_ndjson_lines(
    stream: object,
    chunk_size: int = DEFAULT_READ_CHUNK_SIZE,
) -> Iterator[bytes]:
    """Yield complete non-empty lines from arbitrarily fragmented HTTP data."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    buffer = bytearray()
    while True:
        read1 = getattr(stream, "read1", None)
        chunk = (
            read1(chunk_size)
            if callable(read1)
            else stream.read(chunk_size)  # type: ignore[attr-defined]
        )
        if not chunk:
            return
        buffer.extend(chunk)
        while True:
            newline = buffer.find(b"\n")
            if newline < 0:
                break
            line = bytes(buffer[:newline]).strip()
            del buffer[: newline + 1]
            if line:
                yield line


class SoundEventStream:
    """Read microcontroller sound events on a reconnecting background thread."""

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
        if not url.strip():
            raise ValueError("sound event URL must not be empty")
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
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._active_stream: object | None = None
        self._lock = Lock()
        self._pending: deque[SoundEvent] = deque(maxlen=MAX_PENDING_EVENTS)
        self._state = "STOPPED"
        self._last_connected_at: datetime | None = None
        self._last_message_at: datetime | None = None
        self._last_message_monotonic: float | None = None
        self._last_event_at: datetime | None = None
        self._last_event_monotonic: float | None = None
        self._last_event_sequence: int | None = None
        self._last_event_uptime_ms: int | None = None
        self._events_received = 0
        self._events_dropped = 0
        self._reconnect_count = 0
        self._retry_deadline: float | None = None
        self._last_error: str | None = None
        self._connection_last_sequence: int | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        with self._lock:
            self._pending.clear()
            self._state = "CONNECTING"
            self._last_connected_at = None
            self._last_message_at = None
            self._last_message_monotonic = None
            self._last_event_at = None
            self._last_event_monotonic = None
            self._last_event_sequence = None
            self._last_event_uptime_ms = None
            self._events_received = 0
            self._events_dropped = 0
            self._reconnect_count = 0
            self._retry_deadline = None
            self._last_error = None
            self._connection_last_sequence = None
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run,
            name=f"sound-events-{self.url}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        with self._lock:
            stream = self._active_stream
        close = getattr(stream, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 - best-effort shutdown
                logger.debug("failed to close sound event stream", exc_info=True)
        if thread and thread is not current_thread():
            thread.join(timeout=self._request_timeout + 0.5)
        if thread is None or not thread.is_alive():
            self._thread = None
        with self._lock:
            self._state = "STOPPED"
            self._retry_deadline = None
            self._last_error = None

    def read_events(self) -> tuple[SoundEvent, ...]:
        with self._lock:
            events = tuple(self._pending)
            self._pending.clear()
            return events

    def get_status(self) -> SoundSourceStatus:
        now = monotonic()
        with self._lock:
            message_age = (
                None
                if self._last_message_monotonic is None
                else max(0.0, now - self._last_message_monotonic)
            )
            event_age = (
                None
                if self._last_event_monotonic is None
                else max(0.0, now - self._last_event_monotonic)
            )
            state = self._state
            if state == "CONNECTED" and (
                message_age is None or message_age > self._stale_after_seconds
            ):
                state = "STALE"
            retry_in = (
                None
                if self._retry_deadline is None
                else max(0.0, self._retry_deadline - now)
            )
            return SoundSourceStatus(
                state=state,
                last_connected_at=self._last_connected_at,
                last_message_at=self._last_message_at,
                last_message_age_seconds=message_age,
                last_event_at=self._last_event_at,
                last_event_age_seconds=event_age,
                last_event_sequence=self._last_event_sequence,
                last_event_uptime_ms=self._last_event_uptime_ms,
                events_received=self._events_received,
                events_dropped=self._events_dropped,
                reconnect_count=self._reconnect_count,
                retry_in_seconds=retry_in,
                last_error=self._last_error,
            )

    def _run(self) -> None:
        backoff = self._initial_backoff
        while not self._stop_event.is_set():
            self._set_connecting_state()
            try:
                with self._opener(self.url, timeout=self._request_timeout) as stream:  # type: ignore[union-attr]
                    with self._lock:
                        self._active_stream = stream
                        self._last_connected_at = datetime.now(timezone.utc)
                        self._connection_last_sequence = None
                        self._retry_deadline = None
                        self._last_error = None
                    backoff = self._initial_backoff
                    try:
                        if self._stop_event.is_set():
                            return
                        for line in iter_ndjson_lines(stream):
                            if self._stop_event.is_set():
                                return
                            self._handle_line(line)
                    finally:
                        with self._lock:
                            if self._active_stream is stream:
                                self._active_stream = None
                raise ConnectionError("sound event stream ended")
            except Exception as exc:  # noqa: BLE001 - reconnect boundary
                if self._stop_event.is_set():
                    return
                with self._lock:
                    self._reconnect_count += 1
                    self._state = "RECONNECTING"
                    self._last_error = str(exc)
                    self._retry_deadline = monotonic() + backoff
                logger.warning(
                    "sound event stream disconnected url=%s error=%s retry_in=%.1fs",
                    self.url,
                    exc,
                    backoff,
                )
                self._wait(backoff)
                backoff = min(backoff * 2, self._max_backoff)

    def _set_connecting_state(self) -> None:
        with self._lock:
            self._state = (
                "RECONNECTING" if self._reconnect_count else "CONNECTING"
            )

    def _handle_line(self, line: bytes) -> None:
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("message must be a JSON object")
            message_type = payload.get("type")
            uptime_ms = _non_negative_int(payload.get("uptime_ms"), "uptime_ms")
            sequence = None
            if message_type == "sound":
                sequence = _non_negative_int(payload.get("sequence"), "sequence")
            elif message_type != "heartbeat":
                raise ValueError(f"unsupported message type: {message_type!r}")
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("invalid sound event message error=%s", exc)
            return

        received_at = datetime.now(timezone.utc)
        received_monotonic = monotonic()
        with self._lock:
            self._state = "CONNECTED"
            self._last_message_at = received_at
            self._last_message_monotonic = received_monotonic
            self._last_error = None
            if sequence is None:
                return
            if (
                self._connection_last_sequence is not None
                and sequence <= self._connection_last_sequence
            ):
                return
            self._connection_last_sequence = sequence
            event = SoundEvent(sequence, uptime_ms, received_at)
            if len(self._pending) == self._pending.maxlen:
                self._events_dropped += 1
            self._pending.append(event)
            self._events_received += 1
            self._last_event_at = received_at
            self._last_event_monotonic = received_monotonic
            self._last_event_sequence = sequence
            self._last_event_uptime_ms = uptime_ms

    def _wait(self, seconds: float) -> None:
        deadline = monotonic() + seconds
        while not self._stop_event.is_set() and monotonic() < deadline:
            self._stop_event.wait(timeout=min(0.2, deadline - monotonic()))


def _non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value
