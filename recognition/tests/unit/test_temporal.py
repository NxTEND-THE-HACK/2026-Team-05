from datetime import datetime, timedelta, timezone

from gesture_recognition.domain.models import HandObservation, Landmark, LandmarkFrame
from gesture_recognition.gestures.catalog import MOTION_CODES
from gesture_recognition.gestures.temporal import (
    FEATURE_NAMES,
    ExponentialMovingAverage,
    KNNMotionClassifier,
    LandmarkNormalizer,
    MotionTemplate,
    NormalizedLandmarkFrame,
    SlidingWindow,
    dtw_distance,
)


def _landmark_frame(
    at: datetime,
    *,
    shoulder_width: float = 0.4,
    right_wrist_x: float = 0.4,
    visibility: float | None = 0.9,
    with_hand: bool = False,
) -> LandmarkFrame:
    pose = {
        "LEFT_SHOULDER": Landmark(0.5 + shoulder_width / 2, 0.5, visibility=visibility),
        "RIGHT_SHOULDER": Landmark(0.5 - shoulder_width / 2, 0.5, visibility=visibility),
        "RIGHT_WRIST": Landmark(right_wrist_x, 0.3, visibility=visibility),
    }
    hands = ()
    if with_hand:
        hands = (
            HandObservation(
                "Right",
                tuple(Landmark(right_wrist_x, 0.3) for _ in range(21)),
            ),
        )
    return LandmarkFrame(at, pose, hands)


def _normalized_frame(value: float, at: datetime) -> NormalizedLandmarkFrame:
    return NormalizedLandmarkFrame(
        at,
        tuple((value, value, value) for _ in FEATURE_NAMES),
    )


def _template(motion_code: str, value: float) -> MotionTemplate:
    return MotionTemplate(
        motion_code,
        "sample-1",
        (tuple((value, value, value) for _ in FEATURE_NAMES),),
    )


def test_normalizer_uses_shoulder_midpoint_and_width() -> None:
    at = datetime(2026, 8, 12, tzinfo=timezone.utc)
    normalized = LandmarkNormalizer().normalize(
        _landmark_frame(at, shoulder_width=0.4, right_wrist_x=0.3)
    )

    assert normalized is not None
    right_wrist = normalized.points[FEATURE_NAMES.index("POSE_RIGHT_WRIST")]
    assert right_wrist is not None
    assert abs(right_wrist[0] + 0.5) < 1e-9
    assert abs(right_wrist[1] + 0.5) < 1e-9


def test_normalizer_rejects_missing_or_low_visibility_shoulders() -> None:
    at = datetime(2026, 8, 12, tzinfo=timezone.utc)
    assert LandmarkNormalizer().normalize(
        _landmark_frame(at, visibility=0.49)
    ) is None
    assert LandmarkNormalizer().normalize(
        LandmarkFrame(at, {"LEFT_SHOULDER": Landmark(0.4, 0.5)}, ())
    ) is None


def test_normalizer_keeps_hands_in_handedness_slots() -> None:
    at = datetime(2026, 8, 12, tzinfo=timezone.utc)
    normalized = LandmarkNormalizer().normalize(
        _landmark_frame(at, with_hand=True)
    )

    assert normalized is not None
    right_hand = normalized.points[FEATURE_NAMES.index("RIGHT_HAND_0")]
    left_hand = normalized.points[FEATURE_NAMES.index("LEFT_HAND_0")]
    assert right_hand is not None
    assert left_hand is None


def test_ema_applies_alpha_and_resets() -> None:
    at = datetime(2026, 8, 12, tzinfo=timezone.utc)
    ema = ExponentialMovingAverage(alpha=0.4)
    first = ema.update(_normalized_frame(0.0, at))
    second = ema.update(_normalized_frame(1.0, at + timedelta(milliseconds=67)))

    assert first.points[0] == (0.0, 0.0, 0.0)
    assert second.points[0] == (0.4, 0.4, 0.4)
    ema.reset()
    assert ema.update(_normalized_frame(1.0, at)).points[0] == (1.0, 1.0, 1.0)


def test_sliding_window_keeps_only_latest_frames() -> None:
    at = datetime(2026, 8, 12, tzinfo=timezone.utc)
    window = SlidingWindow(max_frames=2)
    window.append(_normalized_frame(1.0, at))
    window.append(_normalized_frame(2.0, at + timedelta(seconds=1)))
    window.append(_normalized_frame(3.0, at + timedelta(seconds=2)))

    assert window.is_full
    assert [frame.points[0][0] for frame in window.snapshot()] == [2.0, 3.0]


def test_dtw_absorbs_different_sequence_speeds() -> None:
    at = datetime(2026, 8, 12, tzinfo=timezone.utc)
    slow = [_normalized_frame(value, at) for value in (0.0, 0.5, 1.0)]
    fast = [_normalized_frame(value, at) for value in (0.0, 0.5, 0.5, 1.0, 1.0)]

    assert dtw_distance(slow, fast) == 0.0
    assert dtw_distance(slow, [_normalized_frame(2.0, at)]) > 0.0


def test_knn_uses_majority_vote_and_average_distance_for_ties() -> None:
    at = datetime(2026, 8, 12, tzinfo=timezone.utc)
    window = (_normalized_frame(0.1, at),)
    templates = (
        _template(MOTION_CODES[0], 0.0),
        _template(MOTION_CODES[0], 0.2),
        _template(MOTION_CODES[1], 0.11),
    )

    result = KNNMotionClassifier(templates, k=3, thresholds={code: 1.0 for code in MOTION_CODES}).classify(window)

    assert result.motion_code == MOTION_CODES[0]
    assert result.confidence > 0.0


def test_knn_returns_unknown_when_distance_exceeds_threshold() -> None:
    at = datetime(2026, 8, 12, tzinfo=timezone.utc)
    result = KNNMotionClassifier(
        (_template(MOTION_CODES[0], 0.0),),
        thresholds={MOTION_CODES[0]: 0.1},
    ).classify((_normalized_frame(1.0, at),))

    assert result.motion_code is None
    assert result.confidence == 0.0
