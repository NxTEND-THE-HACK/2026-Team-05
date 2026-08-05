"""Thread-safe latest-frame buffer.

The buffer deliberately keeps one frame only. This prevents a slow inference
loop from processing stale video after the camera has already moved on.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from ..domain.models import CapturedFrame


class LatestFrameStore:
    """Keep only the most recently received frame in memory."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._latest: CapturedFrame | None = None
        self._sequence = 0

    def put(self, data: bytes, captured_at: datetime | None = None) -> CapturedFrame:
        if not data:
            raise ValueError("frame data must not be empty")

        timestamp = captured_at or datetime.now(timezone.utc)
        with self._lock:
            self._sequence += 1
            frame = CapturedFrame(data, timestamp, self._sequence)
            self._latest = frame
            return frame

    def read_latest(self, after_sequence: int = 0) -> CapturedFrame | None:
        with self._lock:
            frame = self._latest
            if frame is None or frame.sequence <= after_sequence:
                return None
            return frame
