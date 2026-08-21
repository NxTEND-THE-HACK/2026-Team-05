from datetime import datetime, timedelta, timezone

from gesture_recognition.domain.models import HandObservation, Landmark, LandmarkFrame
from gesture_recognition.gestures.engine import GestureEngine
from gesture_recognition.gestures.registry import default_engine, default_rules
from gesture_recognition.gestures.rules import (
    ClapRule,
    FingerSnapRule,
    HandRotateLeftRule,
    HandRotateRightRule,
    LeftHandRaisedRule,
    OpenToFistDownRule,
    RightHandRaisedRule,
    SwipeLeftRule,
    SwipeRightRule,
    ThumbsDownMoveDownRule,
    ThumbsUpMoveUpRule,
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


def test_raised_pose_cooldown_blocks_quick_retrigger() -> None:
    start = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = RightHandRaisedRule(cooldown_seconds=0.75)

    assert rule.update(_frame(start)) is None
    assert rule.update(_frame(start + timedelta(seconds=0.5))) is not None
    assert rule.update(_frame(start + timedelta(seconds=0.6), wrist_y=0.52)) is None
    assert rule.update(_frame(start + timedelta(seconds=0.7))) is None
    assert rule.update(_frame(start + timedelta(seconds=1.3))) is not None


def test_swipe_right_fires_once_until_wrist_returns() -> None:
    start = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = SwipeRightRule(movement_threshold=0.15)

    assert rule.update(_frame(start, wrist_x=0.55)) is None
    detection = rule.update(_frame(start + timedelta(milliseconds=100), wrist_x=0.35))
    assert detection is not None
    assert detection.motion_code == "MOTION_SWIPE_RIGHT"
    assert rule.update(_frame(start + timedelta(milliseconds=200), wrist_x=0.15)) is None
    assert rule.update(_frame(start + timedelta(milliseconds=300), wrist_x=0.55)) is None
    detection = rule.update(_frame(start + timedelta(milliseconds=400), wrist_x=0.4))
    assert detection is not None
    assert detection.motion_code == "MOTION_SWIPE_RIGHT"


def test_swipe_right_does_not_require_hand_landmarker_output() -> None:
    start = datetime(2026, 8, 5, tzinfo=timezone.utc)
    initial = _frame(start, wrist_x=0.55)
    moved = _frame(start + timedelta(milliseconds=100), wrist_x=0.35)

    rule = SwipeRightRule(movement_threshold=0.18)
    assert rule.update(LandmarkFrame(initial.captured_at, initial.pose, ())) is None
    result = rule.update(LandmarkFrame(moved.captured_at, moved.pose, ()))
    assert result is not None
    assert result.motion_code == "MOTION_SWIPE_RIGHT"


def test_default_swipe_right_ignores_small_daily_wrist_motion() -> None:
    start = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = SwipeRightRule()

    assert rule.update(_frame(start, wrist_x=0.55)) is None
    assert rule.update(
        _frame(start + timedelta(milliseconds=100), wrist_x=0.34)
    ) is None
    detection = rule.update(
        _frame(start + timedelta(milliseconds=200), wrist_x=0.28)
    )
    assert detection is not None
    assert detection.motion_code == "MOTION_SWIPE_RIGHT"


def test_default_swipe_right_rejects_large_diagonal_motion() -> None:
    start = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = SwipeRightRule()

    assert rule.update(_frame(start, wrist_x=0.55, wrist_y=0.50)) is None
    assert rule.update(
        _frame(
            start + timedelta(milliseconds=200),
            wrist_x=0.28,
            wrist_y=0.30,
        )
    ) is None


def test_swipe_requires_a_chest_like_start_region_when_shoulders_are_available() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    shoulders = {
        "LEFT_SHOULDER": Landmark(0.55, 0.55, visibility=0.9),
        "RIGHT_SHOULDER": Landmark(0.45, 0.55, visibility=0.9),
    }

    def frame_at(index: int, x: float, y: float) -> LandmarkFrame:
        return LandmarkFrame(
            at + timedelta(milliseconds=index * 100),
            {
                **shoulders,
                "RIGHT_WRIST": Landmark(x, y, visibility=0.9),
            },
            (),
        )

    rule = SwipeRightRule(movement_threshold=0.12)
    assert rule.update(frame_at(0, 0.9, 0.6)) is None
    assert rule.update(frame_at(1, 0.55, 0.7)) is None
    detection = rule.update(frame_at(2, 0.35, 0.55))
    assert detection is not None
    assert detection.motion_code == "MOTION_SWIPE_RIGHT"


def test_left_hand_raise_and_swipe_are_supported() -> None:
    start = datetime(2026, 8, 5, tzinfo=timezone.utc)
    pose = {
        "LEFT_WRIST": Landmark(0.55, 0.2, visibility=0.9),
        "LEFT_ELBOW": Landmark(0.55, 0.45, visibility=0.9),
        "LEFT_SHOULDER": Landmark(0.55, 0.55, visibility=0.9),
    }
    hand = HandObservation("Left", tuple(Landmark(0.6, 0.3) for _ in range(21)))
    frame = lambda at, x=0.55: LandmarkFrame(
        at,
        {**pose, "LEFT_WRIST": Landmark(x, 0.2, visibility=0.9)},
        (hand,),
    )

    raised = LeftHandRaisedRule(hold_seconds=0.4)
    assert raised.update(frame(start)) is None
    detection = raised.update(frame(start + timedelta(seconds=0.5)))
    assert detection is not None
    assert detection.motion_code == "POSE_LEFT_HAND_UP"

    swipe = SwipeLeftRule(movement_threshold=0.12)
    assert swipe.update(frame(start, x=0.55)) is None
    detection = swipe.update(frame(start + timedelta(milliseconds=100), x=0.7))
    assert detection is not None
    assert detection.motion_code == "MOTION_SWIPE_LEFT"


def test_left_swipe_rebaselines_after_the_hand_returns_toward_the_chest() -> None:
    start = datetime(2026, 8, 5, tzinfo=timezone.utc)
    pose = {
        "LEFT_WRIST": Landmark(0.55, 0.2, visibility=0.9),
        "LEFT_ELBOW": Landmark(0.55, 0.45, visibility=0.9),
        "LEFT_SHOULDER": Landmark(0.55, 0.55, visibility=0.9),
    }
    hand = HandObservation("Left", tuple(Landmark(0.6, 0.3) for _ in range(21)))

    def frame_at(index: int, x: float) -> LandmarkFrame:
        return LandmarkFrame(
            start + timedelta(milliseconds=index * 100),
            {**pose, "LEFT_WRIST": Landmark(x, 0.2, visibility=0.9)},
            (hand,),
        )

    rule = SwipeLeftRule(movement_threshold=0.12)
    assert rule.update(frame_at(0, 0.55)) is None
    assert rule.update(frame_at(1, 0.7)) is not None
    assert rule.update(frame_at(2, 0.9)) is None
    assert rule.update(frame_at(3, 0.72)) is None
    assert rule.update(frame_at(4, 0.6)) is None
    detection = rule.update(frame_at(5, 0.75))
    assert detection is not None
    assert detection.motion_code == "MOTION_SWIPE_LEFT"


def test_engine_rejects_duplicate_codes() -> None:
    rule = RightHandRaisedRule()
    try:
        GestureEngine((rule, rule))
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("duplicate motion codes should fail")


def test_default_engine_registers_every_rule_with_a_unique_code() -> None:
    engine = default_engine()
    assert engine is not None


def test_default_rules_can_disable_selected_motions() -> None:
    rules = default_rules(
        disabled_motions=(
            "MOTION_CLAP",
            "MOTION_HAND_ROTATE_RIGHT",
            "MOTION_HAND_ROTATE_LEFT",
        )
    )
    codes = {rule.motion_code for rule in rules}

    assert "MOTION_CLAP" not in codes
    assert "MOTION_HAND_ROTATE_RIGHT" not in codes
    assert "MOTION_HAND_ROTATE_LEFT" not in codes


def test_engine_resets_rules_after_a_capture_gap() -> None:
    start = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = SwipeRightRule(movement_threshold=0.15)
    engine = GestureEngine((rule,), reset_after_gap_seconds=0.5)

    assert engine.update(_frame(start, wrist_x=0.55)) == ()
    assert engine.update(
        _frame(start + timedelta(milliseconds=100), wrist_x=0.35)
    )[0].motion_code == "MOTION_SWIPE_RIGHT"
    assert engine.update(
        _frame(start + timedelta(seconds=1.0), wrist_x=0.35)
    ) == ()
    assert engine.update(
        _frame(start + timedelta(seconds=1.1), wrist_x=0.15)
    )[0].motion_code == "MOTION_SWIPE_RIGHT"


def _snap_hand(extended: bool) -> HandObservation:
    points = [Landmark(0.5, 0.5) for _ in range(21)]
    # Thumb: bent/near middle finger in preparation, extended after release.
    points[2] = Landmark(0.48, 0.5)
    points[3] = Landmark(0.45, 0.47)
    points[4] = (
        Landmark(0.42, 0.44)
        if not extended
        else Landmark(0.50, 0.48)
    )
    if extended:
        points[2] = Landmark(0.42, 0.56)
        points[3] = Landmark(0.46, 0.54)
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
    rule = FingerSnapRule(minimum_wrist_displacement=0.0)

    assert rule.update(LandmarkFrame(at, {}, (_snap_hand(False),))) is None
    detection = rule.update(LandmarkFrame(at + timedelta(milliseconds=100), {}, (_snap_hand(True),)))
    assert detection is not None
    assert detection.motion_code == "MOTION_FINGER_SNAP"
    assert rule.update(LandmarkFrame(at + timedelta(milliseconds=200), {}, (_snap_hand(True),))) is None


def test_finger_snap_requires_preparation_state() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = FingerSnapRule()

    assert rule.update(LandmarkFrame(at, {}, (_snap_hand(True),))) is None


def test_finger_snap_rejects_a_stationary_shape_change() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = FingerSnapRule()

    assert rule.update(LandmarkFrame(at, {}, (_snap_hand(False),))) is None
    assert rule.update(
        LandmarkFrame(
            at + timedelta(milliseconds=100),
            {},
            (_snap_hand(True),),
        )
    ) is None


def _thumb_hand(pose: str, wrist_y: float = 0.6) -> HandObservation:
    points = [Landmark(0.5, wrist_y) for _ in range(21)]
    points[0] = Landmark(0.5, wrist_y)
    points[2] = Landmark(0.4, wrist_y - 0.05 if pose == "up" else wrist_y + 0.05)
    points[3] = Landmark(0.35, wrist_y - 0.15 if pose == "up" else wrist_y + 0.15)
    points[4] = Landmark(0.35, wrist_y - 0.35 if pose == "up" else wrist_y + 0.35)
    for mcp, pip, tip in ((9, 10, 12), (13, 14, 16), (17, 18, 20)):
        points[mcp] = Landmark(0.5, wrist_y)
        points[pip] = Landmark(0.5, wrist_y - 0.05)
        points[tip] = Landmark(0.55, wrist_y - 0.04)
    return HandObservation("Right", tuple(points))


def test_thumbs_up_move_up_and_thumbs_down_move_down() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)

    # This case verifies re-arming mechanics independently of the default
    # anti-jitter cooldown.
    thumbs_up = ThumbsUpMoveUpRule(
        cooldown_seconds=0.0,
        minimum_pose_frames=3,
        movement_threshold=0.12,
    )
    assert thumbs_up.update(LandmarkFrame(at, {}, (_thumb_hand("up", 0.6),))) is None
    assert thumbs_up.update(
        LandmarkFrame(at + timedelta(milliseconds=50), {}, (_thumb_hand("up", 0.55),))
    ) is None
    detection = thumbs_up.update(
        LandmarkFrame(at + timedelta(milliseconds=100), {}, (_thumb_hand("up", 0.48),))
    )
    assert detection is not None
    assert detection.motion_code == "MOTION_THUMBS_UP_MOVE_UP"
    assert thumbs_up.update(
        LandmarkFrame(at + timedelta(milliseconds=200), {}, (_thumb_hand("up", 0.6),))
    ) is None
    assert thumbs_up.update(
        LandmarkFrame(at + timedelta(milliseconds=250), {}, (_thumb_hand("up", 0.55),))
    ) is None
    detection = thumbs_up.update(
        LandmarkFrame(at + timedelta(milliseconds=300), {}, (_thumb_hand("up", 0.48),))
    )
    assert detection is not None
    assert detection.motion_code == "MOTION_THUMBS_UP_MOVE_UP"

    thumbs_down = ThumbsDownMoveDownRule(
        cooldown_seconds=0.0,
        minimum_pose_frames=3,
    )
    down_pose = {
        "RIGHT_WRIST": Landmark(0.5, 0.45, visibility=0.9),
        "LEFT_SHOULDER": Landmark(0.6, 0.5, visibility=0.9),
        "RIGHT_SHOULDER": Landmark(0.4, 0.5, visibility=0.9),
    }
    assert thumbs_down.update(
        LandmarkFrame(at, down_pose, (_thumb_hand("down", 0.45),))
    ) is None
    assert thumbs_down.update(
        LandmarkFrame(
            at + timedelta(milliseconds=100),
            down_pose,
            (_thumb_hand("down", 0.45),),
        )
    ) is None
    assert thumbs_down.update(
        LandmarkFrame(
            at + timedelta(milliseconds=200),
            down_pose,
            (_thumb_hand("down", 0.45),),
        )
    ) is None
    detection = thumbs_down.update(
        LandmarkFrame(
            at + timedelta(milliseconds=300),
            {**down_pose, "RIGHT_WRIST": Landmark(0.5, 0.65, visibility=0.9)},
            (),
        )
    )
    assert detection is not None
    assert detection.motion_code == "MOTION_THUMBS_DOWN_MOVE_DOWN"
    assert thumbs_down.update(
        LandmarkFrame(
            at + timedelta(milliseconds=400),
            {**down_pose, "RIGHT_WRIST": Landmark(0.5, 0.47, visibility=0.9)},
            (_thumb_hand("down", 0.47),),
        )
    ) is None
    detection = thumbs_down.update(
        LandmarkFrame(
            at + timedelta(milliseconds=500),
            {**down_pose, "RIGHT_WRIST": Landmark(0.5, 0.47, visibility=0.9)},
            (_thumb_hand("down", 0.47),),
        )
    )
    assert detection is None
    assert thumbs_down.update(
        LandmarkFrame(
            at + timedelta(milliseconds=600),
            {**down_pose, "RIGHT_WRIST": Landmark(0.5, 0.47, visibility=0.9)},
            (_thumb_hand("down", 0.47),),
        )
    ) is None
    assert thumbs_down.update(
        LandmarkFrame(
            at + timedelta(milliseconds=700),
            {**down_pose, "RIGHT_WRIST": Landmark(0.47, 0.47, visibility=0.9)},
            (_thumb_hand("down", 0.47),),
        )
    ) is None
    detection = thumbs_down.update(
        LandmarkFrame(
            at + timedelta(milliseconds=800),
            {**down_pose, "RIGHT_WRIST": Landmark(0.5, 0.75, visibility=0.9)},
            (),
        )
    )
    # A continuous sequence cannot emit a duplicate after the first event.
    assert detection is None


