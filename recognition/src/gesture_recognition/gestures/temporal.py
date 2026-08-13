"""Landmark preprocessing and template-based temporal classification.

The runtime classifier deliberately has no dependency on NumPy or MediaPipe.
It consumes the transport-independent :class:`LandmarkFrame` domain model,
which makes the normalization, DTW, and k-NN stages straightforward to test
with recorded or synthetic landmarks.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import zlib
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..domain.models import HandObservation, Landmark, LandmarkFrame
try:  # NumPy is a runtime dependency, but domain-only tests can run without it.
    import numpy as _np
except ImportError:  # pragma: no cover - exercised only in dependency-free envs
    _np = None

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

DEFAULT_MISSING_POINT_PENALTY = 0.20
DEFAULT_DTW_THRESHOLD = 0.35
DEFAULT_NEAR_EXACT_MATCH_DISTANCE = 0.01
DEFAULT_NEAR_EXACT_RATIO = 0.1


@dataclass(frozen=True, slots=True)
class _FeatureFrame:
    """A private feature-selected frame used by the DTW fallback path."""

    captured_at: datetime
    points: tuple[Point | None, ...]
    weights: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class NormalizedLandmarkFrame:
    """One normalized frame in the fixed serialized feature order."""

    captured_at: datetime
    points: tuple[Point | None, ...]
    observed: tuple[bool, ...] | None = None
    weights: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        if len(self.points) != len(FEATURE_NAMES):
            raise ValueError(
                f"points must contain {len(FEATURE_NAMES)} features"
            )
        observed = self.observed
        if observed is None:
            observed = tuple(point is not None for point in self.points)
            object.__setattr__(self, "observed", observed)
        elif len(observed) != len(FEATURE_NAMES):
            raise ValueError(
                f"observed must contain {len(FEATURE_NAMES)} features"
            )

        weights = self.weights
        if weights is None:
            weights = tuple(1.0 if point is not None else 0.0 for point in self.points)
            object.__setattr__(self, "weights", weights)
        elif len(weights) != len(FEATURE_NAMES):
            raise ValueError(
                f"weights must contain {len(FEATURE_NAMES)} features"
            )
        if any(not math.isfinite(weight) or not 0.0 <= weight <= 1.0 for weight in weights):
            raise ValueError("weights must be finite values between 0 and 1")


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

        normalized_points = tuple(points)
        return NormalizedLandmarkFrame(
            frame.captured_at,
            normalized_points,
            tuple(point is not None for point in normalized_points),
            tuple(1.0 if point is not None else 0.0 for point in normalized_points),
        )

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
        return NormalizedLandmarkFrame(
            frame.captured_at,
            points,
            frame.observed,
            frame.weights,
        )

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


@dataclass(slots=True)
class _HandRecoveryState:
    points: dict[int, Point]
    wrist: Point | None
    last_observed_at: datetime


class HandGapFiller:
    """Fill short hand-detector gaps with low-weight translated landmarks.

    A hand is eligible for recovery only after enough real hand points were
    observed in the current frame.  Recovered points are marked as
    ``observed=False`` and carry a decaying weight, so they can bridge a
    detector dropout but cannot become strong evidence by themselves.
    """

    def __init__(
        self,
        *,
        max_gap_seconds: float = 0.55,
        minimum_observed_points: int = 10,
        initial_weight: float = 0.55,
        minimum_weight: float = 0.20,
    ) -> None:
        if max_gap_seconds <= 0:
            raise ValueError("max_gap_seconds must be positive")
        if not 1 <= minimum_observed_points <= HAND_LANDMARK_COUNT:
            raise ValueError(
                "minimum_observed_points must be between 1 and 21"
            )
        if not 0.0 < minimum_weight <= initial_weight <= 1.0:
            raise ValueError(
                "weights must satisfy 0 < minimum_weight <= initial_weight <= 1"
            )
        self.max_gap_seconds = max_gap_seconds
        self.minimum_observed_points = minimum_observed_points
        self.initial_weight = initial_weight
        self.minimum_weight = minimum_weight
        self._hand_indices = {
            "right": tuple(
                FEATURE_INDEX[f"RIGHT_HAND_{index}"]
                for index in range(HAND_LANDMARK_COUNT)
            ),
            "left": tuple(
                FEATURE_INDEX[f"LEFT_HAND_{index}"]
                for index in range(HAND_LANDMARK_COUNT)
            ),
        }
        self._wrist_indices = {
            "right": FEATURE_INDEX["POSE_RIGHT_WRIST"],
            "left": FEATURE_INDEX["POSE_LEFT_WRIST"],
        }
        self._states: dict[str, _HandRecoveryState] = {}

    def update(self, frame: NormalizedLandmarkFrame) -> NormalizedLandmarkFrame:
        assert frame.observed is not None
        assert frame.weights is not None
        points = list(frame.points)
        observed = list(frame.observed)
        weights = list(frame.weights)

        for side, hand_indices in self._hand_indices.items():
            actual_indices = tuple(
                index
                for index in hand_indices
                if observed[index] and points[index] is not None
            )
            state = self._states.get(side)
            wrist_index = self._wrist_indices[side]
            current_wrist = points[wrist_index]

            if len(actual_indices) >= self.minimum_observed_points:
                translated_previous: dict[int, Point] = {}
                if (
                    state is not None
                    and state.wrist is not None
                    and current_wrist is not None
                ):
                    delta = _point_delta(current_wrist, state.wrist)
                    translated_previous = {
                        index: _point_add(point, delta)
                        for index, point in state.points.items()
                    }

                next_points = {
                    index: translated_previous.get(index)
                    for index in hand_indices
                    if translated_previous.get(index) is not None
                }
                for index in actual_indices:
                    assert points[index] is not None
                    next_points[index] = points[index]
                self._states[side] = _HandRecoveryState(
                    next_points,
                    current_wrist,
                    frame.captured_at,
                )
                continue

            if state is None:
                continue
            elapsed = (frame.captured_at - state.last_observed_at).total_seconds()
            if elapsed < 0 or elapsed > self.max_gap_seconds:
                self._states.pop(side, None)
                continue

            recovery_weight = max(
                self.minimum_weight,
                self.initial_weight
                - (self.initial_weight - self.minimum_weight)
                * elapsed
                / self.max_gap_seconds,
            )
            delta = (
                _point_delta(current_wrist, state.wrist)
                if current_wrist is not None and state.wrist is not None
                else (0.0, 0.0, 0.0)
            )
            for index, previous_point in state.points.items():
                if points[index] is not None:
                    continue
                points[index] = _point_add(previous_point, delta)
                observed[index] = False
                weights[index] = recovery_weight

        return NormalizedLandmarkFrame(
            frame.captured_at,
            tuple(points),
            tuple(observed),
            tuple(weights),
        )

    def reset(self) -> None:
        self._states.clear()


def _point_delta(current: Point, previous: Point) -> Point:
    return tuple(
        current_value - previous_value
        for current_value, previous_value in zip(current, previous, strict=True)
    )  # type: ignore[return-value]


def _point_add(point: Point, delta: Point) -> Point:
    return tuple(
        point_value + delta_value
        for point_value, delta_value in zip(point, delta, strict=True)
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


# The live sliding window remains 30 frames. DTW uses a compact common time
# axis so adding templates does not make inference cost grow with every raw
# sample frame.
DEFAULT_COMPARISON_FRAMES = 12


def resample_sequence(
    sequence: Sequence[PointSequence | NormalizedLandmarkFrame],
    target_frames: int = DEFAULT_COMPARISON_FRAMES,
) -> tuple[PointSequence | NormalizedLandmarkFrame, ...]:
    """Represent any registered/window sequence at one common frame count.

    Nearest-frame sampling changes only the time axis. It intentionally does
    not synthesize a missing landmark; temporal gap filling remains the sole
    place where short detector dropouts may be recovered.
    """

    if not sequence:
        raise ValueError("sequence must not be empty")
    if target_frames < 1:
        raise ValueError("target_frames must be positive")
    if len(sequence) == target_frames:
        return tuple(sequence)
    if target_frames == 1:
        return (sequence[0],)
    source_last = len(sequence) - 1
    target_last = target_frames - 1
    return tuple(
        sequence[round(index * source_last / target_last)]
        for index in range(target_frames)
    )


def _frame_distance(
    first: PointSequence,
    second: PointSequence,
    *,
    missing_point_penalty: float,
    first_weights: Sequence[float] | None = None,
    second_weights: Sequence[float] | None = None,
) -> float:
    if len(first) != len(second):
        raise ValueError("DTW frames must use the same feature count")
    if first_weights is not None and len(first_weights) != len(first):
        raise ValueError("first frame weights must match the feature count")
    if second_weights is not None and len(second_weights) != len(second):
        raise ValueError("second frame weights must match the feature count")
    total = 0.0
    support = 0.0
    for index, (first_point, second_point) in enumerate(
        zip(first, second, strict=True)
    ):
        first_weight = (
            1.0
            if first_weights is None and first_point is not None
            else 0.0
            if first_weights is None
            else first_weights[index]
        )
        second_weight = (
            1.0
            if second_weights is None and second_point is not None
            else 0.0
            if second_weights is None
            else second_weights[index]
        )
        if first_point is None and second_point is None:
            continue
        if first_point is None or second_point is None:
            support += max(first_weight, second_weight)
            total += missing_point_penalty * max(first_weight, second_weight)
            continue
        point_distance = math.sqrt(
            sum(
                (first_value - second_value) ** 2
                for first_value, second_value in zip(
                    first_point, second_point, strict=True
                )
            )
        )
        support += min(first_weight, second_weight)
        total += point_distance * min(first_weight, second_weight)
    if support <= 0:
        return missing_point_penalty
    return total / support


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
    first_weights = [_weights(item) for item in first]
    second_weights = [_weights(item) for item in second]
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
                first_weights=first_weights[first_index - 1],
                second_weights=second_weights[second_index - 1],
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


def _points(
    item: PointSequence | NormalizedLandmarkFrame | _FeatureFrame,
) -> PointSequence:
    return (
        item.points
        if isinstance(item, (NormalizedLandmarkFrame, _FeatureFrame))
        else item
    )


def _weights(
    item: PointSequence | NormalizedLandmarkFrame | _FeatureFrame,
) -> tuple[float, ...]:
    if isinstance(item, (NormalizedLandmarkFrame, _FeatureFrame)):
        assert item.weights is not None
        return item.weights
    return tuple(1.0 if point is not None else 0.0 for point in item)


@dataclass(frozen=True, slots=True)
class MotionTemplate:
    motion_code: str
    sample_id: str
    frames: tuple[PointSequence, ...]

    def __post_init__(self) -> None:
        if not self.motion_code.strip():
            raise ValueError("motion_code must not be empty")
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
        template_motion_codes = {template.motion_code for template in self.templates}
        for motion_code, threshold in self.thresholds.items():
            if motion_code not in template_motion_codes:
                raise ValueError(
                    f"threshold has no matching motion template: {motion_code}"
                )
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
        feature_names = raw.get("feature_names")
        if feature_names is not None and tuple(feature_names) != FEATURE_NAMES:
            raise ValueError("motion template feature order does not match runtime")
        encoding = str(raw.get("encoding", "plain"))
        coordinate_scale = float(raw.get("coordinate_scale", 1.0))
        if coordinate_scale <= 0:
            raise ValueError("coordinate_scale must be positive")

        templates: list[MotionTemplate] = []
        for raw_template in raw_templates:
            if not isinstance(raw_template, dict):
                raise ValueError("each motion template must be an object")
            raw_frames = raw_template.get("frames")
            if encoding == "zlib-base64":
                if isinstance(raw_frames, list) and all(
                    isinstance(chunk, str) for chunk in raw_frames
                ):
                    raw_frames = "".join(raw_frames)
                if not isinstance(raw_frames, str):
                    raise ValueError("compressed template frames must be a string")
                try:
                    raw_frames = json.loads(
                        zlib.decompress(base64.b64decode(raw_frames)).decode("utf-8")
                    )
                except (
                    ValueError,
                    TypeError,
                    UnicodeError,
                    binascii.Error,
                    zlib.error,
                ) as exc:
                    raise ValueError("invalid compressed motion template frames") from exc
            if not isinstance(raw_frames, list):
                raise ValueError("each motion template must contain frames")
            frames = tuple(
                _decode_frame(raw_frame, coordinate_scale=coordinate_scale)
                for raw_frame in raw_frames
            )
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
        coordinate_scale = 1000.0
        return {
            "schema_version": self.schema_version,
            "feature_names": list(FEATURE_NAMES),
            "encoding": "zlib-base64",
            "coordinate_scale": coordinate_scale,
            "thresholds": dict(sorted(self.thresholds.items())),
            "templates": [
                {
                    "motion_code": template.motion_code,
                    "sample_id": template.sample_id,
                    "frames": base64.b64encode(
                        zlib.compress(
                            json.dumps(
                                [
                                    [
                                        None
                                        if point is None
                                        else [
                                            round(value * coordinate_scale)
                                            for value in point
                                        ]
                                        for point in frame
                                    ]
                                    for frame in template.frames
                                ],
                                separators=(",", ":"),
                            ).encode("utf-8"),
                            level=9,
                        )
                    ).decode("ascii"),
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


def _decode_frame(
    raw_frame: Any, *, coordinate_scale: float = 1.0
) -> tuple[Point | None, ...]:
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
        points.append(
            (
                float(raw_point[0]) / coordinate_scale,
                float(raw_point[1]) / coordinate_scale,
                float(raw_point[2]) / coordinate_scale,
            )
        )
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
    is_near_exact: bool = False


class KNNMotionClassifier:
    """Classify a window by majority vote over its nearest DTW templates."""

    def __init__(
        self,
        templates: Iterable[MotionTemplate],
        *,
        k: int = 3,
        thresholds: dict[str, float] | None = None,
        missing_point_penalty: float = DEFAULT_MISSING_POINT_PENALTY,
        feature_indices: Sequence[int] | None = None,
        comparison_frames: int = DEFAULT_COMPARISON_FRAMES,
        require_full_consensus: bool = False,
    ) -> None:
        self.templates = tuple(templates)
        if not self.templates:
            raise ValueError("at least one motion template is required")
        if k < 1:
            raise ValueError("k must be positive")
        if missing_point_penalty < 0:
            raise ValueError("missing_point_penalty must not be negative")
        if comparison_frames < 1:
            raise ValueError("comparison_frames must be positive")
        self.k = min(k, len(self.templates))
        self.thresholds = dict(thresholds or {})
        self.missing_point_penalty = missing_point_penalty
        self.comparison_frames = comparison_frames
        self.require_full_consensus = require_full_consensus
        self.feature_indices = (
            tuple(range(len(FEATURE_NAMES)))
            if feature_indices is None
            else tuple(feature_indices)
        )
        if not self.feature_indices:
            raise ValueError("feature_indices must not be empty")
        if any(
            index < 0 or index >= len(FEATURE_NAMES)
            for index in self.feature_indices
        ):
            raise ValueError("feature_indices contains an out-of-range index")
        if len(set(self.feature_indices)) != len(self.feature_indices):
            raise ValueError("feature_indices must be unique")
        self._runtime_templates = tuple(
            MotionTemplate(
                template.motion_code,
                template.sample_id,
                tuple(
                    item.points
                    if isinstance(item, NormalizedLandmarkFrame)
                    else item
                    for item in resample_sequence(
                        template.frames,
                        comparison_frames,
                    )
                ),
            )
            for template in self.templates
        )
        self._numpy_template_batches = (
            _build_numpy_template_batches(
                self._runtime_templates,
                feature_indices=self.feature_indices,
            )
            if _np is not None
            else None
        )
        for motion_code, threshold in self.thresholds.items():
            if not math.isfinite(threshold) or threshold <= 0:
                raise ValueError(f"threshold for {motion_code} must be positive")

    def classify(
        self, window: Sequence[NormalizedLandmarkFrame]
    ) -> ClassificationResult:
        if not window:
            raise ValueError("classification window must not be empty")
        distances = []
        comparison_window = resample_sequence(
            window,
            self.comparison_frames,
        )
        if self._numpy_template_batches is None or _np is None:
            for template in self._runtime_templates:
                window_items = tuple(
                    _select_features(item, self.feature_indices)
                    for item in comparison_window
                )
                template_items = tuple(
                    _select_features(frame, self.feature_indices)
                    for frame in template.frames
                )
                distance = dtw_distance(
                    window_items,
                    template_items,
                    missing_point_penalty=self.missing_point_penalty,
                )
                distances.append((template, distance))
        else:
            # All registered and current windows use the same temporal
            # representation, so every template can be aligned in one batch.
            window_arrays = _numpy_arrays(
                comparison_window,
                feature_indices=self.feature_indices,
            )
            for template_indices, lengths, values, valid, weights in (
                self._numpy_template_batches
            ):
                batch_distances = _numpy_dtw_distances(
                    window_arrays,
                    values,
                    valid,
                    weights,
                    lengths,
                    missing_point_penalty=self.missing_point_penalty,
                )
                distances.extend(
                    (
                    self.templates[template_indices[offset]],
                        distance,
                    )
                    for offset, distance in enumerate(batch_distances)
                )
        neighbors = tuple(
            Neighbor(template.motion_code, template.sample_id, distance)
            for template, distance in sorted(
                distances,
                key=lambda item: (item[1], item[0].motion_code, item[0].sample_id),
            )[: self.k]
        )
        if not neighbors or not any(math.isfinite(item.distance) for item in neighbors):
            return ClassificationResult(None, 0.0, math.inf, neighbors)

        # A registered sample can be replayed exactly after the same
        # normalization/EMA pipeline. In that case, the nearest sample is
        # stronger evidence than a k-NN vote made up of two merely similar
        # samples from another class. This is class-agnostic and also makes
        # adding a new motion behave predictably from its first registration.
        nearest = neighbors[0]
        second_distance = (
            neighbors[1].distance if len(neighbors) > 1 else math.inf
        )
        if (
            nearest.distance <= DEFAULT_NEAR_EXACT_MATCH_DISTANCE
            and nearest.distance <= second_distance * DEFAULT_NEAR_EXACT_RATIO
        ):
            threshold = self.thresholds.get(
                nearest.motion_code,
                DEFAULT_DTW_THRESHOLD,
            )
            confidence = max(
                0.0,
                min(1.0, 1.0 - nearest.distance / threshold),
            )
            return ClassificationResult(
                nearest.motion_code,
                confidence,
                nearest.distance,
                neighbors,
                True,
            )
        if self.require_full_consensus and len(
            {item.motion_code for item in neighbors}
        ) > 1:
            return ClassificationResult(None, 0.0, neighbors[0].distance, neighbors)

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
        nearest_distance = neighbors[0].distance
        threshold = self.thresholds.get(winner, DEFAULT_DTW_THRESHOLD)
        if nearest_distance > threshold:
            return ClassificationResult(None, 0.0, nearest_distance, neighbors)
        confidence = max(0.0, min(1.0, 1.0 - nearest_distance / threshold))
        return ClassificationResult(winner, confidence, nearest_distance, neighbors)


def _select_features(
    item: PointSequence | NormalizedLandmarkFrame,
    feature_indices: Sequence[int],
) -> PointSequence | _FeatureFrame:
    if isinstance(item, NormalizedLandmarkFrame):
        assert item.observed is not None
        assert item.weights is not None
        return _FeatureFrame(
            item.captured_at,
            tuple(item.points[index] for index in feature_indices),
            tuple(item.weights[index] for index in feature_indices),
        )
    return tuple(item[index] for index in feature_indices)


def _numpy_arrays(
    sequence: Sequence[PointSequence | NormalizedLandmarkFrame],
    *,
    feature_indices: Sequence[int] | None = None,
) -> tuple[Any, Any, Any]:
    assert _np is not None
    indices = (
        tuple(range(len(FEATURE_NAMES)))
        if feature_indices is None
        else tuple(feature_indices)
    )
    values = _np.zeros((len(sequence), len(indices), 3), dtype=_np.float64)
    valid = _np.zeros((len(sequence), len(indices)), dtype=_np.bool_)
    weights = _np.zeros((len(sequence), len(indices)), dtype=_np.float64)
    for frame_index, item in enumerate(sequence):
        points = _points(item)
        item_weights = _weights(item)
        for local_index, point_index in enumerate(indices):
            point = points[local_index] if feature_indices is None else points[point_index]
            if point is not None:
                values[frame_index, local_index] = point
                valid[frame_index, local_index] = True
                source_index = local_index if feature_indices is None else point_index
                weights[frame_index, local_index] = item_weights[source_index]
    return values, valid, weights


def _build_numpy_template_batches(
    templates: Sequence[MotionTemplate],
    *,
    batch_size: int = 8,
    feature_indices: Sequence[int] | None = None,
) -> tuple[tuple[tuple[int, ...], tuple[int, ...], Any, Any, Any], ...]:
    assert _np is not None
    batches = []
    by_length: dict[int, list[int]] = {}
    for index, template in enumerate(templates):
        by_length.setdefault(len(template.frames), []).append(index)
    for template_indices in by_length.values():
        for start in range(0, len(template_indices), batch_size):
            batch_indices = tuple(template_indices[start : start + batch_size])
            template_arrays = [
                _numpy_arrays(
                    templates[index].frames,
                    feature_indices=feature_indices,
                )
                for index in batch_indices
            ]
            max_frames = max(
                values.shape[0] for values, _, _ in template_arrays
            )
            feature_count = template_arrays[0][0].shape[1]
            values = _np.zeros(
                (len(template_arrays), max_frames, feature_count, 3),
                dtype=_np.float64,
            )
            valid = _np.zeros(
                (len(template_arrays), max_frames, feature_count),
                dtype=_np.bool_,
            )
            weights = _np.zeros(
                (len(template_arrays), max_frames, feature_count),
                dtype=_np.float64,
            )
            lengths = []
            for index, (template_values, template_valid, template_weights) in enumerate(
                template_arrays
            ):
                length = template_values.shape[0]
                values[index, :length] = template_values
                valid[index, :length] = template_valid
                weights[index, :length] = template_weights
                lengths.append(length)
            batches.append(
                (batch_indices, tuple(lengths), values, valid, weights)
            )
    return tuple(batches)


def _numpy_dtw_distances(
    window_arrays: tuple[Any, Any, Any],
    template_values: Any,
    template_valid: Any,
    template_weights: Any,
    template_lengths: Sequence[int],
    *,
    missing_point_penalty: float,
) -> list[float]:
    assert _np is not None
    window_values, window_valid, window_weights = window_arrays
    coordinate_distance = _np.sqrt(
        _np.sum(
            (
                window_values[None, :, None, :, :]
                - template_values[:, None, :, :, :]
            )
            ** 2,
            axis=4,
        )
    )
    both_valid = window_valid[None, :, None, :] & template_valid[:, None, :, :]
    one_missing = window_valid[None, :, None, :] ^ template_valid[:, None, :, :]
    both_weights = _np.minimum(
        window_weights[None, :, None, :],
        template_weights[:, None, :, :],
    )
    one_missing_weights = _np.maximum(
        window_weights[None, :, None, :],
        template_weights[:, None, :, :],
    )
    local_distances = _np.where(
        both_valid,
        coordinate_distance * both_weights,
        0.0,
    )
    local_distances += _np.where(
        one_missing,
        missing_point_penalty * one_missing_weights,
        0.0,
    )
    support = _np.where(
        both_valid,
        both_weights,
        _np.where(one_missing, one_missing_weights, 0.0),
    )
    local_distances = local_distances.sum(axis=3) / _np.maximum(
        support.sum(axis=3),
        1e-12,
    )
    if len(set(template_lengths)) == 1:
        return _dtw_from_local_distances_batch(
            local_distances[:, :, : template_lengths[0]]
        )
    return [
        _dtw_from_local_distances(
            local_distances[index, :, :length].tolist()
        )
        for index, length in enumerate(template_lengths)
    ]


def _dtw_from_local_distances_batch(local_distances: Any) -> list[float]:
    """Align a batch of equal-sized matrices with vectorized DP cells."""

    assert _np is not None
    batch_size, rows, columns = local_distances.shape
    costs = _np.full(
        (batch_size, rows + 1, columns + 1),
        _np.inf,
        dtype=_np.float64,
    )
    path_lengths = _np.zeros(
        (batch_size, rows + 1, columns + 1),
        dtype=_np.int32,
    )
    costs[:, 0, 0] = 0.0
    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            previous_costs = _np.stack(
                (
                    costs[:, row - 1, column],
                    costs[:, row, column - 1],
                    costs[:, row - 1, column - 1],
                ),
                axis=1,
            )
            choices = _np.argmin(previous_costs, axis=1)
            selected_costs = previous_costs[
                _np.arange(batch_size), choices
            ]
            previous_lengths = _np.stack(
                (
                    path_lengths[:, row - 1, column],
                    path_lengths[:, row, column - 1],
                    path_lengths[:, row - 1, column - 1],
                ),
                axis=1,
            )
            costs[:, row, column] = (
                selected_costs + local_distances[:, row - 1, column - 1]
            )
            path_lengths[:, row, column] = (
                previous_lengths[_np.arange(batch_size), choices] + 1
            )
    return (
        costs[:, rows, columns]
        / _np.maximum(path_lengths[:, rows, columns], 1)
    ).tolist()


def _dtw_from_local_distances(local_distances: list[list[float]]) -> float:
    """Align a precomputed frame-distance matrix and normalize its path."""

    rows = len(local_distances)
    columns = len(local_distances[0]) if rows else 0
    costs = [[math.inf] * (columns + 1) for _ in range(rows + 1)]
    predecessors: list[list[tuple[int, int] | None]] = [
        [None] * (columns + 1) for _ in range(rows + 1)
    ]
    costs[0][0] = 0.0
    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            candidates = (
                (costs[row - 1][column], (row - 1, column)),
                (costs[row][column - 1], (row, column - 1)),
                (costs[row - 1][column - 1], (row - 1, column - 1)),
            )
            previous_cost, previous_cell = min(candidates, key=lambda item: item[0])
            costs[row][column] = previous_cost + local_distances[row - 1][column - 1]
            predecessors[row][column] = previous_cell

    row = rows
    column = columns
    path_length = 0
    while row or column:
        previous = predecessors[row][column]
        if previous is None:
            raise ValueError("DTW could not construct an alignment path")
        path_length += 1
        row, column = previous
    return costs[-1][-1] / max(path_length, 1)
