"""MediaPipe Tasks Pose and Hand Landmarker adapter.

Imports of OpenCV, NumPy, and MediaPipe are intentionally delayed until the
detector is started. This keeps domain and rule tests runnable without camera
or native inference dependencies. The `.task` model files are supplied via
constructor paths and are never generated from camera frames.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..domain.models import CapturedFrame, HandObservation, Landmark, LandmarkFrame

logger = logging.getLogger(__name__)


class InferenceDependencyError(RuntimeError):
    """Raised when native inference dependencies are unavailable."""


class MediaPipeDetector:
    """Run Pose and Hand Landmarker for each supplied JPEG frame."""

    def __init__(
        self,
        *,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        model_complexity: int = 1,
        hands_max_num: int = 2,
        pose_model_path: str = "models/pose_landmarker_full.task",
        hand_model_path: str = "models/hand_landmarker.task",
    ) -> None:
        if not 0.0 <= min_detection_confidence <= 1.0:
            raise ValueError("min_detection_confidence must be between 0 and 1")
        if not 0.0 <= min_tracking_confidence <= 1.0:
            raise ValueError("min_tracking_confidence must be between 0 and 1")
        self._pose_options = {
            "static_image_mode": False,
            "model_complexity": model_complexity,
            "enable_segmentation": False,
            "min_detection_confidence": min_detection_confidence,
            "min_tracking_confidence": min_tracking_confidence,
        }
        self._hands_options = {
            "num_hands": hands_max_num,
            "min_hand_detection_confidence": min_detection_confidence,
            "min_hand_presence_confidence": min_detection_confidence,
            "min_tracking_confidence": min_tracking_confidence,
        }
        self._pose_model_path = pose_model_path
        self._hand_model_path = hand_model_path
        self._cv2: Any | None = None
        self._np: Any | None = None
        self._pose: Any | None = None
        self._hands: Any | None = None
        self._mp: Any | None = None
        self._last_timestamp_ms = -1

    def start(self) -> None:
        if self._pose is not None:
            return
        missing = [
            path
            for path in (self._pose_model_path, self._hand_model_path)
            if not Path(path).is_file()
        ]
        if missing:
            raise InferenceDependencyError(
                "MediaPipe task model file(s) not found: " + ", ".join(missing)
            )
        try:
            import cv2
            import mediapipe as mp
            import numpy as np
            from mediapipe.tasks import python as mp_tasks
            from mediapipe.tasks.python import vision
        except ImportError as exc:
            raise InferenceDependencyError(
                "opencv-python, numpy, and mediapipe are required for inference"
            ) from exc

        self._cv2 = cv2
        self._np = np
        self._mp = mp
        pose_options = vision.PoseLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=self._pose_model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=self._pose_options[
                "min_detection_confidence"
            ],
            min_pose_presence_confidence=self._pose_options[
                "min_detection_confidence"
            ],
            min_tracking_confidence=self._pose_options["min_tracking_confidence"],
        )
        hand_options = vision.HandLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=self._hand_model_path),
            running_mode=vision.RunningMode.VIDEO,
            **self._hands_options,
        )
        self._pose = vision.PoseLandmarker.create_from_options(pose_options)
        self._hands = vision.HandLandmarker.create_from_options(hand_options)

    def close(self) -> None:
        if self._pose is not None:
            self._pose.close()
        if self._hands is not None:
            self._hands.close()
        self._pose = None
        self._hands = None
        self._mp = None
        self._last_timestamp_ms = -1

    def detect(self, frame: CapturedFrame) -> LandmarkFrame:
        self.start()
        assert self._cv2 is not None
        assert self._np is not None
        assert self._pose is not None
        assert self._hands is not None
        assert self._mp is not None

        image = self._cv2.imdecode(
            self._np.frombuffer(frame.data, dtype=self._np.uint8),
            self._cv2.IMREAD_COLOR,
        )
        if image is None:
            raise ValueError("frame does not contain a decodable JPEG image")

        rgb_image = self._cv2.cvtColor(image, self._cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB,
            data=rgb_image,
        )
        timestamp_ms = max(
            self._last_timestamp_ms + 1,
            int(frame.captured_at.timestamp() * 1000),
        )
        self._last_timestamp_ms = timestamp_ms
        pose_result = self._pose.detect_for_video(mp_image, timestamp_ms)
        hands_result = self._hands.detect_for_video(mp_image, timestamp_ms)

        pose: dict[str, Landmark] = {}
        if pose_result.pose_landmarks:
            for name, landmark in zip(
                _POSE_LANDMARK_NAMES,
                pose_result.pose_landmarks[0],
                strict=False,
            ):
                pose[name] = _landmark(landmark, include_visibility=True)

        hands: list[HandObservation] = []
        for index, hand_landmarks in enumerate(hands_result.hand_landmarks or []):
            handedness = "Unknown"
            if hands_result.handedness and index < len(hands_result.handedness):
                classifications = hands_result.handedness[index]
                if classifications:
                    handedness = (
                        classifications[0].category_name
                        or classifications[0].display_name
                        or "Unknown"
                    )
            hands.append(
                HandObservation(
                    handedness=handedness,
                    landmarks=tuple(
                        _landmark(item) for item in hand_landmarks
                    ),
                )
            )

        return LandmarkFrame(
            captured_at=frame.captured_at,
            pose=pose,
            hands=tuple(hands),
        )


_POSE_LANDMARK_NAMES = (
    "NOSE",
    "LEFT_EYE_INNER",
    "LEFT_EYE",
    "LEFT_EYE_OUTER",
    "RIGHT_EYE_INNER",
    "RIGHT_EYE",
    "RIGHT_EYE_OUTER",
    "LEFT_EAR",
    "RIGHT_EAR",
    "MOUTH_LEFT",
    "MOUTH_RIGHT",
    "LEFT_SHOULDER",
    "RIGHT_SHOULDER",
    "LEFT_ELBOW",
    "RIGHT_ELBOW",
    "LEFT_WRIST",
    "RIGHT_WRIST",
    "LEFT_PINKY",
    "RIGHT_PINKY",
    "LEFT_INDEX",
    "RIGHT_INDEX",
    "LEFT_THUMB",
    "RIGHT_THUMB",
    "LEFT_HIP",
    "RIGHT_HIP",
    "LEFT_KNEE",
    "RIGHT_KNEE",
    "LEFT_ANKLE",
    "RIGHT_ANKLE",
    "LEFT_HEEL",
    "RIGHT_HEEL",
    "LEFT_FOOT_INDEX",
    "RIGHT_FOOT_INDEX",
)


def _landmark(item: Any, *, include_visibility: bool = False) -> Landmark:
    visibility = getattr(item, "visibility", None) if include_visibility else None
    return Landmark(
        x=float(item.x),
        y=float(item.y),
        z=float(item.z),
        visibility=None if visibility is None else float(visibility),
    )