def test_thumbs_down_conflicting_good_pose_clears_latch_safely() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = ThumbsDownMoveDownRule(
        cooldown_seconds=0.0,
        minimum_pose_frames=3,
    )
    pose = {
        "RIGHT_WRIST": Landmark(0.5, 0.45, visibility=0.9),
        "LEFT_SHOULDER": Landmark(0.6, 0.5, visibility=0.9),
        "RIGHT_SHOULDER": Landmark(0.4, 0.5, visibility=0.9),
    }

    for offset in (0, 100, 200):
        assert rule.update(
            LandmarkFrame(
                at + timedelta(milliseconds=offset),
                pose,
                (_thumb_hand("down", 0.45),),
            )
        ) is None
    detection = rule.update(
        LandmarkFrame(
            at + timedelta(milliseconds=300),
            {**pose, "RIGHT_WRIST": Landmark(0.5, 0.65, visibility=0.9)},
            (),
        )
    )
    assert detection is not None

    good_pose = {**pose, "RIGHT_WRIST": Landmark(0.5, 0.65, visibility=0.9)}
    assert rule.update(
        LandmarkFrame(
            at + timedelta(milliseconds=400),
            good_pose,
            (_thumb_hand("up", 0.65),),
        )
    ) is None
    # The following frame used to raise AssertionError because the Good pose
    # cleared _gate_baseline_y but left _latched set.
    assert rule.update(
        LandmarkFrame(
            at + timedelta(milliseconds=500),
            good_pose,
            (_thumb_hand("up", 0.65),),
        )
    ) is None


