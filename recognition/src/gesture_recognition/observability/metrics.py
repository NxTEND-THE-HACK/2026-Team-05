"""Runtime metrics for measuring camera-frame inference throughput."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import datetime
from time import monotonic


class FrameProcessingMetrics:
    """Track selected, skipped, and inferred frames over a short time window.

    The camera sources intentionally keep only the newest frame. A sequence
    gap therefore represents frames that arrived but were overwritten before
    the inference loop could read them.
    """

    def __init__(
        self,
        *,
        window_seconds: float = 5.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.window_seconds = window_seconds
        self._clock = clock
        self._last_sequence: int | None = None
        self._inference_times: deque[float] = deque()
        self._output_times: deque[float] = deque()
        self._inference_durations: deque[tuple[float, float]] = deque()
        self._loop_times: deque[float] = deque()
        self._loop_durations: deque[tuple[float, float]] = deque()
        self.frames_processed = 0
        self.frames_output = 0
        self.frames_dropped = 0
        self.inference_errors = 0
        self.last_inference_at: datetime | None = None
        self.last_inference_ms: float | None = None

    def observe_frame(self, sequence: int) -> None:
        """Record one frame selected from the latest-frame buffer."""

        if sequence < 1:
            raise ValueError("sequence must be positive")
        if self._last_sequence is None:
            self.frames_dropped += max(0, sequence - 1)
        elif sequence > self._last_sequence + 1:
            self.frames_dropped += sequence - self._last_sequence - 1
        self._last_sequence = max(sequence, self._last_sequence or sequence)

    def record_inference(
        self,
        elapsed_seconds: float,
        *,
        captured_at: datetime,
        success: bool = True,
    ) -> None:
        """Record one MediaPipe inference attempt."""

        if elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must not be negative")
        now = self._clock()
        self.frames_processed += 1
        if not success:
            self.inference_errors += 1
        self.last_inference_at = captured_at
        self.last_inference_ms = elapsed_seconds * 1000.0
        self._inference_times.append(now)
        if success:
            self.frames_output += 1
            self._output_times.append(now)
        self._inference_durations.append((now, elapsed_seconds))
        self._trim(now)

    def record_loop(self, elapsed_seconds: float) -> None:
        """Record the time spent processing one selected camera frame."""

        if elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must not be negative")
        now = self._clock()
        self._loop_times.append(now)
        self._loop_durations.append((now, elapsed_seconds))
        self._trim(now)

    def to_payload(self) -> dict[str, object]:
        """Return JSON-safe metrics for the monitor dashboard."""

        now = self._clock()
        self._trim(now)
        inference_fps = self._rate(self._inference_times)
        output_fps = self._rate(self._output_times)
        loop_fps = self._rate(self._loop_times)

        average_inference_ms = 0.0
        if self._inference_durations:
            average_inference_ms = (
                sum(duration for _, duration in self._inference_durations)
                / len(self._inference_durations)
                * 1000.0
            )
        average_loop_ms = 0.0
        if self._loop_durations:
            average_loop_ms = (
                sum(duration for _, duration in self._loop_durations)
                / len(self._loop_durations)
                * 1000.0
            )

        total_seen = self.frames_processed + self.frames_dropped
        processing_ratio = (
            0.0
            if total_seen == 0
            else self.frames_processed / total_seen * 100.0
        )
        return {
            "frames_processed": self.frames_processed,
            "frames_output": self.frames_output,
            "frames_dropped": self.frames_dropped,
            "inference_errors": self.inference_errors,
            "inference_fps": round(inference_fps, 1),
            "output_fps": round(output_fps, 1),
            "loop_fps": round(loop_fps, 1),
            "processing_ratio": round(processing_ratio, 1),
            "last_inference_ms": (
                None
                if self.last_inference_ms is None
                else round(self.last_inference_ms, 1)
            ),
            "average_inference_ms": round(average_inference_ms, 1),
            "average_loop_ms": round(average_loop_ms, 1),
            "last_inference_at": (
                None
                if self.last_inference_at is None
                else self.last_inference_at.isoformat()
            ),
        }

    def _trim(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._inference_times and self._inference_times[0] < cutoff:
            self._inference_times.popleft()
        while self._output_times and self._output_times[0] < cutoff:
            self._output_times.popleft()
        while self._inference_durations and self._inference_durations[0][0] < cutoff:
            self._inference_durations.popleft()
        while self._loop_times and self._loop_times[0] < cutoff:
            self._loop_times.popleft()
        while self._loop_durations and self._loop_durations[0][0] < cutoff:
            self._loop_durations.popleft()

    @staticmethod
    def _rate(times: deque[float]) -> float:
        if len(times) < 2:
            return 0.0
        elapsed = times[-1] - times[0]
        return (len(times) - 1) / elapsed if elapsed > 0 else 0.0
