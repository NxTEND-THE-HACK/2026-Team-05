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
class RightHandRaisedRule:
    """Emit once after the right hand is held above the shoulder."""

    hold_seconds: float = 0.6
    minimum_vertical_gap: float = 0.08
    motion_code: str = "POSE_RIGHT_HAND_UP"

    _active_since: datetime | None = None
    _latched: bool = False

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        wrist = frame.pose.get(RIGHT_WRIST)
        elbow = frame.pose.get(RIGHT_ELBOW)
        shoulder = frame.pose.get(RIGHT_SHOULDER)
        if (
            wrist is None
            or elbow is None
            or shoulder is None
            or not _visible(wrist, elbow, shoulder)
            or _hand(frame, "Right") is None
            or shoulder.y - wrist.y < self.minimum_vertical_gap
            or _angle(wrist, elbow, shoulder) < 100.0
        ):
            self._active_since = None
            self._latched = False
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


@dataclass(slots=True)
class SwipeRightRule:
    """Detect one rightward wrist movement, then wait for reset."""

    movement_threshold: float = 0.18
    reset_margin: float = 0.05
    motion_code: str = "MOTION_SWIPE_RIGHT"

    _start_x: float | None = None
    _latched: bool = False

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        wrist = frame.pose.get(RIGHT_WRIST)
        shoulder = frame.pose.get(RIGHT_SHOULDER)
        if wrist is None or shoulder is None or _hand(frame, "Right") is None:
            return None

        if self._start_x is None:
            self._start_x = wrist.x
            return None

        movement = wrist.x - self._start_x
        if not self._latched and movement >= self.movement_threshold:
            self._latched = True
            return GestureDetection(
                self.motion_code,
                min(1.0, max(0.0, movement / (self.movement_threshold * 2))),
            )

        if self._latched and wrist.x <= self._start_x + self.reset_margin:
            self.reset()
        return None

    def reset(self) -> None:
        self._start_x = None
        self._latched = False


@dataclass(slots=True)
class FingerSnapRule:
    """Detect a right-hand snap-like transition from curled to extended fingers.

    The camera cannot reliably hear a snap. This visual rule uses the
    supplied gesture description: the index finger becomes extended while the
    thumb is partially extended and the other fingers remain curled.
    """

    motion_code: str = "MOTION_FINGER_SNAP"
    extended_index_angle: float = 155.0
    extended_thumb_angle: float = 115.0
    curled_finger_angle: float = 145.0
    thumb_middle_contact_ratio: float = 1.2

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
        return all(
            _joint_angle(hand, mcp, pip, tip) <= self.curled_finger_angle
            for mcp, pip, tip in ((9, 10, 12), (13, 14, 16), (17, 18, 20))
        )

    def _thumb_middle_distance(self, hand: HandObservation) -> float:
        palm_size = max(landmark_distance(hand.point(0), hand.point(9)), 0.001)
        return landmark_distance(hand.point(4), hand.point(12)) / palm_size

    def _confidence(self, hand: HandObservation) -> float:
        index_margin = _joint_angle(hand, 5, 6, 8) / 180.0
        thumb_margin = _joint_angle(hand, 2, 3, 4) / 180.0
        return min(1.0, max(0.0, (index_margin + thumb_margin) / 2.0))


def _joint_angle(
    hand: HandObservation, first: int, middle: int, last: int
) -> float:
    return _angle(hand.point(first), hand.point(middle), hand.point(last))


def landmark_distance(first: Landmark, last: Landmark) -> float:
    """Return normalized 2D distance for future rule implementations."""

    return hypot(first.x - last.x, first.y - last.y)