def test_thumbs_down_rejects_a_low_stationary_bad_pose() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = ThumbsDownMoveDownRule()
    shoulders = {
        "LEFT_SHOULDER": Landmark(0.6, 0.5, visibility=0.9),
        "RIGHT_SHOULDER": Landmark(0.4, 0.5, visibility=0.9),
    }

    assert rule.update(
        LandmarkFrame(
            at,
            {
                **shoulders,
                "RIGHT_WRIST": Landmark(0.5, 0.45, visibility=0.9),
            },
            (),
        )
    ) is None
    for index in range(1, 5):
        assert rule.update(
            LandmarkFrame(
                at + timedelta(milliseconds=index * 100),
                {
                    **shoulders,
                    "RIGHT_WRIST": Landmark(0.5, 0.75, visibility=0.9),
                },
                (_thumb_hand("down", 0.75),),
            )
        ) is None


def test_thumbs_down_is_suppressed_while_the_other_hand_is_swiping_left() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = ThumbsDownMoveDownRule(cooldown_seconds=0.0)
    shoulders = {
        "LEFT_SHOULDER": Landmark(0.6, 0.5, visibility=0.9),
        "RIGHT_SHOULDER": Landmark(0.4, 0.5, visibility=0.9),
    }

    def frame_at(
        milliseconds: int,
        *,
        left_wrist_x: float,
        right_wrist_y: float,
        with_right_hand: bool = True,
    ) -> LandmarkFrame:
        pose = {
            **shoulders,
            "LEFT_WRIST": Landmark(left_wrist_x, 0.65, visibility=0.9),
            "RIGHT_WRIST": Landmark(0.5, right_wrist_y, visibility=0.9),
        }
        hands = (_thumb_hand("down", right_wrist_y),) if with_right_hand else ()
        return LandmarkFrame(at + timedelta(milliseconds=milliseconds), pose, hands)

    # Establish a Bad gate while the left hand is still at the chest.
    assert rule.update(frame_at(0, left_wrist_x=0.50, right_wrist_y=0.45)) is None
    assert rule.update(frame_at(100, left_wrist_x=0.50, right_wrist_y=0.45)) is None
    assert rule.update(frame_at(200, left_wrist_x=0.50, right_wrist_y=0.45)) is None

    # The left swipe becomes active before the right wrist moves down.  That
    # cross-hand motion must invalidate the pending Bad sequence.
    assert rule.update(frame_at(300, left_wrist_x=0.75, right_wrist_y=0.45)) is None
    assert rule.update(
        frame_at(400, left_wrist_x=0.85, right_wrist_y=0.65, with_right_hand=False)
    ) is None


