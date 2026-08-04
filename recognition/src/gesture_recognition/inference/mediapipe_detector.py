"""MediaPipe Pose and Hands adapter.

Imports of OpenCV, NumPy, and MediaPipe are intentionally delayed until the
detector is created. This keeps domain and rule tests runnable without camera
or native inference dependencies.
"""

from __future__ import annotations

import logging
from typing import Any

from ..domain.models import CapturedFrame, HandObservation, Landmark, LandmarkFrame

logger = logging.getLogger(__name__)


class InferenceDependencyError(RuntimeError):
    """Raised when native inference dependencies are unavailable."""


class MediaPipeDetector:
    """Run Pose and Hands for each supplied JPEG frame."""

    def __init__(
        self,
        *,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        model_complexity: int = 1,
        hands_static_image_mode: bool = False,
        hands_max_num: int = 2,
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
            "static_image_mode": hands_static_image_mode,
            "max_num_hands": hands_max_num,
            "min_detection_confidence": min_detection_confidence,
            "min_tracking_confidence": min_tracking_confidence,
        }
        self._cv2: Any | None = None
        self._np: Any | None = None
        self._pose: Any | None = None
        self._hands: Any | None = None
        self._pose_landmark_enum: Any | None = None

    def start(self) -> None:
        if self._pose is not None:
            return
        try:
            import cv2
            import mediapipe as mp
            import numpy as np
        except ImportError as exc:
            raise InferenceDependencyError(
                "opencv-python, numpy, and mediapipe are required for inference"
            ) from exc

        self._cv2 = cv2
        self._np = np
        self._pose = mp.solutions.pose.Pose(**self._pose_options)
        self._hands = mp.solutions.hands.Hands(**self._hands_options)
        self._pose_landmark_enum = mp.solutions.pose.PoseLandmark

    def close(self) -> None:
        if self._pose is not None:
            self._pose.close()
        if self._hands is not None:
            self._hands.close()
        self._pose = None
        self._hands = None

    def detect(self, frame: CapturedFrame) -> LandmarkFrame:
        self.start()
        assert self._cv2 is not None
        assert self._np is not None
        assert self._pose is not None
        assert self._hands is not None
        assert self._pose_landmark_enum is not None

        image = self._cv2.imdecode(
            self._np.frombuffer(frame.data, dtype=self._np.uint8),
            self._cv2.IMREAD_COLOR,
        )
        if image is None:
            raise ValueError("frame does not contain a decodable JPEG image")

        rgb_image = self._cv2.cvtColor(image, self._cv2.COLOR_BGR2RGB)
        pose_result = self._pose.process(rgb_image)
        hands_result = self._hands.process(rgb_image)

        pose: dict[str, Landmark] = {}
        if pose_result.pose_landmarks:
            for name, enum_value in self._pose_landmark_enum.__members__.items():
                landmark = pose_result.pose_landmarks.landmark[enum_value.value]
                pose[name] = _landmark(landmark, include_visibility=True)

        hands: list[HandObservation] = []
        for index, hand_landmarks in enumerate(
            hands_result.multi_hand_landmarks or []
        ):
            handedness = "Unknown"
            if hands_result.multi_handedness and index < len(
                hands_result.multi_handedness
            ):
                classifications = hands_result.multi_handedness[index].classification
                if classifications:
                    handedness = classifications[0].label
            hands.append(
                HandObservation(
                    handedness=handedness,
                    landmarks=tuple(
                        _landmark(item) for item in hand_landmarks.landmark
                    ),
                )
            )

        return LandmarkFrame(
            captured_at=frame.captured_at,
            pose=pose,
            hands=tuple(hands),
        )


def _landmark(item: Any, *, include_visibility: bool = False) -> Landmark:
    visibility = getattr(item, "visibility", None) if include_visibility else None
    return Landmark(
        x=float(item.x),
        y=float(item.y),
        z=float(item.z),
        visibility=None if visibility is None else float(visibility),
    )
