from datetime import datetime, timedelta, timezone

from gesture_recognition.domain.models import HandObservation, Landmark, LandmarkFrame
from gesture_recognition.gestures.engine import GestureEngine
from gesture_recognition.gestures.rules import RightHandRaisedRule, SwipeRightRule


def _frame(at: datetime, *, wrist_x: float = 0.45, wrist_y: float = 0.25) -> LandmarkFrame:
    pose = {
        "RIGHT_WRIST": Landmark(wrist_x, wrist_y, visibility=0.9),
        "RIGHT_ELBOW": Landmark(0.45, 0.45, visibility=0.9),
        "RIGHT_SHOULDER": Landmark(0.45, 0.55, visibility=0.9),
    }
    hand = HandObservation("Right", tuple(Landmark(0.4, 0.3) for _ in range(21)))
    return LandmarkFrame(at, pose, (hand,))


def test_raised_hand_requires_hold_and_fires_once() -> None:
    start = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = RightHandRaisedRule(hold_seconds=0.5)

    assert rule.update(_frame(start)) is None
    detection = rule.update(_frame(start + timedelta(seconds=0.6)))
    assert detection is not None
    assert detection.motion_code == "POSE_RIGHT_HAND_UP"
    assert rule.update(_frame(start + timedelta(seconds=1.2))) is None

    assert rule.update(_frame(start + timedelta(seconds=1.3), wrist_y=0.52)) is None
    assert rule.update(_frame(start + timedelta(seconds=1.4))) is None


def test_swipe_right_fires_once_until_wrist_returns() -> None:
    start = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = SwipeRightRule(movement_threshold=0.15)

    assert rule.update(_frame(start, wrist_x=0.25)) is None
    detection = rule.update(_frame(start + timedelta(milliseconds=100), wrist_x=0.42))
    assert detection is not None
    assert detection.motion_code == "MOTION_SWIPE_RIGHT"
    assert rule.update(_frame(start + timedelta(milliseconds=200), wrist_x=0.6)) is None
    assert rule.update(_frame(start + timedelta(milliseconds=300), wrist_x=0.25)) is None
    assert rule.update(_frame(start + timedelta(milliseconds=400), wrist_x=0.45)) is None


def test_engine_rejects_duplicate_codes() -> None:
    rule = RightHandRaisedRule()
    try:
        GestureEngine((rule, rule))
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("duplicate motion codes should fail")