def test_thumbs_up_cooldown_blocks_a_quick_duplicate() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = ThumbsUpMoveUpRule(
        minimum_pose_frames=3,
        movement_threshold=0.12,
    )

    assert rule.update(LandmarkFrame(at, {}, (_thumb_hand("up", 0.6),))) is None
    assert rule.update(
        LandmarkFrame(at + timedelta(milliseconds=100), {}, (_thumb_hand("up", 0.55),))
    ) is None
    assert rule.update(
        LandmarkFrame(at + timedelta(milliseconds=200), {}, (_thumb_hand("up", 0.48),))
    ) is not None
    assert rule.update(
        LandmarkFrame(at + timedelta(milliseconds=300), {}, (_thumb_hand("up", 0.6),))
    ) is None
    assert rule.update(
        LandmarkFrame(at + timedelta(milliseconds=400), {}, (_thumb_hand("up", 0.55),))
    ) is None
    assert rule.update(
        LandmarkFrame(at + timedelta(milliseconds=500), {}, (_thumb_hand("up", 0.48),))
    ) is None


def test_clap_requires_hands_to_move_from_apart_to_contact() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = ClapRule()
    apart = {
        "LEFT_WRIST": Landmark(0.2, 0.4, visibility=0.9),
        "RIGHT_WRIST": Landmark(0.8, 0.4, visibility=0.9),
        "LEFT_SHOULDER": Landmark(0.4, 0.5, visibility=0.9),
        "RIGHT_SHOULDER": Landmark(0.6, 0.5, visibility=0.9),
    }
    close = {
        **apart,
        "LEFT_WRIST": Landmark(0.47, 0.4, visibility=0.9),
        "RIGHT_WRIST": Landmark(0.53, 0.4, visibility=0.9),
    }

    assert rule.update(LandmarkFrame(at, apart, ())) is None
    detection = rule.update(
        LandmarkFrame(at + timedelta(milliseconds=100), close, ())
    )
    assert detection is not None
    assert detection.motion_code == "MOTION_CLAP"


