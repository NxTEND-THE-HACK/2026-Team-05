"""Environment-based worker configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from collections.abc import Mapping

from .stream.profile import get_webcam_profile


class ConfigurationError(ValueError):
    """Raised when required worker configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    camera_id: str
    camera_source: str | None
    go_api_url: str
    webcam_index: int | None = None
    webcam_profile: str = "micon"
    webcam_fps: float = 15.0
    webcam_jpeg_quality: int = 80
    log_level: str = "INFO"
    reconnect_initial_seconds: float = 1.0
    reconnect_max_seconds: float = 30.0
    detection_send_retries: int = 3
    detection_send_timeout_seconds: float = 3.0
    frame_poll_interval_seconds: float = 0.001
    camera_stale_after_seconds: float = 3.0
    pose_model_path: str = "models/pose_landmarker_full.task"
    hand_model_path: str = "models/hand_landmarker.task"
    motion_samples_path: str = "models/motion_samples.json"
    target_fps: float = 15.0
    window_frames: int = 30
    inference_stride_frames: int = 3
    ema_alpha: float = 0.4
    landmark_visibility: float = 0.5
    knn_k: int = 3
    confirmation_count: int = 2
    recognition_cooldown_seconds: float = 1.0
    recognition_reset_gap_seconds: float = 1.5

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if env is None else env

        camera_id = _required(values, "CAMERA_ID")
        camera_source = values.get("CAMERA_SOURCE", "").strip() or None
        webcam_index = _optional_non_negative_int(values, "CAMERA_WEBCAM_INDEX")
        if camera_source is None and webcam_index is None:
            raise ConfigurationError(
                "CAMERA_SOURCE is required unless CAMERA_WEBCAM_INDEX is set"
            )
        go_api_url = values.get(
            "GO_API_URL", "http://127.0.0.1:8080/internal/detections"
        )
        webcam_profile = values.get("CAMERA_WEBCAM_PROFILE", "micon").strip().lower()
        webcam_fps = _positive_float(values, "CAMERA_WEBCAM_FPS", 15.0)
        webcam_jpeg_quality = _bounded_int(
            values,
            "CAMERA_WEBCAM_JPEG_QUALITY",
            80,
            minimum=1,
            maximum=100,
        )
        try:
            get_webcam_profile(
                webcam_profile,
                target_fps=webcam_fps,
                jpeg_quality=webcam_jpeg_quality,
            )
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc

        initial = _positive_float(values, "RECONNECT_INITIAL_SECONDS", 1.0)
        maximum = _positive_float(values, "RECONNECT_MAX_SECONDS", 30.0)
        if maximum < initial:
            raise ConfigurationError(
                "RECONNECT_MAX_SECONDS must be greater than or equal to "
                "RECONNECT_INITIAL_SECONDS"
            )

        retries = _non_negative_int(values, "DETECTION_SEND_RETRIES", 3)
        timeout = _positive_float(
            values, "DETECTION_SEND_TIMEOUT_SECONDS", 3.0
        )
        poll_interval = _positive_float(
            values, "FRAME_POLL_INTERVAL_SECONDS", 0.001
        )
        camera_stale_after = _positive_float(
            values, "CAMERA_STALE_AFTER_SECONDS", 3.0
        )
        pose_model_path = _required_or_default(
            values, "POSE_MODEL_PATH", "models/pose_landmarker_full.task"
        )
        hand_model_path = _required_or_default(
            values, "HAND_MODEL_PATH", "models/hand_landmarker.task"
        )
        motion_samples_path = _required_or_default(
            values, "MOTION_SAMPLES_PATH", "models/motion_samples.json"
        )
        target_fps = _positive_float(values, "TARGET_FPS", 15.0)
        window_frames = _positive_int(values, "WINDOW_FRAMES", 30)
        inference_stride_frames = _positive_int(
            values, "INFERENCE_STRIDE_FRAMES", 3
        )
        ema_alpha = _unit_float(values, "EMA_ALPHA", 0.4, minimum_exclusive=True)
        landmark_visibility = _unit_float(
            values, "LANDMARK_VISIBILITY", 0.5
        )
        knn_k = _positive_int(values, "KNN_K", 3)
        confirmation_count = _positive_int(values, "CONFIRMATION_COUNT", 2)
        recognition_cooldown = _non_negative_float(
            values, "RECOGNITION_COOLDOWN_SECONDS", 1.0
        )
        recognition_reset_gap = _positive_float(
            values, "RECOGNITION_RESET_GAP_SECONDS", 1.5
        )

        return cls(
            camera_id=camera_id,
            camera_source=camera_source,
            go_api_url=go_api_url,
            webcam_index=webcam_index,
            webcam_profile=webcam_profile,
            webcam_fps=webcam_fps,
            webcam_jpeg_quality=webcam_jpeg_quality,
            log_level=values.get("LOG_LEVEL", "INFO").upper(),
            reconnect_initial_seconds=initial,
            reconnect_max_seconds=maximum,
            detection_send_retries=retries,
            detection_send_timeout_seconds=timeout,
            frame_poll_interval_seconds=poll_interval,
            camera_stale_after_seconds=camera_stale_after,
            pose_model_path=pose_model_path,
            hand_model_path=hand_model_path,
            motion_samples_path=motion_samples_path,
            target_fps=target_fps,
            window_frames=window_frames,
            inference_stride_frames=inference_stride_frames,
            ema_alpha=ema_alpha,
            landmark_visibility=landmark_visibility,
            knn_k=knn_k,
            confirmation_count=confirmation_count,
            recognition_cooldown_seconds=recognition_cooldown,
            recognition_reset_gap_seconds=recognition_reset_gap,
        )


