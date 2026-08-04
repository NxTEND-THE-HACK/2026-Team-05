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
    assert settings.reconnect_initial_seconds == 1.0


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