def test_clap_rejects_slow_or_low_hand_contact() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    apart = {
        "LEFT_WRIST": Landmark(0.2, 0.4, visibility=0.9),
        "RIGHT_WRIST": Landmark(0.8, 0.4, visibility=0.9),
        "LEFT_SHOULDER": Landmark(0.4, 0.5, visibility=0.9),
        "RIGHT_SHOULDER": Landmark(0.6, 0.5, visibility=0.9),
    }
    near = {
        **apart,
        "LEFT_WRIST": Landmark(0.455, 0.4, visibility=0.9),
        "RIGHT_WRIST": Landmark(0.545, 0.4, visibility=0.9),
    }
    close = {
        **apart,
        "LEFT_WRIST": Landmark(0.47, 0.4, visibility=0.9),
        "RIGHT_WRIST": Landmark(0.53, 0.4, visibility=0.9),
    }

    slow = ClapRule()
    assert slow.update(LandmarkFrame(at, apart, ())) is None
    assert slow.update(
        LandmarkFrame(at + timedelta(milliseconds=100), near, ())
    ) is None
    assert slow.update(
        LandmarkFrame(at + timedelta(milliseconds=200), close, ())
    ) is None

    low = ClapRule()
    low_contact = {
        **close,
        "LEFT_WRIST": Landmark(0.47, 0.65, visibility=0.9),
        "RIGHT_WRIST": Landmark(0.53, 0.65, visibility=0.9),
    }
    assert low.update(LandmarkFrame(at, apart, ())) is None
    assert low.update(
        LandmarkFrame(at + timedelta(milliseconds=100), low_contact, ())
    ) is None


