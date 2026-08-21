import pytest

from gesture_recognition.config import ConfigurationError, Settings


def test_settings_load_required_values() -> None:
    settings = Settings.from_env(
        {
            "CAMERA_ID": "camera-1",
            "CAMERA_SOURCE": "http://camera/stream",
            "GO_API_URL": "http://go/internal/detections",
        }
    )

    assert settings.camera_id == "camera-1"
    assert settings.camera_source == "http://camera/stream"
    assert settings.go_api_url == "http://go/internal/detections"
    assert settings.detection_min_confidence == 0.5
    assert settings.webcam_index is None
    assert settings.webcam_profile == "micon"
    assert settings.webcam_fps == 15.0
    assert settings.webcam_jpeg_quality == 80
    assert settings.reconnect_initial_seconds == 1.0
    assert settings.frame_poll_interval_seconds == 0.001
    assert settings.pose_model_path == "models/pose_landmarker_full.task"
    assert settings.hand_model_path == "models/hand_landmarker.task"
    assert settings.camera_stale_after_seconds == 3.0
    assert settings.motion_samples_path == "models/motion_samples.json"
    assert settings.target_fps == 15.0
    assert settings.window_frames == 30
    assert settings.inference_stride_frames == 3
    assert settings.ema_alpha == 0.4
    assert settings.landmark_visibility == 0.5
    assert settings.knn_k == 3
    assert settings.confirmation_count == 2
    assert settings.recognition_cooldown_seconds == 1.0


def test_settings_load_temporal_recognition_overrides() -> None:
    settings = Settings.from_env(
        {
            "CAMERA_ID": "camera-1",
            "CAMERA_SOURCE": "http://camera/stream",
            "TARGET_FPS": "12",
            "WINDOW_FRAMES": "24",
            "INFERENCE_STRIDE_FRAMES": "2",
            "EMA_ALPHA": "0.25",
            "LANDMARK_VISIBILITY": "0.6",
            "KNN_K": "5",
            "CONFIRMATION_COUNT": "3",
            "RECOGNITION_COOLDOWN_SECONDS": "1.5",
            "RECOGNITION_RESET_GAP_SECONDS": "0.9",
            "DETECTION_MIN_CONFIDENCE": "0.65",
            "MOTION_SAMPLES_PATH": "custom/templates.json",
            "CAMERA_STALE_AFTER_SECONDS": "4.5",
        }
    )

    assert settings.target_fps == 12.0
    assert settings.window_frames == 24
    assert settings.inference_stride_frames == 2
    assert settings.ema_alpha == 0.25
    assert settings.landmark_visibility == 0.6
    assert settings.knn_k == 5
    assert settings.confirmation_count == 3
    assert settings.recognition_cooldown_seconds == 1.5
    assert settings.recognition_reset_gap_seconds == 0.9
    assert settings.detection_min_confidence == 0.65
    assert settings.motion_samples_path == "custom/templates.json"
    assert settings.camera_stale_after_seconds == 4.5


def test_settings_load_local_webcam_configuration() -> None:
    settings = Settings.from_env(
        {
            "CAMERA_ID": "camera-1",
            "CAMERA_WEBCAM_INDEX": "2",
            "CAMERA_WEBCAM_PROFILE": "micon",
            "CAMERA_WEBCAM_FPS": "12",
            "CAMERA_WEBCAM_JPEG_QUALITY": "70",
        }
    )

    assert settings.camera_source is None
    assert settings.webcam_index == 2
    assert settings.webcam_profile == "micon"
    assert settings.webcam_fps == 12.0
    assert settings.webcam_jpeg_quality == 70


def test_settings_reject_missing_camera_input() -> None:
    with pytest.raises(
        ConfigurationError,
        match="CAMERA_SOURCE is required unless CAMERA_WEBCAM_INDEX is set",
    ):
        Settings.from_env({"CAMERA_ID": "camera-1"})


def test_settings_reject_invalid_webcam_values() -> None:
    base = {"CAMERA_ID": "camera-1", "CAMERA_WEBCAM_INDEX": "0"}
    for key, value in (
        ("CAMERA_WEBCAM_INDEX", "-1"),
        ("CAMERA_WEBCAM_FPS", "0"),
        ("CAMERA_WEBCAM_JPEG_QUALITY", "101"),
        ("CAMERA_WEBCAM_PROFILE", "unknown"),
    ):
        with pytest.raises(ConfigurationError):
            Settings.from_env({**base, key: value})


def test_settings_reject_invalid_temporal_values() -> None:
    base = {
        "CAMERA_ID": "camera-1",
        "CAMERA_SOURCE": "http://camera/stream",
    }
    for key, value in (
        ("WINDOW_FRAMES", "0"),
        ("INFERENCE_STRIDE_FRAMES", "0"),
        ("EMA_ALPHA", "0"),
        ("LANDMARK_VISIBILITY", "1.1"),
        ("KNN_K", "0"),
        ("CONFIRMATION_COUNT", "0"),
        ("CAMERA_STALE_AFTER_SECONDS", "0"),
        ("DETECTION_MIN_CONFIDENCE", "-0.1"),
        ("DETECTION_MIN_CONFIDENCE", "1.1"),
    ):
        values = {**base, key: value}
        try:
            Settings.from_env(values)
        except ConfigurationError:
            continue
        raise AssertionError(f"{key} should reject {value}")


def test_settings_reject_missing_camera_id() -> None:
    with pytest.raises(ConfigurationError, match="CAMERA_ID is required"):
        Settings.from_env({"CAMERA_SOURCE": "http://camera/stream"})


def test_settings_reject_invalid_reconnect_range() -> None:
    with pytest.raises(ConfigurationError, match="greater than or equal"):
        Settings.from_env(
            {
                "CAMERA_ID": "camera-1",
                "CAMERA_SOURCE": "http://camera/stream",
                "RECONNECT_INITIAL_SECONDS": "5",
                "RECONNECT_MAX_SECONDS": "1",
            }
        )