def _required(values: Mapping[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise ConfigurationError(f"{key} is required")
    return value


def _required_or_default(
    values: Mapping[str, str], key: str, default: str
) -> str:
    value = values.get(key, default).strip()
    if not value:
        raise ConfigurationError(f"{key} must not be empty")
    return value


def _positive_float(
    values: Mapping[str, str], key: str, default: float
) -> float:
    raw = values.get(key)
    try:
        value = default if raw is None else float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be a number") from exc
    if value <= 0:
        raise ConfigurationError(f"{key} must be greater than zero")
    return value


def _optional_non_negative_int(
    values: Mapping[str, str], key: str
) -> int | None:
    raw = values.get(key)
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be an integer") from exc
    if value < 0:
        raise ConfigurationError(f"{key} must not be negative")
    return value


def _non_negative_float(
    values: Mapping[str, str], key: str, default: float
) -> float:
    raw = values.get(key)
    try:
        value = default if raw is None else float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be a number") from exc
    if value < 0:
        raise ConfigurationError(f"{key} must not be negative")
    return value


def _unit_float(
    values: Mapping[str, str],
    key: str,
    default: float,
    *,
    minimum_exclusive: bool = False,
) -> float:
    raw = values.get(key)
    try:
        value = default if raw is None else float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be a number") from exc
    lower_valid = value > 0 if minimum_exclusive else value >= 0
    if not lower_valid or value > 1:
        operator = "greater than zero" if minimum_exclusive else "between 0 and 1"
        raise ConfigurationError(f"{key} must be {operator}")
    return value


def _non_negative_int(
    values: Mapping[str, str], key: str, default: int
) -> int:
    raw = values.get(key)
    try:
        value = default if raw is None else int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be an integer") from exc
    if value < 0:
        raise ConfigurationError(f"{key} must not be negative")
    return value


def _positive_int(values: Mapping[str, str], key: str, default: int) -> int:
    raw = values.get(key)
    try:
        value = default if raw is None else int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be an integer") from exc
    if value <= 0:
        raise ConfigurationError(f"{key} must be greater than zero")
    return value


def _bounded_int(
    values: Mapping[str, str],
    key: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = values.get(key)
    try:
        value = default if raw is None else int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(
            f"{key} must be between {minimum} and {maximum}"
        )
    return value