def _rotation_frame(
    at: datetime,
    *,
    side: str,
    angle: float,
) -> LandmarkFrame:
    import math

    wrist_name = f"{side.upper()}_WRIST"
    radians = math.radians(angle)
    center_x, center_y = 0.5, 0.4
    half_width = 0.05
    points = [Landmark(center_x, center_y) for _ in range(21)]
    points[0] = Landmark(center_x, center_y)
    points[5] = Landmark(
        center_x - math.cos(radians) * half_width,
        center_y - math.sin(radians) * half_width,
    )
    points[17] = Landmark(
        center_x + math.cos(radians) * half_width,
        center_y + math.sin(radians) * half_width,
    )
    points[9] = Landmark(
        center_x + math.cos(radians) * 0.10,
        center_y + math.sin(radians) * 0.10,
    )
    pose = {wrist_name: Landmark(center_x, center_y, visibility=0.9)}
    hand = HandObservation("Unknown", tuple(points))
    return LandmarkFrame(at, pose, (hand,))


def test_hand_rotate_rules_use_palm_angle_and_rearm_at_baseline() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)

    right = HandRotateRightRule(
        cooldown_seconds=0.0,
        minimum_path_length=0.0,
        maximum_path_length=None,
        minimum_middle_axis_delta=None,
        maximum_middle_axis_delta=None,
        minimum_vertical_displacement=None,
        maximum_vertical_displacement=None,
        minimum_ring_angle=None,
        maximum_ring_angle=None,
    )
    assert right.update(_rotation_frame(at, side="right", angle=0.0)) is None
    assert right.update(
        _rotation_frame(at + timedelta(milliseconds=300), side="right", angle=35.0)
    ) is None
    detection = right.update(
        _rotation_frame(at + timedelta(milliseconds=400), side="right", angle=35.0)
    )
    assert detection is not None
    assert detection.motion_code == "MOTION_HAND_ROTATE_RIGHT"
    assert right.update(
        _rotation_frame(at + timedelta(milliseconds=500), side="right", angle=0.0)
    ) is None
    assert right.update(
        _rotation_frame(at + timedelta(milliseconds=800), side="right", angle=35.0)
    ) is None
    detection = right.update(
        _rotation_frame(at + timedelta(milliseconds=900), side="right", angle=35.0)
    )
    assert detection is not None

    left = HandRotateLeftRule(
        minimum_path_length=0.0,
        maximum_path_length=None,
        minimum_middle_axis_delta=None,
        maximum_middle_axis_delta=None,
        minimum_index_angle_range=None,
        maximum_index_angle_range=None,
    )
    assert left.update(_rotation_frame(at, side="left", angle=0.0)) is None
    assert left.update(
        _rotation_frame(at + timedelta(milliseconds=300), side="left", angle=0.0)
    ) is None
    detection = left.update(
        _rotation_frame(at + timedelta(milliseconds=800), side="left", angle=-35.0)
    )
    assert detection is not None
    assert detection.motion_code == "MOTION_HAND_ROTATE_LEFT"


