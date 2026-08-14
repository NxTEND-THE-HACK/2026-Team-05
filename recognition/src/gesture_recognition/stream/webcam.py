"""OpenCV local-camera input with configurable output normalization."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event, Lock, Thread, current_thread
from time import monotonic

import cv2
import numpy as np

from ..domain.models import CapturedFrame
from .latest import LatestFrameStore
from .profile import WebcamProfile

logger = logging.getLogger(__name__)

CaptureFactory = Callable[[int], object]


@dataclass(frozen=True, slots=True)
class WebcamSourceStatus:
    """Observable state for one Python-side local camera connection."""

    state: str
    last_connected_at: datetime | None
    last_frame_at: datetime | None
    last_frame_age_seconds: float | None
    receive_fps: float
    frames_received: int
    reconnect_count: int
    retry_in_seconds: float | None
    last_error: str | None
    source_type: str = "webcam"
    profile: str = "micon"
    device_index: int = 0
    frame_width: int = 800
    frame_height: int = 600
    target_fps: float = 15.0
    jpeg_quality: int = 80

    def to_payload(self) -> dict[str, object]:
        return {
            "source_type": self.source_type,
            "profile": self.profile,
            "device_index": self.device_index,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "target_fps": round(self.target_fps, 1),
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


def normalize_bgr_frame(
    image: np.ndarray,
    *,
    width: int,
    height: int,
) -> np.ndarray:
    """Center-crop a BGR frame to the target aspect ratio and resize it."""

    if image.ndim != 3 or image.shape[2] < 3:
        raise ValueError("camera frame must be a color image")
    source_height, source_width = image.shape[:2]
    if source_width <= 0 or source_height <= 0:
        raise ValueError("camera frame dimensions must be positive")

    target_ratio = width / height
    source_ratio = source_width / source_height
    if source_ratio > target_ratio:
        crop_width = max(1, int(round(source_height * target_ratio)))
        left = (source_width - crop_width) // 2
        cropped = image[:, left : left + crop_width]
    elif source_ratio < target_ratio:
        crop_height = max(1, int(round(source_width / target_ratio)))
        top = (source_height - crop_height) // 2
        cropped = image[top : top + crop_height, :]
    else:
        cropped = image

    return cv2.resize(cropped, (width, height), interpolation=cv2.INTER_AREA)


class OpenCvFrameSource:
    """Read a local USB or built-in camera on a background thread."""

    def __init__(
        self,
        device_index: int,
        *,
        profile: WebcamProfile,
        reconnect_initial_seconds: float = 1.0,
        reconnect_max_seconds: float = 30.0,
        stale_after_seconds: float = 3.0,
        capture_factory: CaptureFactory = cv2.VideoCapture,
    ) -> None:
        if device_index < 0:
            raise ValueError("webcam device index must not be negative")
        if reconnect_initial_seconds <= 0:
            raise ValueError("reconnect_initial_seconds must be positive")
        if reconnect_max_seconds < reconnect_initial_seconds:
            raise ValueError(
                "reconnect_max_seconds must be greater than or equal to "
                "reconnect_initial_seconds"
            )
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")

        self.device_index = device_index
        self.profile = profile
        self._initial_backoff = reconnect_initial_seconds
        self._max_backoff = reconnect_max_seconds
        self._stale_after_seconds = stale_after_seconds
        self._capture_factory = capture_factory
        self._store = LatestFrameStore()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._capture_lock = Lock()
        self._capture: object | None = None
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
            name=f"webcam-{self.device_index}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._capture_lock:
            capture = self._capture
        if capture is not None:
            self._release_capture(capture)
        if self._thread and self._thread is not current_thread():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._set_state("STOPPED")

    def read_latest(self, after_sequence: int = 0) -> CapturedFrame | None:
        return self._store.read_latest(after_sequence)

    def get_status(self) -> WebcamSourceStatus:
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
            return WebcamSourceStatus(
                state=state,
                last_connected_at=self._last_connected_at,
                last_frame_at=self._last_frame_at,
                last_frame_age_seconds=last_frame_age,
                receive_fps=self._receive_fps_locked(now),
                frames_received=self._frames_received,
                reconnect_count=self._reconnect_count,
                retry_in_seconds=retry_in,
                last_error=self._last_error,
                profile=self.profile.name,
                device_index=self.device_index,
                frame_width=self.profile.width,
                frame_height=self.profile.height,
                target_fps=self.profile.target_fps,
                jpeg_quality=self.profile.jpeg_quality,
            )

    def _run(self) -> None:
        backoff = self._initial_backoff
        while not self._stop_event.is_set():
            capture: object | None = None
            try:
                capture = self._capture_factory(self.device_index)
                with self._capture_lock:
                    self._capture = capture
                if not bool(capture.isOpened()):  # type: ignore[attr-defined]
                    raise ConnectionError(
                        f"webcam device {self.device_index} could not be opened"
                    )

                self._configure_capture(capture)
                self._set_state("CONNECTED")
                backoff = self._initial_backoff
                next_frame_at = monotonic()
                while not self._stop_event.is_set():
                    wait_seconds = next_frame_at - monotonic()
                    if wait_seconds > 0 and self._stop_event.wait(wait_seconds):
                        return

                    ok, image = capture.read()  # type: ignore[attr-defined]
                    if not ok or image is None:
                        raise ConnectionError(
                            f"webcam device {self.device_index} returned no frame"
                        )
                    jpeg = self._encode_frame(image)
                    frame = self._store.put(jpeg)
                    self._record_frame(frame)
                    next_frame_at = max(
                        next_frame_at + 1.0 / self.profile.target_fps,
                        monotonic(),
                    )
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
                    "webcam disconnected device=%s error=%s retry_in=%.1fs",
                    self.device_index,
                    exc,
                    backoff,
                )
                self._wait(backoff)
                backoff = min(backoff * 2, self._max_backoff)
            finally:
                if capture is not None:
                    with self._capture_lock:
                        if self._capture is capture:
                            self._capture = None
                    self._release_capture(capture)

    def _configure_capture(self, capture: object) -> None:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.profile.width)  # type: ignore[attr-defined]
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.profile.height)  # type: ignore[attr-defined]
        capture.set(cv2.CAP_PROP_FPS, self.profile.target_fps)  # type: ignore[attr-defined]

    def _encode_frame(self, image: np.ndarray) -> bytes:
        normalized = normalize_bgr_frame(
            image,
            width=self.profile.width,
            height=self.profile.height,
        )
        success, encoded = cv2.imencode(
            ".jpg",
            normalized,
            [cv2.IMWRITE_JPEG_QUALITY, self.profile.jpeg_quality],
        )
        if not success:
            raise RuntimeError("failed to encode webcam frame as JPEG")
        return encoded.tobytes()

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
            logger.info(
                "webcam state=%s device=%s profile=%s",
                state,
                self.device_index,
                self.profile.name,
            )

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

    @staticmethod
    def _release_capture(capture: object) -> None:
        try:
            capture.release()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - release must not mask shutdown
            logger.debug("failed to release webcam capture", exc_info=True)
