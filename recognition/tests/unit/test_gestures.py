from datetime import datetime, timedelta, timezone

from gesture_recognition.domain.models import HandObservation, Landmark, LandmarkFrame
from gesture_recognition.gestures.engine import GestureEngine
from gesture_recognition.gestures.rules import (
    FingerSnapRule,
    RightHandRaisedRule,
    SwipeRightRule,
)


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


def _snap_hand(extended: bool) -> HandObservation:
    points = [Landmark(0.5, 0.5) for _ in range(21)]
    # Thumb: bent/near middle finger in preparation, extended after release.
    points[2] = Landmark(0.48, 0.5)
    points[3] = Landmark(0.45, 0.47)
    points[4] = Landmark(0.42, 0.44) if not extended else Landmark(0.28, 0.34)
    # Index: curled in preparation, straight after release.
    points[5] = Landmark(0.55, 0.5)
    points[6] = Landmark(0.54, 0.46)
    points[8] = Landmark(0.55, 0.43) if not extended else Landmark(0.55, 0.2)
    # Middle, ring, and little fingers stay curled.
    for mcp, pip, tip in ((9, 10, 12), (13, 14, 16), (17, 18, 20)):
        points[mcp] = Landmark(0.5, 0.5)
        points[pip] = Landmark(0.47, 0.45)
        points[tip] = Landmark(0.5, 0.48)
    points[0] = Landmark(0.5, 0.6)
    return HandObservation("Right", tuple(points))


def test_finger_snap_is_a_preparation_to_release_transition() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = FingerSnapRule()

    assert rule.update(LandmarkFrame(at, {}, (_snap_hand(False),))) is None
    detection = rule.update(LandmarkFrame(at + timedelta(milliseconds=100), {}, (_snap_hand(True),)))
    assert detection is not None
    assert detection.motion_code == "MOTION_FINGER_SNAP"
    assert rule.update(LandmarkFrame(at + timedelta(milliseconds=200), {}, (_snap_hand(True),))) is None


def test_finger_snap_requires_preparation_state() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = FingerSnapRule()

    assert rule.update(LandmarkFrame(at, {}, (_snap_hand(True),))) is None