def test_hand_rotate_rules_use_forearm_reference_and_tolerate_short_hand_gap() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    right = HandRotateRightRule(
        minimum_path_length=0.0,
        maximum_path_length=None,
        minimum_middle_axis_delta=None,
        maximum_middle_axis_delta=None,
        minimum_vertical_displacement=None,
        maximum_vertical_displacement=None,
        minimum_ring_angle=None,
        maximum_ring_angle=None,
    )

    baseline = _rotation_frame(at, side="right", angle=0.0)
    wrist = baseline.pose["RIGHT_WRIST"]
    baseline_pose = dict(baseline.pose)
    baseline_pose["RIGHT_ELBOW"] = Landmark(wrist.x - 0.10, wrist.y)
    assert right.update(
        LandmarkFrame(at, baseline_pose, baseline.hands)
    ) is None

    assert right.update(
        LandmarkFrame(at + timedelta(milliseconds=200), baseline_pose, ())
    ) is None

    rotated = _rotation_frame(
        at + timedelta(milliseconds=300),
        side="right",
        angle=25.0,
    )
    rotated_pose = dict(rotated.pose)
    rotated_pose["RIGHT_ELBOW"] = Landmark(
        rotated.pose["RIGHT_WRIST"].x - 0.10,
        rotated.pose["RIGHT_WRIST"].y,
    )
    assert right.update(
        LandmarkFrame(rotated.captured_at, rotated_pose, rotated.hands)
    ) is None
    confirm = _rotation_frame(
        at + timedelta(milliseconds=400),
        side="right",
        angle=25.0,
    )
    confirm_pose = dict(confirm.pose)
    confirm_pose["RIGHT_ELBOW"] = Landmark(
        confirm.pose["RIGHT_WRIST"].x - 0.10,
        confirm.pose["RIGHT_WRIST"].y,
    )
    detection = right.update(
        LandmarkFrame(confirm.captured_at, confirm_pose, confirm.hands)
    )
    assert detection is not None
    assert detection.motion_code == "MOTION_HAND_ROTATE_RIGHT"


