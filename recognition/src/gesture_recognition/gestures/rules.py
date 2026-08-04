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


def landmark_distance(first: Landmark, last: Landmark) -> float:
    """Return normalized 2D distance for future rule implementations."""

    return hypot(first.x - last.x, first.y - last.y)
