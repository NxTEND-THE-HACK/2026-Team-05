from time import monotonic, sleep

import cv2
import numpy as np

from gesture_recognition.stream.factory import create_frame_source
from gesture_recognition.stream.mjpeg import MjpegFrameSource
from gesture_recognition.stream.profile import (
    MICON_COMPATIBLE_PROFILE,
    get_webcam_profile,
)
from gesture_recognition.stream.webcam import (
    OpenCvFrameSource,
    normalize_bgr_frame,
)


def _wait_until(predicate, timeout: float = 1.0) -> bool:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return True
        sleep(0.01)
    return predicate()


class _RepeatingCapture:
    def __init__(self, image: np.ndarray) -> None:
        self.image = image
        self.opened = True
        self.released = False
        self.settings: list[tuple[int, float]] = []

    def isOpened(self) -> bool:
        return self.opened

    def set(self, property_id: int, value: float) -> bool:
        self.settings.append((property_id, value))
        return True

    def read(self):
        if self.released:
            return False, None
        return True, self.image

    def release(self) -> None:
        self.released = True


class _ClosedCapture:
    def isOpened(self) -> bool:
        return False

    def release(self) -> None:
        return None


def test_normalize_bgr_frame_center_crops_wide_input() -> None:
    image = np.zeros((900, 1600, 3), dtype=np.uint8)
    image[:, :200] = (0, 0, 255)
    image[:, 200:1400] = (0, 255, 0)
    image[:, 1400:] = (255, 0, 0)

    normalized = normalize_bgr_frame(image, width=800, height=600)

    assert normalized.shape == (600, 800, 3)
    assert normalized[300, 0].tolist() == [0, 255, 0]
    assert normalized[300, -1].tolist() == [0, 255, 0]


def test_webcam_source_outputs_micon_compatible_jpeg() -> None:
    image = np.full((900, 1600, 3), 120, dtype=np.uint8)
    capture = _RepeatingCapture(image)
    source = OpenCvFrameSource(
        0,
        profile=MICON_COMPATIBLE_PROFILE,
        capture_factory=lambda _index: capture,
    )

    source.start()
    try:
        assert _wait_until(lambda: source.get_status().frames_received >= 1)
        frame = source.read_latest()
        assert frame is not None
        decoded = cv2.imdecode(
            np.frombuffer(frame.data, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        assert decoded is not None
        assert decoded.shape == (600, 800, 3)

        status = source.get_status()
        assert status.state == "CONNECTED"
        assert status.profile == "micon"
        assert status.target_fps == 15.0
        assert status.frame_width == 800
        assert status.frame_height == 600
        assert status.jpeg_quality == 80
        assert status.receive_fps >= 0.0
    finally:
        source.stop()

    assert capture.released is True
    assert (cv2.CAP_PROP_FRAME_WIDTH, 800) in capture.settings
    assert (cv2.CAP_PROP_FRAME_HEIGHT, 600) in capture.settings
    assert (cv2.CAP_PROP_FPS, 15.0) in capture.settings


def test_webcam_source_reconnects_after_capture_open_failure() -> None:
    image = np.zeros((600, 800, 3), dtype=np.uint8)
    working_capture = _RepeatingCapture(image)
    captures = [_ClosedCapture(), working_capture]

    def factory(_index: int):
        return captures.pop(0) if captures else working_capture

    source = OpenCvFrameSource(
        0,
        profile=MICON_COMPATIBLE_PROFILE,
        reconnect_initial_seconds=0.01,
        reconnect_max_seconds=0.01,
        capture_factory=factory,
    )

    source.start()
    try:
        assert _wait_until(lambda: source.get_status().frames_received >= 1)
        assert source.get_status().reconnect_count >= 1
    finally:
        source.stop()


def test_factory_keeps_mjpeg_as_default_and_selects_webcam_explicitly() -> None:
    mjpeg = create_frame_source(camera_source="http://camera/stream")
    webcam = create_frame_source(
        camera_source="http://camera/stream",
        webcam_index=0,
        webcam_profile="micon",
    )

    assert isinstance(mjpeg, MjpegFrameSource)
    assert isinstance(webcam, OpenCvFrameSource)


def test_webcam_profile_accepts_runtime_overrides() -> None:
    profile = get_webcam_profile(
        "micon",
        target_fps=12.0,
        jpeg_quality=70,
    )

    assert profile.width == 800
    assert profile.height == 600
    assert profile.target_fps == 12.0
    assert profile.jpeg_quality == 70
