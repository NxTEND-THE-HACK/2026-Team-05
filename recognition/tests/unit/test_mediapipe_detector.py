import pytest

from gesture_recognition.inference.mediapipe_detector import (
    InferenceDependencyError,
    MediaPipeDetector,
)


def test_detector_reports_missing_task_models() -> None:
    detector = MediaPipeDetector(
        pose_model_path="/missing/pose.task",
        hand_model_path="/missing/hand.task",
    )

    with pytest.raises(InferenceDependencyError, match="model file"):
        detector.start()