def test_left_hand_rotate_allows_its_longer_tracking_gap() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    left = HandRotateLeftRule(
        minimum_path_length=0.0,
        maximum_path_length=None,
        minimum_middle_axis_delta=None,
        maximum_middle_axis_delta=None,
        minimum_index_angle_range=None,
        maximum_index_angle_range=None,
    )
    assert left.update(_rotation_frame(at, side="left", angle=0.0)) is None
    assert left.update(
        _rotation_frame(at + timedelta(milliseconds=200), side="left", angle=0.0)
    ) is None
    assert left.update(
        LandmarkFrame(at + timedelta(milliseconds=500), {}, ())
    ) is None
    detection = left.update(
        _rotation_frame(at + timedelta(milliseconds=800), side="left", angle=-35.0)
    )
    assert detection is not None
    assert detection.motion_code == "MOTION_HAND_ROTATE_LEFT"


def _open_or_fist_hand(kind: str, wrist_y: float) -> HandObservation:
    points = [Landmark(0.5, wrist_y) for _ in range(21)]
    points[0] = Landmark(0.5, wrist_y)
    if kind == "open":
        for mcp, pip, tip in (
            (5, 6, 8),
            (9, 10, 12),
            (13, 14, 16),
            (17, 18, 20),
        ):
            points[mcp] = Landmark(0.5, wrist_y - 0.05)
            points[pip] = Landmark(0.5, wrist_y - 0.15)
            points[tip] = Landmark(0.5, wrist_y - 0.25)
        points[2] = Landmark(0.4, wrist_y - 0.05)
        points[3] = Landmark(0.35, wrist_y - 0.15)
        points[4] = Landmark(0.3, wrist_y - 0.25)
    else:
        for mcp, pip, tip in (
            (5, 6, 8),
            (9, 10, 12),
            (13, 14, 16),
            (17, 18, 20),
        ):
            points[mcp] = Landmark(0.5, wrist_y - 0.05)
            points[pip] = Landmark(0.5, wrist_y)
            points[tip] = Landmark(0.55, wrist_y - 0.01)
    return HandObservation("Right", tuple(points))


def test_open_to_fist_down_requires_open_start_and_downward_motion() -> None:
    at = datetime(2026, 8, 5, tzinfo=timezone.utc)
    rule = OpenToFistDownRule()
    assert rule.update(
        LandmarkFrame(at, {}, (_open_or_fist_hand("open", 0.2),))
    ) is None
    detection = rule.update(
        LandmarkFrame(
            at + timedelta(milliseconds=100),
            {},
            (_open_or_fist_hand("fist", 0.50),),
        )
    )
    assert detection is not None
    assert detection.motion_code == "MOTION_OPEN_TO_FIST_DOWN"
