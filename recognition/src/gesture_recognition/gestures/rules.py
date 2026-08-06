"""MVP gesture rules.

The thresholds here are deliberately isolated in rule constructors so the
demo can tune them without changing the worker pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import atan2, degrees, hypot

from ..domain.models import HandObservation, Landmark, LandmarkFrame
from .base import GestureDetection

RIGHT_WRIST = "RIGHT_WRIST"
RIGHT_ELBOW = "RIGHT_ELBOW"
RIGHT_SHOULDER = "RIGHT_SHOULDER"


def _hand(frame: LandmarkFrame, handedness: str) -> HandObservation | None:
    return next(
        (item for item in frame.hands if item.handedness == handedness),
        None,
    )


def _visible(*landmarks: Landmark) -> bool:
    return all(
        landmark.visibility is None or landmark.visibility >= 0.5
        for landmark in landmarks
    )


def _angle(first: Landmark, middle: Landmark, last: Landmark) -> float:
    first_angle = atan2(first.y - middle.y, first.x - middle.x)
    last_angle = atan2(last.y - middle.y, last.x - middle.x)
    value = abs(degrees(first_angle - last_angle))
    return 360.0 - value if value > 180.0 else value


@dataclass(slots=True)
class _HandRaisedRule:
    """Shared held-above-shoulder rule for either hand."""

    handedness: str
    wrist_name: str
    elbow_name: str
    shoulder_name: str
    motion_code: str
    hold_seconds: float = 0.45
    minimum_vertical_gap: float = 0.05
    minimum_elbow_angle: float = 90.0

    _active_since: datetime | None = None
    _latched: bool = False

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        wrist = frame.pose.get(self.wrist_name)
        elbow = frame.pose.get(self.elbow_name)
        shoulder = frame.pose.get(self.shoulder_name)
        if (
            wrist is None
            or elbow is None
            or shoulder is None
            or not _visible(wrist, elbow, shoulder)
            or _hand(frame, self.handedness) is None
            or shoulder.y - wrist.y < self.minimum_vertical_gap
            or _angle(wrist, elbow, shoulder) < self.minimum_elbow_angle
        ):
            self.reset()
            return None

        if self._latched:
            return None
        if self._active_since is None:
            self._active_since = frame.captured_at
            return None
        held_seconds = (frame.captured_at - self._active_since).total_seconds()
        if held_seconds < self.hold_seconds:
            return None

        self._latched = True
        return GestureDetection(self.motion_code, self._confidence(wrist, shoulder))

    def reset(self) -> None:
        self._active_since = None
        self._latched = False

    def _confidence(self, wrist: Landmark, shoulder: Landmark) -> float:
        gap = shoulder.y - wrist.y
        return min(1.0, max(0.0, 0.5 + gap))


class RightHandRaisedRule(_HandRaisedRule):
    """Emit once after the right hand is held above the shoulder."""

    def __init__(
        self,
        *,
        hold_seconds: float = 0.45,
        minimum_vertical_gap: float = 0.05,
        minimum_elbow_angle: float = 90.0,
    ) -> None:
        super().__init__(
            "Right",
            RIGHT_WRIST,
            RIGHT_ELBOW,
            RIGHT_SHOULDER,
            "POSE_RIGHT_HAND_UP",
            hold_seconds,
            minimum_vertical_gap,
            minimum_elbow_angle,
        )


class LeftHandRaisedRule(_HandRaisedRule):
    """Emit once after the left hand is held above the shoulder."""

    def __init__(
        self,
        *,
        hold_seconds: float = 0.45,
        minimum_vertical_gap: float = 0.05,
        minimum_elbow_angle: float = 90.0,
    ) -> None:
        super().__init__(
            "Left",
            "LEFT_WRIST",
            "LEFT_ELBOW",
            "LEFT_SHOULDER",
            "POSE_LEFT_HAND_UP",
            hold_seconds,
            minimum_vertical_gap,
            minimum_elbow_angle,
        )


@dataclass(slots=True)
class _SwipeRule:
    """Shared horizontal wrist movement rule for either hand."""

    handedness: str
    wrist_name: str
    shoulder_name: str
    direction: float
    motion_code: str
    movement_threshold: float = 0.12
    reset_margin: float = 0.05

    _start_x: float | None = None
    _latched: bool = False

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        wrist = frame.pose.get(self.wrist_name)
        shoulder = frame.pose.get(self.shoulder_name)
        if wrist is None or shoulder is None or _hand(frame, self.handedness) is None:
            return None

        if self._start_x is None:
            self._start_x = wrist.x
            return None

        movement = self.direction * (wrist.x - self._start_x)
        if not self._latched and movement >= self.movement_threshold:
            self._latched = True
            return GestureDetection(
                self.motion_code,
                min(1.0, max(0.0, movement / (self.movement_threshold * 2))),
            )

        if self._latched and self.direction * (wrist.x - self._start_x) <= self.reset_margin:
            self.reset()
        return None

    def reset(self) -> None:
        self._start_x = None
        self._latched = False


class SwipeRightRule(_SwipeRule):
    """Detect one rightward right-wrist movement, then wait for reset."""

    def __init__(self, *, movement_threshold: float = 0.12, reset_margin: float = 0.05) -> None:
        super().__init__(
            "Right", RIGHT_WRIST, RIGHT_SHOULDER, 1.0, "MOTION_SWIPE_RIGHT", movement_threshold, reset_margin
        )


class SwipeLeftRule(_SwipeRule):
    """Detect one leftward left-wrist movement, then wait for reset."""

    def __init__(self, *, movement_threshold: float = 0.12, reset_margin: float = 0.05) -> None:
        super().__init__(
            "Left", "LEFT_WRIST", "LEFT_SHOULDER", -1.0, "MOTION_SWIPE_LEFT", movement_threshold, reset_margin
        )


@dataclass(slots=True)
class FingerSnapRule:
    """Detect a right-hand snap-like transition from curled to extended fingers.

    The camera cannot reliably hear a snap. This visual rule uses the
    supplied gesture description: the index finger becomes extended while the
    thumb is partially extended and the other fingers remain curled.
    """

    motion_code: str = "MOTION_FINGER_SNAP"
    extended_index_angle: float = 150.0
    extended_thumb_angle: float = 105.0
    curled_finger_angle: float = 150.0
    thumb_middle_contact_ratio: float = 1.35

    _armed: bool = False
    _latched: bool = False

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        hand = _hand(frame, "Right")
        if hand is None or len(hand.landmarks) < 21:
            return None

        ready = self._is_ready(hand)
        post_snap = self._is_post_snap(hand)

        if self._latched:
            if not post_snap:
                self._latched = False
                self._armed = ready
            return None

        if ready:
            self._armed = True
            return None

        if self._armed and post_snap:
            self._latched = True
            self._armed = False
            return GestureDetection(self.motion_code, self._confidence(hand))

        return None

    def reset(self) -> None:
        self._armed = False
        self._latched = False

    def _is_ready(self, hand: HandObservation) -> bool:
        return (
            not self._index_extended(hand)
            and self._other_fingers_curled(hand)
            and self._thumb_middle_distance(hand) <= self.thumb_middle_contact_ratio
        )

    def _is_post_snap(self, hand: HandObservation) -> bool:
        return (
            self._index_extended(hand)
            and self._thumb_extended(hand)
            and self._other_fingers_curled(hand)
        )

    def _index_extended(self, hand: HandObservation) -> bool:
        return _joint_angle(hand, 5, 6, 8) >= self.extended_index_angle

    def _thumb_extended(self, hand: HandObservation) -> bool:
        return _joint_angle(hand, 2, 3, 4) >= self.extended_thumb_angle

    def _other_fingers_curled(self, hand: HandObservation) -> bool:
        return _other_fingers_curled(hand, self.curled_finger_angle)

    def _thumb_middle_distance(self, hand: HandObservation) -> float:
        palm_size = max(landmark_distance(hand.point(0), hand.point(9)), 0.001)
        return landmark_distance(hand.point(4), hand.point(12)) / palm_size

    def _confidence(self, hand: HandObservation) -> float:
        index_margin = _joint_angle(hand, 5, 6, 8) / 180.0
        thumb_margin = _joint_angle(hand, 2, 3, 4) / 180.0
        return min(1.0, max(0.0, (index_margin + thumb_margin) / 2.0))


def _other_fingers_curled(hand: HandObservation, maximum_angle: float) -> bool:
    return all(
        _joint_angle(hand, mcp, pip, tip) <= maximum_angle
        for mcp, pip, tip in ((9, 10, 12), (13, 14, 16), (17, 18, 20))
    )


def _is_thumbs_up(hand: HandObservation) -> bool:
    return (
        _joint_angle(hand, 2, 3, 4) >= 105.0
        and _other_fingers_curled(hand, 155.0)
        and hand.point(4).y <= hand.point(0).y - 0.03
    )


def _is_thumbs_down(hand: HandObservation) -> bool:
    return (
        _joint_angle(hand, 2, 3, 4) >= 105.0
        and _other_fingers_curled(hand, 155.0)
        and hand.point(4).y >= hand.point(0).y + 0.03
    )


@dataclass(slots=True)
class _ThumbVerticalMotionRule:
    """Detect a vertical movement that starts in a right-hand thumb pose."""

    pose_name: str
    direction: float
    motion_code: str
    movement_threshold: float = 0.10

    _start_y: float | None = None
    _armed: bool = False
    _latched: bool = False

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        hand = _hand(frame, "Right")
        if hand is None or len(hand.landmarks) < 21:
            return None

        pose = (
            _is_thumbs_up(hand)
            if self.pose_name == "up"
            else _is_thumbs_down(hand)
        )
        if self._latched:
            if not pose:
                self.reset()
            return None

        if not pose:
            if self._armed:
                self.reset()
            return None

        if not self._armed:
            self._armed = True
            self._start_y = hand.point(0).y
            return None

        assert self._start_y is not None
        movement = self.direction * (self._start_y - hand.point(0).y)
        if movement < self.movement_threshold:
            return None

        self._latched = True
        confidence = min(
            1.0,
            max(0.0, movement / (self.movement_threshold * 2)),
        )
        return GestureDetection(self.motion_code, confidence)

    def reset(self) -> None:
        self._start_y = None
        self._armed = False
        self._latched = False


class ThumbsUpMoveUpRule(_ThumbVerticalMotionRule):
    """Detect a right-hand thumbs-up followed by upward movement."""

    def __init__(self, *, movement_threshold: float = 0.10) -> None:
        super().__init__("up", 1.0, "MOTION_THUMBS_UP_MOVE_UP", movement_threshold)


class ThumbsDownMoveDownRule(_ThumbVerticalMotionRule):
    """Detect a right-hand thumbs-down followed by downward movement."""

    def __init__(self, *, movement_threshold: float = 0.10) -> None:
        super().__init__("down", -1.0, "MOTION_THUMBS_DOWN_MOVE_DOWN", movement_threshold)


@dataclass(slots=True)
class ClapRule:
    """Detect both hands moving from apart to a close palm-to-palm position."""

    contact_ratio: float = 1.35
    release_ratio: float = 1.80

    _armed: bool = False
    _latched: bool = False
    _previous_ratio: float | None = None

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        left = _hand(frame, "Left")
        right = _hand(frame, "Right")
        if (
            left is None
            or right is None
            or len(left.landmarks) < 21
            or len(right.landmarks) < 21
        ):
            return None

        ratio = self._palm_distance_ratio(left, right)
        previous_ratio = self._previous_ratio
        self._previous_ratio = ratio

        if ratio >= self.release_ratio:
            self._armed = True
            self._latched = False
            return None

        if (
            self._armed
            and not self._latched
            and ratio <= self.contact_ratio
            and previous_ratio is not None
            and ratio < previous_ratio
        ):
            self._latched = True
            confidence = (self.release_ratio - ratio) / (
                self.release_ratio - self.contact_ratio
            )
            return GestureDetection(
                "MOTION_CLAP",
                min(1.0, max(0.0, confidence)),
            )
        return None

    def reset(self) -> None:
        self._armed = False
        self._latched = False
        self._previous_ratio = None

    def _palm_distance_ratio(
        self, left: HandObservation, right: HandObservation
    ) -> float:
        distance = landmark_distance(left.point(0), right.point(0))
        left_size = landmark_distance(left.point(0), left.point(9))
        right_size = landmark_distance(right.point(0), right.point(9))
        palm_size = max((left_size + right_size) / 2.0, 0.001)
        return distance / palm_size


def _is_open_palm(hand: HandObservation) -> bool:
    return (
        _joint_angle(hand, 2, 3, 4) >= 105.0
        and all(
            _joint_angle(hand, mcp, pip, tip) >= 140.0
            for mcp, pip, tip in (
                (5, 6, 8),
                (9, 10, 12),
                (13, 14, 16),
                (17, 18, 20),
            )
        )
    )


def _is_fist(hand: HandObservation) -> bool:
    return _other_fingers_curled(hand, 155.0)


@dataclass(slots=True)
class OpenToFistDownRule:
    """Detect a right hand changing from an open palm to a fist while lowering."""

    movement_threshold: float = 0.10

    _start_y: float | None = None
    _armed: bool = False
    _latched: bool = False

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        hand = _hand(frame, "Right")
        if hand is None or len(hand.landmarks) < 21:
            return None

        if self._latched:
            if not _is_fist(hand):
                self.reset()
            return None

        if _is_open_palm(hand):
            self._armed = True
            self._start_y = hand.point(0).y
            return None

        if not self._armed or not _is_fist(hand):
            return None

        assert self._start_y is not None
        movement = hand.point(0).y - self._start_y
        if movement < self.movement_threshold:
            return None

        self._latched = True
        confidence = min(
            1.0,
            max(0.0, movement / (self.movement_threshold * 2)),
        )
        return GestureDetection("MOTION_OPEN_TO_FIST_DOWN", confidence)

    def reset(self) -> None:
        self._start_y = None
        self._armed = False
        self._latched = False


def _joint_angle(
    hand: HandObservation, first: int, middle: int, last: int
) -> float:
    return _angle(hand.point(first), hand.point(middle), hand.point(last))


def landmark_distance(first: Landmark, last: Landmark) -> float:
    """Return normalized 2D distance for future rule implementations."""

    return hypot(first.x - last.x, first.y - last.y)
