"""Landmark preprocessing and template-based temporal classification.

The runtime classifier deliberately has no dependency on NumPy or MediaPipe.
It consumes the transport-independent :class:`LandmarkFrame` domain model,
which makes the normalization, DTW, and k-NN stages straightforward to test
with recorded or synthetic landmarks.
"""

from __future__ import annotations

import json
import math
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..domain.models import HandObservation, Landmark, LandmarkFrame
from .catalog import SUPPORTED_MOTION_CODES

Point = tuple[float, float, float]
PointSequence = Sequence[Point | None]

# Pose names follow the MediaPipe Pose Landmarker order. Keeping this list in
# the feature module makes the serialized template format independent from
# the detector implementation.
POSE_LANDMARK_NAMES = (
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

HAND_LANDMARK_COUNT = 21
FEATURE_NAMES = (
    tuple(f"POSE_{name}" for name in POSE_LANDMARK_NAMES)
    + tuple(f"RIGHT_HAND_{index}" for index in range(HAND_LANDMARK_COUNT))
    + tuple(f"LEFT_HAND_{index}" for index in range(HAND_LANDMARK_COUNT))
)
FEATURE_INDEX = {name: index for index, name in enumerate(FEATURE_NAMES)}

DEFAULT_MISSING_POINT_PENALTY = 0.05
DEFAULT_DTW_THRESHOLD = 0.35


@dataclass(frozen=True, slots=True)
class NormalizedLandmarkFrame:
    """One normalized frame in the fixed serialized feature order."""

    captured_at: datetime
    points: tuple[Point | None, ...]

    def __post_init__(self) -> None:
        if len(self.points) != len(FEATURE_NAMES):
            raise ValueError(
                f"points must contain {len(FEATURE_NAMES)} features"
            )


class LandmarkNormalizer:
    """Normalize pose and hand landmarks around the shoulder midpoint."""

    def __init__(
        self,
        *,
        visibility_threshold: float = 0.5,
        minimum_shoulder_width: float = 1e-6,
    ) -> None:
        if not 0.0 <= visibility_threshold <= 1.0:
            raise ValueError("visibility_threshold must be between 0 and 1")
        if minimum_shoulder_width <= 0:
            raise ValueError("minimum_shoulder_width must be positive")
        self.visibility_threshold = visibility_threshold
        self.minimum_shoulder_width = minimum_shoulder_width

    def normalize(self, frame: LandmarkFrame) -> NormalizedLandmarkFrame | None:
        """Return a normalized frame, or ``None`` when shoulders are unusable.

        The shoulder midpoint is subtracted from every coordinate and the
        shoulder distance in the image plane is used as the scale. Z is
        translated by the same midpoint and divided by that scale, preserving
        the relative depth information reported by MediaPipe.
        """

        left_shoulder = frame.pose.get("LEFT_SHOULDER")
        right_shoulder = frame.pose.get("RIGHT_SHOULDER")
        if not self._visible(left_shoulder) or not self._visible(right_shoulder):
            return None
        assert left_shoulder is not None
        assert right_shoulder is not None

        center = (
            (left_shoulder.x + right_shoulder.x) / 2.0,
            (left_shoulder.y + right_shoulder.y) / 2.0,
            (left_shoulder.z + right_shoulder.z) / 2.0,
        )
        shoulder_width = math.hypot(
            left_shoulder.x - right_shoulder.x,
            left_shoulder.y - right_shoulder.y,
        )
        if shoulder_width < self.minimum_shoulder_width:
            return None

        hand_by_side = {
            "RIGHT": self._find_hand(frame.hands, "right"),
            "LEFT": self._find_hand(frame.hands, "left"),
        }
        points: list[Point | None] = []
        for name in POSE_LANDMARK_NAMES:
            points.append(
                self._normalize_landmark(
                    frame.pose.get(name), center, shoulder_width
                )
            )
        for side in ("RIGHT", "LEFT"):
            hand = hand_by_side[side]
            for index in range(HAND_LANDMARK_COUNT):
                landmark = (
                    None
                    if hand is None or len(hand.landmarks) <= index
                    else hand.landmarks[index]
                )
                points.append(
                    self._normalize_landmark(
                        landmark, center, shoulder_width, check_visibility=False
                    )
                )

        return NormalizedLandmarkFrame(frame.captured_at, tuple(points))

    def _normalize_landmark(
        self,
        landmark: Landmark | None,
        center: Point,
        shoulder_width: float,
        *,
        check_visibility: bool = True,
    ) -> Point | None:
        if landmark is None:
            return None
        if check_visibility and not self._visible(landmark):
            return None
        return (
            (landmark.x - center[0]) / shoulder_width,
            (landmark.y - center[1]) / shoulder_width,
            (landmark.z - center[2]) / shoulder_width,
        )

    def _visible(self, landmark: Landmark | None) -> bool:
        return (
            landmark is not None
            and (
                landmark.visibility is None
                or landmark.visibility >= self.visibility_threshold
            )
        )

    @staticmethod
    def _find_hand(
        hands: Iterable[HandObservation], handedness: str
    ) -> HandObservation | None:
        expected = handedness.casefold()
        return next(
            (
                hand
                for hand in hands
                if hand.handedness.strip().casefold() == expected
            ),
            None,
        )


class ExponentialMovingAverage:
    """Apply EMA smoothing independently to every available landmark."""

    def __init__(self, alpha: float = 0.4) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be greater than 0 and at most 1")
        self.alpha = alpha
        self._previous: tuple[Point | None, ...] | None = None

    def update(self, frame: NormalizedLandmarkFrame) -> NormalizedLandmarkFrame:
        if self._previous is None:
            points = frame.points
        else:
            points = tuple(
                self._smooth(previous, current)
                for previous, current in zip(
                    self._previous, frame.points, strict=True
                )
            )
        self._previous = points
        return NormalizedLandmarkFrame(frame.captured_at, points)

    def reset(self) -> None:
        self._previous = None

    def _smooth(
        self, previous: Point | None, current: Point | None
    ) -> Point | None:
        if current is None:
            return None
        if previous is None:
            return current
        return tuple(
            self.alpha * current_value + (1.0 - self.alpha) * previous_value
            for previous_value, current_value in zip(previous, current, strict=True)
        )  # type: ignore[return-value]


class SlidingWindow:
    """Keep the newest normalized frames up to a fixed maximum length."""

    def __init__(self, max_frames: int = 30) -> None:
        if max_frames < 1:
            raise ValueError("max_frames must be positive")
        self.max_frames = max_frames
        self._frames: deque[NormalizedLandmarkFrame] = deque(maxlen=max_frames)

    def append(self, frame: NormalizedLandmarkFrame) -> None:
        self._frames.append(frame)

    def clear(self) -> None:
        self._frames.clear()

    @property
    def is_full(self) -> bool:
        return len(self._frames) == self.max_frames

    def snapshot(self) -> tuple[NormalizedLandmarkFrame, ...]:
        return tuple(self._frames)

    def __len__(self) -> int:
        return len(self._frames)


def _frame_distance(
    first: PointSequence,
    second: PointSequence,
    *,
    missing_point_penalty: float,
) -> float:
    if len(first) != len(second):
        raise ValueError("DTW frames must use the same feature count")
    total = 0.0
    for first_point, second_point in zip(first, second, strict=True):
        if first_point is None and second_point is None:
            continue
        if first_point is None or second_point is None:
            total += missing_point_penalty
            continue
        total += math.sqrt(
            sum(
                (first_value - second_value) ** 2
                for first_value, second_value in zip(
                    first_point, second_point, strict=True
                )
            )
        )
    return total / max(len(first), 1)


def dtw_distance(
    first: Sequence[PointSequence | NormalizedLandmarkFrame],
    second: Sequence[PointSequence | NormalizedLandmarkFrame],
    *,
    missing_point_penalty: float = DEFAULT_MISSING_POINT_PENALTY,
) -> float:
    """Return a path-length-normalized DTW distance between two sequences."""

    if not first or not second:
        raise ValueError("DTW sequences must not be empty")
    if missing_point_penalty < 0:
        raise ValueError("missing_point_penalty must not be negative")

    first_points = [_points(item) for item in first]
    second_points = [_points(item) for item in second]
    costs = [
        [math.inf] * (len(second_points) + 1)
        for _ in range(len(first_points) + 1)
    ]
    predecessors: list[list[tuple[int, int] | None]] = [
        [None] * (len(second_points) + 1)
        for _ in range(len(first_points) + 1)
    ]
    costs[0][0] = 0.0

    for first_index, first_frame in enumerate(first_points, start=1):
        for second_index, second_frame in enumerate(second_points, start=1):
            candidates = (
                (costs[first_index - 1][second_index], (first_index - 1, second_index)),
                (costs[first_index][second_index - 1], (first_index, second_index - 1)),
                (
                    costs[first_index - 1][second_index - 1],
                    (first_index - 1, second_index - 1),
                ),
            )
            previous_cost, previous_cell = min(candidates, key=lambda item: item[0])
            costs[first_index][second_index] = previous_cost + _frame_distance(
                first_frame,
                second_frame,
                missing_point_penalty=missing_point_penalty,
            )
            predecessors[first_index][second_index] = previous_cell

    row = len(first_points)
    column = len(second_points)
    path_length = 0
    while row or column:
        previous = predecessors[row][column]
        if previous is None:
            raise ValueError("DTW could not construct an alignment path")
        path_length += 1
        row, column = previous
    return costs[-1][-1] / max(path_length, 1)


def _points(item: PointSequence | NormalizedLandmarkFrame) -> PointSequence:
    return item.points if isinstance(item, NormalizedLandmarkFrame) else item


@dataclass(frozen=True, slots=True)
class MotionTemplate:
    motion_code: str
    sample_id: str
    frames: tuple[PointSequence, ...]

    def __post_init__(self) -> None:
        if self.motion_code not in SUPPORTED_MOTION_CODES:
            raise ValueError(f"unsupported motion code: {self.motion_code}")
        if not self.sample_id.strip():
            raise ValueError("sample_id must not be empty")
        if not self.frames:
            raise ValueError("template frames must not be empty")
        feature_count = len(FEATURE_NAMES)
        if any(len(frame) != feature_count for frame in self.frames):
            raise ValueError(f"template frames must contain {feature_count} features")


@dataclass(frozen=True, slots=True)
class TemplateSet:
    """A validated collection of fixed motion templates and thresholds."""

    templates: tuple[MotionTemplate, ...]
    thresholds: dict[str, float]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported motion template schema version")
        if not self.templates:
            raise ValueError("at least one motion template is required")
        sample_ids: set[tuple[str, str]] = set()
        for template in self.templates:
            key = (template.motion_code, template.sample_id)
            if key in sample_ids:
                raise ValueError(f"duplicate motion template: {key}")
            sample_ids.add(key)
        for motion_code, threshold in self.thresholds.items():
            if motion_code not in SUPPORTED_MOTION_CODES:
                raise ValueError(f"unsupported threshold motion code: {motion_code}")
            if not math.isfinite(threshold) or threshold <= 0:
                raise ValueError(f"threshold for {motion_code} must be positive")

    @classmethod
    def from_json(cls, path: str | Path) -> "TemplateSet":
        with Path(path).open(encoding="utf-8") as source:
            raw = json.load(source)
        if not isinstance(raw, dict):
            raise ValueError("motion template file must contain a JSON object")
        schema_version = int(raw.get("schema_version", 0))
        raw_templates = raw.get("templates")
        if not isinstance(raw_templates, list):
            raise ValueError("motion template file must contain templates")

        templates: list[MotionTemplate] = []
        for raw_template in raw_templates:
            if not isinstance(raw_template, dict):
                raise ValueError("each motion template must be an object")
            raw_frames = raw_template.get("frames")
            if not isinstance(raw_frames, list):
                raise ValueError("each motion template must contain frames")
            frames = tuple(_decode_frame(raw_frame) for raw_frame in raw_frames)
            templates.append(
                MotionTemplate(
                    motion_code=str(raw_template.get("motion_code", "")),
                    sample_id=str(raw_template.get("sample_id", "")),
                    frames=frames,
                )
            )

        raw_thresholds = raw.get("thresholds", {})
        if not isinstance(raw_thresholds, dict):
            raise ValueError("thresholds must be an object")
        thresholds = {str(code): float(value) for code, value in raw_thresholds.items()}
        return cls(tuple(templates), thresholds, schema_version)

    def to_json_object(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "feature_names": list(FEATURE_NAMES),
            "thresholds": dict(sorted(self.thresholds.items())),
            "templates": [
                {
                    "motion_code": template.motion_code,
                    "sample_id": template.sample_id,
                    "frames": [
                        [
                            None if point is None else list(point)
                            for point in frame
                        ]
                        for frame in template.frames
                    ],
                }
                for template in self.templates
            ],
        }

    def write_json(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_json_object(), ensure_ascii=False, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
        )


def _decode_frame(raw_frame: Any) -> tuple[Point | None, ...]:
    if not isinstance(raw_frame, list) or len(raw_frame) != len(FEATURE_NAMES):
        raise ValueError(f"each template frame must contain {len(FEATURE_NAMES)} features")
    points: list[Point | None] = []
    for raw_point in raw_frame:
        if raw_point is None:
            points.append(None)
            continue
        if (
            not isinstance(raw_point, list)
            or len(raw_point) != 3
            or not all(isinstance(value, (int, float)) for value in raw_point)
        ):
            raise ValueError("template points must be null or [x, y, z]")
        points.append((float(raw_point[0]), float(raw_point[1]), float(raw_point[2])))
    return tuple(points)


@dataclass(frozen=True, slots=True)
class Neighbor:
    motion_code: str
    sample_id: str
    distance: float


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    motion_code: str | None
    confidence: float
    distance: float
    neighbors: tuple[Neighbor, ...]


class KNNMotionClassifier:
    """Classify a window by majority vote over its nearest DTW templates."""

    def __init__(
        self,
        templates: Iterable[MotionTemplate],
        *,
        k: int = 3,
        thresholds: dict[str, float] | None = None,
        missing_point_penalty: float = DEFAULT_MISSING_POINT_PENALTY,
    ) -> None:
        self.templates = tuple(templates)
        if not self.templates:
            raise ValueError("at least one motion template is required")
        if k < 1:
            raise ValueError("k must be positive")
        if missing_point_penalty < 0:
            raise ValueError("missing_point_penalty must not be negative")
        self.k = min(k, len(self.templates))
        self.thresholds = dict(thresholds or {})
        self.missing_point_penalty = missing_point_penalty
        for motion_code, threshold in self.thresholds.items():
            if motion_code not in SUPPORTED_MOTION_CODES:
                raise ValueError(f"unsupported threshold motion code: {motion_code}")
            if not math.isfinite(threshold) or threshold <= 0:
                raise ValueError(f"threshold for {motion_code} must be positive")

    def classify(
        self, window: Sequence[NormalizedLandmarkFrame]
    ) -> ClassificationResult:
        if not window:
            raise ValueError("classification window must not be empty")
        neighbors = tuple(
            Neighbor(template.motion_code, template.sample_id, distance)
            for template, distance in sorted(
                (
                    (
                        template,
                        dtw_distance(
                            window,
                            template.frames,
                            missing_point_penalty=self.missing_point_penalty,
                        ),
                    )
                    for template in self.templates
                ),
                key=lambda item: (item[1], item[0].motion_code, item[0].sample_id),
            )[: self.k]
        )
        if not neighbors or not any(math.isfinite(item.distance) for item in neighbors):
            return ClassificationResult(None, 0.0, math.inf, neighbors)

        votes = Counter(item.motion_code for item in neighbors)
        grouped: dict[str, list[float]] = {}
        for neighbor in neighbors:
            grouped.setdefault(neighbor.motion_code, []).append(neighbor.distance)
        winner = min(
            grouped,
            key=lambda motion_code: (
                -votes[motion_code],
                sum(grouped[motion_code]) / len(grouped[motion_code]),
                motion_code,
            ),
        )
        winner_distance = min(grouped[winner])
        threshold = self.thresholds.get(winner, DEFAULT_DTW_THRESHOLD)
        if winner_distance > threshold:
            return ClassificationResult(None, 0.0, winner_distance, neighbors)
        confidence = max(0.0, min(1.0, 1.0 - winner_distance / threshold))
        return ClassificationResult(winner, confidence, winner_distance, neighbors)
