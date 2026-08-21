"""Construct the configured camera input source."""

from __future__ import annotations

from .base import FrameSource
from .mjpeg import MjpegFrameSource
from .profile import get_webcam_profile
from .webcam import OpenCvFrameSource


def create_frame_source(
    *,
    camera_source: str | None,
    webcam_index: int | None = None,
    webcam_profile: str = "micon",
    webcam_fps: float | None = None,
    webcam_jpeg_quality: int | None = None,
    reconnect_initial_seconds: float = 1.0,
    reconnect_max_seconds: float = 30.0,
    request_timeout_seconds: float = 5.0,
    stale_after_seconds: float = 3.0,
) -> FrameSource:
    """Build a local webcam source when an index is provided, else MJPEG."""

    if webcam_index is not None:
        profile = get_webcam_profile(
            webcam_profile,
            target_fps=webcam_fps,
            jpeg_quality=webcam_jpeg_quality,
        )
        return OpenCvFrameSource(
            webcam_index,
            profile=profile,
            reconnect_initial_seconds=reconnect_initial_seconds,
            reconnect_max_seconds=reconnect_max_seconds,
            stale_after_seconds=stale_after_seconds,
        )

    if not camera_source or not camera_source.strip():
        raise ValueError(
            "CAMERA_SOURCE is required unless CAMERA_WEBCAM_INDEX is set"
        )
    return MjpegFrameSource(
        camera_source,
        reconnect_initial_seconds=reconnect_initial_seconds,
        reconnect_max_seconds=reconnect_max_seconds,
        request_timeout_seconds=request_timeout_seconds,
        stale_after_seconds=stale_after_seconds,
    )
