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
LEFT_WRIST = "LEFT_WRIST"
LEFT_ELBOW = "LEFT_ELBOW"
LEFT_SHOULDER = "LEFT_SHOULDER"


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
    minimum_vertical_gap: float = 0.23
    minimum_elbow_angle: float = 90.0
    cooldown_seconds: float = 0.75

    _active_since: datetime | None = None
    _latched: bool = False
    _last_detection_at: datetime | None = None

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        wrist = frame.pose.get(self.wrist_name)
        elbow = frame.pose.get(self.elbow_name)
        shoulder = frame.pose.get(self.shoulder_name)
        if (
            wrist is None
            or elbow is None
            or shoulder is None
            or not _visible(wrist, elbow, shoulder)
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
        if (
            self._last_detection_at is not None
            and (frame.captured_at - self._last_detection_at).total_seconds()
            < self.cooldown_seconds
        ):
            return None

        self._latched = True
        self._last_detection_at = frame.captured_at
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
        minimum_vertical_gap: float = 0.23,
        minimum_elbow_angle: float = 90.0,
        cooldown_seconds: float = 0.75,
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
            cooldown_seconds,
        )


class LeftHandRaisedRule(_HandRaisedRule):
    """Emit once after the left hand is held above the shoulder."""

    def __init__(
        self,
        *,
        hold_seconds: float = 0.45,
        minimum_vertical_gap: float = 0.23,
        minimum_elbow_angle: float = 90.0,
        cooldown_seconds: float = 0.75,
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
            cooldown_seconds,
        )


@dataclass(slots=True)
class _SwipeRule:
    """Shared Pose-only horizontal wrist movement rule for either hand."""

    wrist_name: str
    shoulder_name: str
    direction: float
    motion_code: str
    movement_threshold: float = 0.18
    reset_margin: float = 0.05
    start_max_center_offset: float = 0.65
    start_min_vertical_offset: float = 0.25
    start_max_vertical_offset: float = 1.70
    maximum_event_elapsed_seconds: float | None = 1.50
    maximum_event_wrist_y: float | None = None
    maximum_vertical_displacement: float | None = None

    _start_x: float | None = None
    _start_y: float | None = None
    _latched: bool = False
    _peak_movement: float | None = None
    _started_at: datetime | None = None

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        wrist = frame.pose.get(self.wrist_name)
        shoulder = frame.pose.get(self.shoulder_name)
        if wrist is None or shoulder is None:
            return None

        if self._start_x is None:
            if not self._is_start_region(frame, wrist):
                return None
            self._start_x = wrist.x
            self._start_y = wrist.y
            self._started_at = frame.captured_at
            return None

        movement = self.direction * (wrist.x - self._start_x)
        if self._latched:
            self._peak_movement = max(self._peak_movement or movement, movement)
            if movement <= self._peak_movement - self.reset_margin:
                # The return frame is the next gesture's new chest baseline.
                self._start_x = wrist.x if self._is_start_region(frame, wrist) else None
                self._start_y = wrist.y if self._start_x is not None else None
                self._started_at = (
                    frame.captured_at if self._start_x is not None else None
                )
                self._latched = False
                self._peak_movement = None
            return None

        # Re-baseline while the hand is moving back toward the chest. This
        # allows repeated swipes even when the resting position drifts.
        if movement < 0:
            self._start_x = wrist.x
            self._start_y = wrist.y
            self._started_at = frame.captured_at
            movement = 0.0

        if movement >= self.movement_threshold:
            if (
                self.maximum_event_elapsed_seconds is not None
                and self._started_at is not None
                and (
                    frame.captured_at - self._started_at
                ).total_seconds()
                > self.maximum_event_elapsed_seconds
            ):
                return None
            if (
                self.maximum_vertical_displacement is not None
                and self._start_y is not None
                and abs(wrist.y - self._start_y)
                > self.maximum_vertical_displacement
            ):
                self._latched = True
                self._peak_movement = movement
                return None
            if (
                self.maximum_event_wrist_y is not None
                and wrist.y > self.maximum_event_wrist_y
            ):
                # A large horizontal displacement at a low image-space Y is
                # commonly the vertical thumb motion being mistaken for a
                # swipe. Consume that path until the wrist returns to the
                # baseline instead of allowing a later frame to fire it.
                self._latched = True
                self._peak_movement = movement
                return None
            self._latched = True
            self._peak_movement = movement
            return GestureDetection(
                self.motion_code,
                min(1.0, max(0.0, movement / (self.movement_threshold * 2))),
            )
        return None

    def _is_start_region(self, frame: LandmarkFrame, wrist: Landmark) -> bool:
        left_shoulder = frame.pose.get(LEFT_SHOULDER)
        right_shoulder = frame.pose.get(RIGHT_SHOULDER)
        if left_shoulder is None or right_shoulder is None:
            # Keep compatibility with partial Pose frames; the full camera
            # detector normally provides both shoulders.
            return True
        shoulder_width = abs(left_shoulder.x - right_shoulder.x)
        if shoulder_width < 0.05:
            return False
        shoulder_center_x = (left_shoulder.x + right_shoulder.x) / 2.0
        shoulder_center_y = (left_shoulder.y + right_shoulder.y) / 2.0
        center_offset = abs(wrist.x - shoulder_center_x) / shoulder_width
        vertical_offset = (wrist.y - shoulder_center_y) / shoulder_width
        return (
            center_offset <= self.start_max_center_offset
            and self.start_min_vertical_offset <= vertical_offset <= self.start_max_vertical_offset
        )

    def reset(self) -> None:
        self._start_x = None
        self._start_y = None
        self._latched = False
        self._peak_movement = None
        self._started_at = None

    @property
    def is_active(self) -> bool:
        """Return whether this swipe sequence has fired and is latched."""

        return self._latched


class SwipeRightRule(_SwipeRule):
    """Mirror the left-swipe rule for the person's right hand.

    The subject's right is the image's left when the camera is facing them,
    so the normalized image X coordinate decreases.
    """

    def __init__(
        self,
        *,
        movement_threshold: float = 0.22,
        reset_margin: float = 0.05,
    ) -> None:
        super().__init__(
            RIGHT_WRIST,
            RIGHT_SHOULDER,
            -1.0,
            "MOTION_SWIPE_RIGHT",
            movement_threshold,
            reset_margin,
        )


class SwipeLeftRule(_SwipeRule):
    """Detect the left hand moving from the chest toward the person's left.

    The camera stream is front-facing, so this movement increases the
    normalized image X coordinate even though it is leftward from the
    subject's perspective.
    """

    def __init__(self, *, movement_threshold: float = 0.22, reset_margin: float = 0.05) -> None:
        super().__init__(
            LEFT_WRIST, LEFT_SHOULDER, 1.0, "MOTION_SWIPE_LEFT", movement_threshold, reset_margin
        )


@dataclass(slots=True)
class _PoseVerticalMotionRule:
    """Shared Pose vertical wrist movement rule with an optional pose gate.

    Keeping the start region near the torso prevents a hand already held low
    from becoming a new baseline and lets the rule re-arm after each return.
    Subclasses can validate a hand pose shortly before the movement without
    requiring HandLandmarker output for every movement frame.
    """

    wrist_name: str
    direction: float
    motion_code: str
    movement_threshold: float = 0.10
    reset_margin: float = 0.05
    start_max_center_offset: float = 0.75
    start_min_vertical_offset: float = -0.40
    start_max_vertical_offset: float = 0.80
    pose_gate_seconds: float = 1.50
    maximum_hand_pose_distance: float = 0.20
    cooldown_seconds: float = 0.75
    maximum_event_vertical_offset: float | None = None
    maximum_event_elapsed_seconds: float | None = None
    minimum_pose_gate_age_without_hand: float | None = None
    maximum_stale_pose_gate_age: float | None = None
    minimum_stale_pose_gate_elapsed: float | None = None
    maximum_stale_pose_gate_vertical_offset: float | None = None

    _start_y: float | None = None
    _latched: bool = False
    _peak_movement: float | None = None
    _pose_seen_at: datetime | None = None
    _last_detection_at: datetime | None = None
    _started_at: datetime | None = None
    _contradictory_pose_seen: bool = False

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        wrist = frame.pose.get(self.wrist_name)
        if wrist is None or not _visible(wrist):
            self.reset()
            return None

        pose_ready = self._pose_is_ready(frame)
        if pose_ready:
            self._pose_seen_at = frame.captured_at
        elif self._pose_is_conflicting(frame):
            # A contradictory hand pose invalidates the short-lived gate.
            # This prevents an upward-thumb sequence from being reused as a
            # later thumb-down movement after the HandLandmarker flickers.
            self._pose_seen_at = None
            self._contradictory_pose_seen = True

        if self._start_y is None:
            if self._is_start_region(frame, wrist):
                self._start_y = wrist.y
                self._started_at = frame.captured_at
            return None

        movement = self.direction * (wrist.y - self._start_y)
        if self._latched:
            self._peak_movement = max(self._peak_movement or movement, movement)
            if movement <= self._peak_movement - self.reset_margin:
                self._start_y = (
                    wrist.y
                    if self._is_start_region(frame, wrist)
                    else None
                )
                self._started_at = (
                    frame.captured_at if self._start_y is not None else None
                )
                self._latched = False
                self._peak_movement = None
                if not pose_ready:
                    self._pose_seen_at = None
            return None

        # Re-baseline while the wrist is returning toward the start position.
        if movement < 0:
            self._start_y = wrist.y if self._is_start_region(frame, wrist) else None
            self._started_at = (
                frame.captured_at if self._start_y is not None else None
            )
            movement = 0.0

        if movement >= self.movement_threshold:
            event_vertical_offset = _pose_vertical_offset_from_shoulders(
                frame,
                wrist,
            )
            if (
                self.maximum_event_vertical_offset is not None
                and event_vertical_offset is not None
                and event_vertical_offset > self.maximum_event_vertical_offset
            ):
                self._reject_motion(movement)
                return None
            if self._contradictory_pose_seen:
                self._reject_motion(movement)
                return None
            if (
                not pose_ready
                and self.minimum_pose_gate_age_without_hand is not None
                and self._pose_seen_at is not None
                and (
                    frame.captured_at - self._pose_seen_at
                ).total_seconds()
                < self.minimum_pose_gate_age_without_hand
            ):
                self._reject_motion(movement)
                return None
            pose_gate_age = (
                None
                if self._pose_seen_at is None
                else (
                    frame.captured_at - self._pose_seen_at
                ).total_seconds()
            )
            event_elapsed = (
                None
                if self._started_at is None
                else (
                    frame.captured_at - self._started_at
                ).total_seconds()
            )
            if (
                not pose_ready
                and pose_gate_age is not None
                and self.maximum_stale_pose_gate_age is not None
                and pose_gate_age > self.maximum_stale_pose_gate_age
                and event_elapsed is not None
                and self.minimum_stale_pose_gate_elapsed is not None
                and event_elapsed > self.minimum_stale_pose_gate_elapsed
                and event_vertical_offset is not None
                and self.maximum_stale_pose_gate_vertical_offset is not None
                and event_vertical_offset
                < self.maximum_stale_pose_gate_vertical_offset
            ):
                self._reject_motion(movement)
                return None
            if (
                self.maximum_event_elapsed_seconds is not None
                and self._started_at is not None
                and (
                    frame.captured_at - self._started_at
                ).total_seconds()
                > self.maximum_event_elapsed_seconds
            ):
                self._reject_motion(movement)
                return None
            if not self._pose_gate_is_recent(frame.captured_at):
                self._reject_motion(movement)
                return None
            if (
                self._last_detection_at is not None
                and (frame.captured_at - self._last_detection_at).total_seconds()
                < self.cooldown_seconds
            ):
                self._latched = True
                self._peak_movement = movement
                self._pose_seen_at = None
                return None
            self._latched = True
            self._peak_movement = movement
            self._pose_seen_at = None
            self._last_detection_at = frame.captured_at
            return GestureDetection(
                self.motion_code,
                min(1.0, max(0.0, movement / (self.movement_threshold * 2))),
            )
        return None

    def _reject_motion(self, movement: float) -> None:
        """Consume a rejected movement until the wrist returns toward baseline."""

        self._latched = True
        self._peak_movement = movement
        self._pose_seen_at = None

    def _pose_is_ready(self, frame: LandmarkFrame) -> bool:
        """Return whether the optional hand-pose gate is satisfied."""

        return True

    def _pose_is_conflicting(self, frame: LandmarkFrame) -> bool:
        """Return whether a visible hand pose contradicts the gate."""

        return False

    def _pose_gate_is_recent(self, captured_at: datetime) -> bool:
        if self._pose_seen_at is None:
            return False
        age = (captured_at - self._pose_seen_at).total_seconds()
        return 0.0 <= age <= self.pose_gate_seconds

    def _is_start_region(self, frame: LandmarkFrame, wrist: Landmark) -> bool:
        left_shoulder = frame.pose.get(LEFT_SHOULDER)
        right_shoulder = frame.pose.get(RIGHT_SHOULDER)
        if left_shoulder is None or right_shoulder is None:
            # Preserve compatibility with partial Pose frames.
            return True
        shoulder_width = abs(left_shoulder.x - right_shoulder.x)
        if shoulder_width < 0.05:
            return False
        shoulder_center_x = (left_shoulder.x + right_shoulder.x) / 2.0
        shoulder_center_y = (left_shoulder.y + right_shoulder.y) / 2.0
        center_offset = abs(wrist.x - shoulder_center_x) / shoulder_width
        vertical_offset = (wrist.y - shoulder_center_y) / shoulder_width
        return (
            center_offset <= self.start_max_center_offset
            and self.start_min_vertical_offset
            <= vertical_offset
            <= self.start_max_vertical_offset
        )

    def reset(self) -> None:
        self._start_y = None
        self._latched = False
        self._peak_movement = None
        self._pose_seen_at = None
        self._started_at = None
        self._contradictory_pose_seen = False


def _signed_angle_delta(current: float, baseline: float) -> float:
    """Return the shortest signed angle from baseline to current."""

    return (current - baseline + 180.0) % 360.0 - 180.0


def _palm_axis_angle(
    hand: HandObservation,
    *,
    axis_landmark: int = 9,
) -> float | None:
    """Return the image-plane angle of a wrist-to-palm landmark axis."""

    if len(hand.landmarks) <= axis_landmark:
        return None
    wrist = hand.point(0)
    palm_landmark = hand.point(axis_landmark)
    if landmark_distance(wrist, palm_landmark) < 0.02:
        return None
    return degrees(
        atan2(palm_landmark.y - wrist.y, palm_landmark.x - wrist.x)
    )


def _palm_rotation_angle(
    hand: HandObservation,
    frame: LandmarkFrame,
    pose_name: str,
    elbow_name: str,
    *,
    axis_landmark: int = 9,
) -> float | None:
    """Return palm rotation relative to the matching forearm direction.

    The raw palm axis also changes when the whole arm is raised or lowered.
    Referencing it to the forearm removes most of that camera-plane motion.
    Partial unit-test frames do not always contain an elbow, so they retain
    the raw-axis fallback.
    """

    palm_angle = _palm_axis_angle(hand, axis_landmark=axis_landmark)
    if palm_angle is None:
        return None
    wrist = frame.pose.get(pose_name)
    elbow = frame.pose.get(elbow_name)
    if wrist is None or elbow is None or landmark_distance(elbow, wrist) < 0.02:
        return palm_angle
    forearm_angle = degrees(
        atan2(wrist.y - elbow.y, wrist.x - elbow.x)
    )
    return _signed_angle_delta(palm_angle, forearm_angle)


def _hand_near_pose_wrist(
    frame: LandmarkFrame,
    pose_name: str,
    maximum_distance: float,
) -> HandObservation | None:
    """Match a hand to its anatomical Pose wrist instead of trusting labels."""

    pose_wrist = frame.pose.get(pose_name)
    candidates = [hand for hand in frame.hands if len(hand.landmarks) >= 18]
    if pose_wrist is None or not candidates:
        return None
    hand = min(
        candidates,
        key=lambda item: landmark_distance(item.point(0), pose_wrist),
    )
    if landmark_distance(hand.point(0), pose_wrist) > maximum_distance:
        return None
    return hand


def _hand_for_pose(
    frame: LandmarkFrame,
    pose_name: str,
    fallback_handedness: str,
    maximum_distance: float = 0.20,
) -> HandObservation | None:
    """Match a hand to Pose when available, with a partial-frame fallback."""

    if frame.pose.get(pose_name) is not None:
        hand = _hand_near_pose_wrist(frame, pose_name, maximum_distance)
        if hand is not None:
            return hand
    return _hand(frame, fallback_handedness)


def _pose_vertical_offset_from_shoulders(
    frame: LandmarkFrame,
    wrist: Landmark,
) -> float | None:
    """Return wrist height below the shoulder center in shoulder widths."""

    left_shoulder = frame.pose.get(LEFT_SHOULDER)
    right_shoulder = frame.pose.get(RIGHT_SHOULDER)
    if left_shoulder is None or right_shoulder is None:
        return None
    shoulder_width = abs(left_shoulder.x - right_shoulder.x)
    if shoulder_width < 0.05:
        return None
    shoulder_center_y = (left_shoulder.y + right_shoulder.y) / 2.0
    return (wrist.y - shoulder_center_y) / shoulder_width


@dataclass(slots=True)
class _HandRotateRule:
    """Detect one in-plane palm rotation and re-arm near the baseline angle."""

    pose_name: str
    elbow_name: str
    direction: float
    motion_code: str
    rotation_threshold: float = 20.0
    rearm_threshold: float = 5.0
    maximum_hand_pose_distance: float = 0.20
    maximum_missing_seconds: float = 0.40
    cooldown_seconds: float = 1.25
    secondary_rotation_threshold: float = 20.0
    minimum_event_elapsed_seconds: float = 0.22
    maximum_event_elapsed_seconds: float | None = 1.16
    minimum_path_length: float = 0.0
    maximum_path_length: float | None = None
    minimum_middle_axis_delta: float | None = None
    maximum_middle_axis_delta: float | None = None
    minimum_index_angle_range: float | None = None
    maximum_index_angle_range: float | None = None
    minimum_vertical_displacement: float | None = None
    maximum_vertical_displacement: float | None = None
    minimum_ring_angle: float | None = None
    maximum_ring_angle: float | None = None
    minimum_raw_secondary_axis_magnitude: float | None = None
    confirmation_minimum_delta: float | None = None

    _baseline_angle: float | None = None
    _secondary_baseline_angle: float | None = None
    _baseline_raw_middle_angle: float | None = None
    _baseline_raw_secondary_angle: float | None = None
    _latched: bool = False
    _last_hand_at: datetime | None = None
    _last_detection_at: datetime | None = None
    _started_at: datetime | None = None
    _last_pose_wrist: Landmark | None = None
    _baseline_pose_wrist: Landmark | None = None
    _path_length: float = 0.0
    _index_angle_min: float | None = None
    _index_angle_max: float | None = None
    _pending_detection: GestureDetection | None = None
    _pending_handedness: str | None = None

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        hand = _hand_near_pose_wrist(
            frame,
            self.pose_name,
            self.maximum_hand_pose_distance,
        )
        if hand is None:
            if self._pending_detection is not None:
                if (
                    self._last_hand_at is not None
                    and (
                        frame.captured_at - self._last_hand_at
                    ).total_seconds()
                    > self.maximum_missing_seconds
                ):
                    self.reset()
                    return None
                pending = self._pending_detection
                self._pending_detection = None
                self._pending_handedness = None
                self._latched = True
                self._last_detection_at = frame.captured_at
                return pending
            if (
                self._last_hand_at is not None
                and (frame.captured_at - self._last_hand_at).total_seconds()
                > self.maximum_missing_seconds
            ):
                self.reset()
            return None

        if (
            self._last_hand_at is not None
            and (frame.captured_at - self._last_hand_at).total_seconds()
            > self.maximum_missing_seconds
        ):
            self.reset()

        angle = _palm_rotation_angle(
            hand,
            frame,
            self.pose_name,
            self.elbow_name,
        )
        secondary_angle = _palm_rotation_angle(
            hand,
            frame,
            self.pose_name,
            self.elbow_name,
            axis_landmark=5,
        )
        if angle is None or secondary_angle is None:
            return None
        self._last_hand_at = frame.captured_at

        if self._baseline_angle is None:
            self._baseline_angle = angle
            self._secondary_baseline_angle = secondary_angle
            self._baseline_raw_middle_angle = _palm_axis_angle(hand)
            self._baseline_raw_secondary_angle = _palm_axis_angle(
                hand,
                axis_landmark=5,
            )
            self._started_at = frame.captured_at
            pose_wrist = frame.pose.get(self.pose_name)
            self._last_pose_wrist = pose_wrist
            self._baseline_pose_wrist = pose_wrist
            index_angle = _joint_angle(hand, 5, 6, 8)
            self._index_angle_min = index_angle
            self._index_angle_max = index_angle
            return None

        pose_wrist = frame.pose.get(self.pose_name)
        if pose_wrist is not None and self._last_pose_wrist is not None:
            self._path_length += landmark_distance(pose_wrist, self._last_pose_wrist)
        if pose_wrist is not None:
            self._last_pose_wrist = pose_wrist
        index_angle = _joint_angle(hand, 5, 6, 8)
        if self._index_angle_min is None:
            self._index_angle_min = index_angle
            self._index_angle_max = index_angle
        else:
            assert self._index_angle_max is not None
            self._index_angle_min = min(self._index_angle_min, index_angle)
            self._index_angle_max = max(self._index_angle_max, index_angle)

        delta = _signed_angle_delta(angle, self._baseline_angle)
        assert self._secondary_baseline_angle is not None
        secondary_delta = _signed_angle_delta(
            secondary_angle,
            self._secondary_baseline_angle,
        )
        directed_delta = self.direction * delta
        directed_secondary_delta = self.direction * secondary_delta
        if self._pending_detection is not None:
            handedness_switched_while_rotating = (
                self._pending_handedness is not None
                and hand.handedness != self._pending_handedness
                and directed_delta >= self.rotation_threshold
                and directed_secondary_delta >= self.secondary_rotation_threshold
            )
            if (
                handedness_switched_while_rotating
                or (
                self.confirmation_minimum_delta is not None
                and (
                    directed_delta < self.confirmation_minimum_delta
                    or directed_secondary_delta < self.confirmation_minimum_delta
                )
                )
            ):
                self._pending_detection = None
                self._pending_handedness = None
                self._latched = True
                return None
            pending = self._pending_detection
            self._pending_detection = None
            self._pending_handedness = None
            self._latched = True
            self._last_detection_at = frame.captured_at
            return pending
        if self._latched:
            if abs(delta) <= self.rearm_threshold:
                self._baseline_angle = angle
                self._secondary_baseline_angle = secondary_angle
                self._baseline_raw_middle_angle = _palm_axis_angle(hand)
                self._baseline_raw_secondary_angle = _palm_axis_angle(
                    hand,
                    axis_landmark=5,
                )
                self._started_at = frame.captured_at
                self._last_pose_wrist = pose_wrist
                self._baseline_pose_wrist = pose_wrist
                self._path_length = 0.0
                self._index_angle_min = index_angle
                self._index_angle_max = index_angle
                self._latched = False
            return None

        if (
            directed_delta < self.rotation_threshold
            or directed_secondary_delta < self.secondary_rotation_threshold
        ):
            return None

        elapsed_seconds = (
            None
            if self._started_at is None
            else (frame.captured_at - self._started_at).total_seconds()
        )
        if (
            elapsed_seconds is not None
            and elapsed_seconds < self.minimum_event_elapsed_seconds
        ):
            return None
        if (
            elapsed_seconds is not None
            and self.maximum_event_elapsed_seconds is not None
            and elapsed_seconds > self.maximum_event_elapsed_seconds
        ):
            self._latched = True
            return None

        index_angle_range = None
        if (
            self._index_angle_min is not None
            and self._index_angle_max is not None
        ):
            index_angle_range = self._index_angle_max - self._index_angle_min
        raw_middle_delta = None
        raw_secondary_delta = None
        raw_middle_angle = _palm_axis_angle(hand)
        if (
            raw_middle_angle is not None
            and self._baseline_raw_middle_angle is not None
        ):
            raw_middle_delta = self.direction * _signed_angle_delta(
                raw_middle_angle,
                self._baseline_raw_middle_angle,
            )
        raw_secondary_angle = _palm_axis_angle(hand, axis_landmark=5)
        if (
            raw_secondary_angle is not None
            and self._baseline_raw_secondary_angle is not None
        ):
            raw_secondary_delta = self.direction * _signed_angle_delta(
                raw_secondary_angle,
                self._baseline_raw_secondary_angle,
            )

        vertical_displacement = None
        current_pose_wrist = frame.pose.get(self.pose_name)
        left_shoulder = frame.pose.get(LEFT_SHOULDER)
        right_shoulder = frame.pose.get(RIGHT_SHOULDER)
        if (
            current_pose_wrist is not None
            and self._baseline_pose_wrist is not None
            and left_shoulder is not None
            and right_shoulder is not None
        ):
            shoulder_width = abs(left_shoulder.x - right_shoulder.x)
            if shoulder_width >= 0.05:
                vertical_displacement = (
                    current_pose_wrist.y - self._baseline_pose_wrist.y
                ) / shoulder_width
        ring_angle = _joint_angle(hand, 13, 14, 16)
        if (
            self._path_length < self.minimum_path_length
            or (
                self.maximum_path_length is not None
                and self._path_length > self.maximum_path_length
            )
            or (
                self.minimum_middle_axis_delta is not None
                and (
                    raw_middle_delta is None
                    or raw_middle_delta < self.minimum_middle_axis_delta
                )
            )
            or (
                self.maximum_middle_axis_delta is not None
                and (
                    raw_middle_delta is None
                    or raw_middle_delta > self.maximum_middle_axis_delta
                )
            )
            or (
                self.minimum_index_angle_range is not None
                and (
                    index_angle_range is None
                    or index_angle_range < self.minimum_index_angle_range
                )
            )
            or (
                self.maximum_index_angle_range is not None
                and (
                    index_angle_range is None
                    or index_angle_range > self.maximum_index_angle_range
                )
            )
            or (
                self.minimum_vertical_displacement is not None
                and (
                    vertical_displacement is None
                    or vertical_displacement < self.minimum_vertical_displacement
                )
            )
            or (
                self.maximum_vertical_displacement is not None
                and (
                    vertical_displacement is None
                    or vertical_displacement > self.maximum_vertical_displacement
                )
            )
            or (
                self.minimum_ring_angle is not None
                and ring_angle < self.minimum_ring_angle
            )
            or (
                self.maximum_ring_angle is not None
                and ring_angle > self.maximum_ring_angle
            )
            or (
                self.minimum_raw_secondary_axis_magnitude is not None
                and (
                    raw_secondary_delta is None
                    or (
                        abs(raw_secondary_delta)
                        < self.minimum_raw_secondary_axis_magnitude
                        and len(frame.hands) > 1
                    )
                )
            )
        ):
            self._latched = True
            return None

        if (
            self._last_detection_at is not None
            and (frame.captured_at - self._last_detection_at).total_seconds()
            < self.cooldown_seconds
        ):
            self._latched = True
            return None

        detection = GestureDetection(
            self.motion_code,
            min(
                1.0,
                max(0.0, directed_delta / (self.rotation_threshold * 2)),
            ),
        )
        if self.confirmation_minimum_delta is not None:
            self._pending_detection = detection
            self._pending_handedness = hand.handedness
            return None
        self._latched = True
        self._last_detection_at = frame.captured_at
        return detection

    def reset(self) -> None:
        self._baseline_angle = None
        self._secondary_baseline_angle = None
        self._baseline_raw_middle_angle = None
        self._baseline_raw_secondary_angle = None
        self._latched = False
        self._last_hand_at = None
        self._started_at = None
        self._last_pose_wrist = None
        self._baseline_pose_wrist = None
        self._path_length = 0.0
        self._index_angle_min = None
        self._index_angle_max = None
        self._pending_detection = None
        self._pending_handedness = None


class HandRotateRightRule(_HandRotateRule):
    """Detect a clockwise/right palm rotation with the right hand."""

    def __init__(
        self,
        *,
        rotation_threshold: float = 20.0,
        rearm_threshold: float = 5.0,
        maximum_hand_pose_distance: float = 0.20,
        maximum_missing_seconds: float = 0.40,
        cooldown_seconds: float = 1.25,
        secondary_rotation_threshold: float = 20.0,
        minimum_event_elapsed_seconds: float = 0.22,
        maximum_event_elapsed_seconds: float | None = 1.16,
        minimum_path_length: float = 0.077,
        maximum_path_length: float | None = 0.306,
        minimum_middle_axis_delta: float | None = -4.9,
        maximum_middle_axis_delta: float | None = 169.14,
        minimum_vertical_displacement: float | None = -2.152,
        maximum_vertical_displacement: float | None = 0.289,
        minimum_ring_angle: float | None = 14.97,
        maximum_ring_angle: float | None = 176.6,
        minimum_raw_secondary_axis_magnitude: float | None = 20.0,
        confirmation_minimum_delta: float | None = 0.0,
    ) -> None:
        super().__init__(
            RIGHT_WRIST,
            RIGHT_ELBOW,
            1.0,
            "MOTION_HAND_ROTATE_RIGHT",
            rotation_threshold,
            rearm_threshold,
            maximum_hand_pose_distance,
            maximum_missing_seconds,
            cooldown_seconds,
            secondary_rotation_threshold,
            minimum_event_elapsed_seconds,
            maximum_event_elapsed_seconds,
            minimum_path_length,
            maximum_path_length,
            minimum_middle_axis_delta,
            maximum_middle_axis_delta,
            None,
            None,
            minimum_vertical_displacement,
            maximum_vertical_displacement,
            minimum_ring_angle,
            maximum_ring_angle,
            minimum_raw_secondary_axis_magnitude,
            confirmation_minimum_delta,
        )


class HandRotateLeftRule(_HandRotateRule):
    """Detect a counter-clockwise/left palm rotation with the left hand."""

    def __init__(
        self,
        *,
        rotation_threshold: float = 20.0,
        rearm_threshold: float = 10.0,
        maximum_hand_pose_distance: float = 0.20,
        maximum_missing_seconds: float = 0.60,
        cooldown_seconds: float = 1.25,
        secondary_rotation_threshold: float = 20.0,
        minimum_event_elapsed_seconds: float = 0.70,
        maximum_event_elapsed_seconds: float | None = 3.10,
        minimum_path_length: float = 0.078,
        maximum_path_length: float | None = 0.2805,
        minimum_middle_axis_delta: float | None = 21.0,
        maximum_middle_axis_delta: float | None = 166.0,
        minimum_index_angle_range: float | None = 37.5,
        maximum_index_angle_range: float | None = 135.0,
    ) -> None:
        super().__init__(
            LEFT_WRIST,
            LEFT_ELBOW,
            -1.0,
            "MOTION_HAND_ROTATE_LEFT",
            rotation_threshold,
            rearm_threshold,
            maximum_hand_pose_distance,
            maximum_missing_seconds,
            cooldown_seconds,
            secondary_rotation_threshold,
            minimum_event_elapsed_seconds,
            maximum_event_elapsed_seconds,
            minimum_path_length,
            maximum_path_length,
            minimum_middle_axis_delta,
            maximum_middle_axis_delta,
            minimum_index_angle_range,
            maximum_index_angle_range,
        )


@dataclass(slots=True)
class FingerSnapRule:
    """Detect a right-hand snap-like transition from curled to extended fingers.

    The camera cannot reliably hear a snap. This visual rule uses the
    supplied gesture description: the index finger becomes extended while the
    thumb is partially extended and the other fingers remain curled.
    """

    motion_code: str = "MOTION_FINGER_SNAP"
    extended_index_angle: float = 160.0
    extended_thumb_angle: float = 105.0
    curled_finger_angle: float = 165.0
    thumb_middle_contact_ratio: float = 1.35
    post_snap_contact_ratio: float = 0.60
    minimum_post_snap_thumb_vertical_gap: float = 0.0
    strict_pose_match_distance: float = 0.20
    minimum_detection_interval_seconds: float = 1.80
    maximum_transition_seconds: float = 3.0
    minimum_wrist_displacement: float = 0.04

    _armed: bool = False
    _latched: bool = False
    _last_detection_at: datetime | None = None
    _armed_at: datetime | None = None
    _armed_wrist: Landmark | None = None

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        hand = _hand_for_pose(frame, RIGHT_WRIST, "Right")
        if hand is None or len(hand.landmarks) < 21:
            return None

        ready = self._is_ready(hand)
        post_snap = self._is_post_snap(hand) and self._post_snap_pose_is_consistent(
            frame,
            hand,
        )

        if self._latched:
            if not post_snap:
                self._latched = False
                self._armed = ready
                self._armed_at = frame.captured_at if ready else None
                self._armed_wrist = hand.point(0) if ready else None
            return None

        if ready:
            if not self._armed:
                self._armed = True
                self._armed_at = frame.captured_at
                self._armed_wrist = hand.point(0)
            return None

        if self._armed and post_snap:
            transition_seconds = (
                None
                if self._armed_at is None
                else (frame.captured_at - self._armed_at).total_seconds()
            )
            wrist_displacement = (
                None
                if self._armed_wrist is None
                else landmark_distance(self._armed_wrist, hand.point(0))
            )
            if (
                transition_seconds is None
                or transition_seconds < 0
                or transition_seconds > self.maximum_transition_seconds
                or wrist_displacement is None
                or wrist_displacement < self.minimum_wrist_displacement
            ):
                self._armed = False
                self._armed_at = None
                self._armed_wrist = None
                return None
            if (
                self._last_detection_at is not None
                and (frame.captured_at - self._last_detection_at).total_seconds()
                < self.minimum_detection_interval_seconds
            ):
                self._latched = True
                self._armed = False
                self._armed_at = None
                self._armed_wrist = None
                return None
            self._latched = True
            self._armed = False
            self._armed_at = None
            self._armed_wrist = None
            self._last_detection_at = frame.captured_at
            return GestureDetection(self.motion_code, self._confidence(hand))

        return None

    def reset(self) -> None:
        self._armed = False
        self._latched = False
        self._last_detection_at = None
        self._armed_at = None
        self._armed_wrist = None

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
            and self._thumb_middle_distance(hand) <= self.post_snap_contact_ratio
        )

    def _post_snap_pose_is_consistent(
        self,
        frame: LandmarkFrame,
        hand: HandObservation,
    ) -> bool:
        """Reject a near-Pose hand whose thumb points the wrong way.

        One collected snap segment contains a temporary Hand/Pose wrist
        mismatch while the thumb is below the wrist. Keep that location-
        independent sample, but reject the same thumb shape when both
        trackers agree closely; that pattern was produced by swipe/rotation
        recordings rather than a snap release.
        """

        thumb_vertical_gap = hand.point(0).y - hand.point(4).y
        if thumb_vertical_gap >= self.minimum_post_snap_thumb_vertical_gap:
            return True
        pose_wrist = frame.pose.get(RIGHT_WRIST)
        if pose_wrist is None:
            return True
        return (
            landmark_distance(hand.point(0), pose_wrist)
            > self.strict_pose_match_distance
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
        and hand.point(4).y <= hand.point(0).y - 0.06
    )


def _is_thumbs_down(hand: HandObservation) -> bool:
    return (
        # A loose thumb angle made ordinary hand transitions look like Bad
        # when the wrist was also moving down.  The collected Bad samples
        # retain a clearly extended thumb at 150 degrees or more.
        _joint_angle(hand, 2, 3, 4) >= 150.0
        and _other_fingers_curled(hand, 155.0)
        and hand.point(4).y >= hand.point(0).y + 0.03
    )


@dataclass(slots=True)
class _ThumbVerticalMotionRule:
    """Detect a vertical movement after a stable right-hand thumb pose.

    The collected ``Good -> up`` samples held the thumb shape for several
    frames before the wrist moved.  The false positives were isolated,
    one-frame shape matches.  The rule therefore combines a stable pose with
    a real Pose-wrist trajectory.  Hand landmarks identify the pose; Pose
    wrist landmarks measure the arm motion and survive hand-detector dropout
    better than a hand wrist alone.
    """

    pose_name: str
    direction: float
    motion_code: str
    movement_threshold: float = 0.12
    reset_margin: float = 0.05
    cooldown_seconds: float = 0.75
    minimum_pose_frames: int = 3
    minimum_event_wrist_y: float | None = None

    _baseline_y: float | None = None
    _pose_run: int = 0
    _latched: bool = False
    _peak_movement: float = 0.0
    _last_detection_at: datetime | None = None

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        wrist = frame.pose.get(RIGHT_WRIST)
        if wrist is not None and not _visible(wrist):
            wrist = None
        hand = _hand_for_pose(frame, RIGHT_WRIST, "Right")
        if wrist is None and hand is not None and len(hand.landmarks) >= 21:
            wrist = hand.point(0)
        if wrist is None:
            self.reset()
            return None

        pose = hand is not None and len(hand.landmarks) >= 21 and (
            _is_thumbs_up(hand)
            if self.pose_name == "up"
            else _is_thumbs_down(hand)
        )
        # In image coordinates an upward movement decreases Y.  Keep the
        # lowest wrist position seen before the gesture as the baseline.
        if self._baseline_y is None:
            self._baseline_y = wrist.y
        elif self.direction > 0:
            self._baseline_y = max(self._baseline_y, wrist.y)
        else:
            self._baseline_y = min(self._baseline_y, wrist.y)

        if self._latched:
            assert self._baseline_y is not None
            movement = self.direction * (self._baseline_y - wrist.y)
            self._peak_movement = max(self._peak_movement, movement)
            if not pose:
                # Do not unlock on a transient HandLandmarker dropout.  A
                # forward open palm above is the explicit neutral separator;
                # without it, the same interval must not emit twice.
                if (
                    hand is not None
                    and len(hand.landmarks) >= 21
                    and _is_forward_open_palm(hand)
                ):
                    self.reset()
            elif movement <= self._peak_movement - self.reset_margin:
                # Re-arm from the current position, but require a fresh
                # stable pose before another event can be emitted.
                self._baseline_y = wrist.y
                self._pose_run = 1
                self._latched = False
                self._peak_movement = 0.0
            return None

        if not pose:
            self._pose_run = 0
            return None

        self._pose_run += 1
        if self._pose_run < self.minimum_pose_frames:
            return None

        assert self._baseline_y is not None
        movement = self.direction * (self._baseline_y - wrist.y)
        if movement < self.movement_threshold:
            return None

        if (
            self.minimum_event_wrist_y is not None
            and wrist.y < self.minimum_event_wrist_y
        ):
            # A hand already above this region is a held raised-hand pose,
            # not the collected Good -> up motion.
            return None

        if (
            self._last_detection_at is not None
            and (frame.captured_at - self._last_detection_at).total_seconds()
            < self.cooldown_seconds
        ):
            self._latched = True
            self._peak_movement = movement
            return None

        self._latched = True
        self._peak_movement = movement
        self._last_detection_at = frame.captured_at
        confidence = min(
            1.0,
            max(0.0, movement / (self.movement_threshold * 2)),
        )
        return GestureDetection(self.motion_code, confidence)

    def reset(self) -> None:
        self._baseline_y = None
        self._pose_run = 0
        self._latched = False
        self._peak_movement = 0.0


class ThumbsUpMoveUpRule(_ThumbVerticalMotionRule):
    """Detect a right-hand thumbs-up followed by upward movement."""

    def __init__(
        self,
        *,
        movement_threshold: float = 0.16,
        minimum_pose_frames: int = 4,
        minimum_event_wrist_y: float = 0.38,
        cooldown_seconds: float = 0.75,
    ) -> None:
        if minimum_pose_frames < 1:
            raise ValueError("minimum_pose_frames must be positive")
        super().__init__(
            "up",
            1.0,
            "MOTION_THUMBS_UP_MOVE_UP",
            movement_threshold,
            cooldown_seconds=cooldown_seconds,
            minimum_pose_frames=minimum_pose_frames,
            minimum_event_wrist_y=minimum_event_wrist_y,
        )


class ThumbsDownMoveDownRule:
    """Detect a stable Bad pose followed by a downward wrist movement.

    All ten collected ``Bad -> down`` samples contain at least three
    consecutive thumb-down frames, while the other collected motions contain
    no such run.  The gate is therefore deliberately strict; once it is
    satisfied, Pose carries the downward trajectory so temporary hand
    landmark dropout does not lose a real gesture.
    """

    def __init__(
        self,
        *,
        movement_threshold: float = 0.18,
        maximum_hand_pose_distance: float = 0.15,
        cooldown_seconds: float = 0.75,
        minimum_pose_frames: int = 4,
        pose_gate_seconds: float = 3.0,
        reset_margin: float = 0.05,
        maximum_event_vertical_offset: float = 0.80,
        maximum_event_elapsed_seconds: float = 2.30,
        minimum_pose_gate_age_without_hand: float = 0.211,
        maximum_stale_pose_gate_age: float = 0.50,
        minimum_stale_pose_gate_elapsed: float = 0.30,
        maximum_stale_pose_gate_vertical_offset: float = 1.0,
    ) -> None:
        if minimum_pose_frames < 1:
            raise ValueError("minimum_pose_frames must be positive")
        if pose_gate_seconds <= 0:
            raise ValueError("pose_gate_seconds must be positive")
        self.motion_code = "MOTION_THUMBS_DOWN_MOVE_DOWN"
        self.movement_threshold = movement_threshold
        self.maximum_hand_pose_distance = maximum_hand_pose_distance
        self.cooldown_seconds = cooldown_seconds
        self.minimum_pose_frames = minimum_pose_frames
        self.pose_gate_seconds = pose_gate_seconds
        self.reset_margin = reset_margin

        # These names remain available for callers that configured the former
        # PoseVerticalMotionRule.  The stable-pose gate and trajectory below
        # are the authoritative checks now.
        self.maximum_event_vertical_offset = maximum_event_vertical_offset
        self.maximum_event_elapsed_seconds = maximum_event_elapsed_seconds
        self.minimum_pose_gate_age_without_hand = minimum_pose_gate_age_without_hand
        self.maximum_stale_pose_gate_age = maximum_stale_pose_gate_age
        self.minimum_stale_pose_gate_elapsed = minimum_stale_pose_gate_elapsed
        self.maximum_stale_pose_gate_vertical_offset = maximum_stale_pose_gate_vertical_offset

        self._baseline_y: float | None = None
        self._gate_baseline_y: float | None = None
        self._pose_run = 0
        self._pose_seen_at: datetime | None = None
        self._latched = False
        self._peak_movement = 0.0
        self._last_detection_at: datetime | None = None
        # A left-hand swipe can make the otherwise idle right hand briefly
        # resemble a Bad pose.  Track the same swipe state here so the Bad
        # rule can suppress that cross-hand false positive without coupling
        # the generic GestureEngine to specific motion codes.
        self._opposite_swipe_rule = SwipeLeftRule()

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        self._opposite_swipe_rule.update(frame)
        if self._opposite_swipe_rule.is_active:
            self._clear_sequence()
            return None

        wrist = frame.pose.get(RIGHT_WRIST)
        if wrist is None or not _visible(wrist):
            self.reset()
            return None

        hand = _hand_for_pose(
            frame,
            RIGHT_WRIST,
            "Right",
            self.maximum_hand_pose_distance,
        )
        has_hand = hand is not None and len(hand.landmarks) >= 21
        pose_ready = has_hand and _is_thumbs_down(hand)
        pose_conflicting = has_hand and _is_thumbs_up(hand)

        # Downward motion increases image-space Y, so the highest pre-motion
        # wrist position is the useful baseline.
        if self._baseline_y is None:
            self._baseline_y = wrist.y
        else:
            self._baseline_y = min(self._baseline_y, wrist.y)

        if pose_conflicting:
            # A Good pose invalidates any older Bad gate.
            # Reset the latch together with the gate.  Clearing only the gate
            # leaves the rule in an impossible state and the next frame used
            # to fail on the assertion in the latched branch.
            self.reset()
            return None

        if self._latched:
            # Keep the state machine defensive even if a future transition
            # clears the gate while a latch is still set.
            if self._gate_baseline_y is None:
                self._latched = False
                self._peak_movement = 0.0
                return None
            movement = wrist.y - self._gate_baseline_y
            self._peak_movement = max(self._peak_movement, movement)
            # Stay latched for the rest of this continuous sequence.  A
            # transient hand-shape change or detector dropout is not enough
            # to turn one physical movement into two events.  The forward
            # open-palm marker is the explicit neutral separator used by the
            # collector and is the only normal re-arm path.
            if has_hand and _is_forward_open_palm(hand):
                self.reset()
            return None

        if pose_ready:
            self._pose_run += 1
            if self._pose_run >= self.minimum_pose_frames:
                self._pose_seen_at = frame.captured_at
                self._gate_baseline_y = self._baseline_y
        else:
            self._pose_run = 0

        if self._gate_baseline_y is None or self._pose_seen_at is None:
            return None

        gate_age = (frame.captured_at - self._pose_seen_at).total_seconds()
        if gate_age < 0 or gate_age > self.pose_gate_seconds:
            self._gate_baseline_y = None
            self._pose_seen_at = None
            return None

        movement = wrist.y - self._gate_baseline_y
        if movement < self.movement_threshold:
            return None

        event_vertical_offset = _pose_vertical_offset_from_shoulders(
            frame,
            wrist,
        )
        if (
            pose_ready
            and event_vertical_offset is not None
            and event_vertical_offset > self.maximum_event_vertical_offset
        ):
            # Collected Bad gestures complete around the chest.  Ordinary
            # activity produced the same temporary thumb shape only after
            # the wrist had fallen to the waist region.
            self._latched = True
            self._peak_movement = movement
            return None

        if (
            self._last_detection_at is not None
            and (frame.captured_at - self._last_detection_at).total_seconds()
            < self.cooldown_seconds
        ):
            self._latched = True
            self._peak_movement = movement
            return None

        self._latched = True
        self._peak_movement = movement
        self._last_detection_at = frame.captured_at
        return GestureDetection(
            self.motion_code,
            min(1.0, max(0.0, movement / (self.movement_threshold * 2))),
        )

    def reset(self) -> None:
        self._clear_sequence()
        self._opposite_swipe_rule.reset()

    def _clear_sequence(self) -> None:
        self._baseline_y = None
        self._gate_baseline_y = None
        self._pose_run = 0
        self._pose_seen_at = None
        self._latched = False
        self._peak_movement = 0.0


@dataclass(slots=True)
class ClapRule:
    """Detect both pose wrists moving from apart to a close position.

    Pose wrist landmarks remain available more often than hand landmarks when
    the palms overlap during a clap, so this rule deliberately does not depend
    on HandLandmarker output or handedness labels.
    """

    motion_code: str = "MOTION_CLAP"
    contact_ratio: float = 0.35
    contact_center_ratio: float = 0.30
    release_ratio: float = 1.60
    minimum_closing_step_ratio: float = 0.35
    maximum_contact_vertical_offset: float = 0.55

    _armed: bool = False
    _latched: bool = False
    _previous_ratio: float | None = None

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        left_wrist = frame.pose.get("LEFT_WRIST")
        right_wrist = frame.pose.get("RIGHT_WRIST")
        left_shoulder = frame.pose.get("LEFT_SHOULDER")
        right_shoulder = frame.pose.get("RIGHT_SHOULDER")
        if (
            left_wrist is None
            or right_wrist is None
            or left_shoulder is None
            or right_shoulder is None
            or not _visible(left_wrist, right_wrist, left_shoulder, right_shoulder)
        ):
            return None

        shoulder_width = abs(left_shoulder.x - right_shoulder.x)
        shoulder_width = max(shoulder_width, 0.001)
        shoulder_center_x = (left_shoulder.x + right_shoulder.x) / 2.0
        shoulder_center_y = (left_shoulder.y + right_shoulder.y) / 2.0
        ratio = abs(left_wrist.x - right_wrist.x) / shoulder_width
        left_center_ratio = abs(left_wrist.x - shoulder_center_x) / shoulder_width
        right_center_ratio = abs(right_wrist.x - shoulder_center_x) / shoulder_width
        contact_vertical_offset = abs(
            ((left_wrist.y + right_wrist.y) / 2.0) - shoulder_center_y
        ) / shoulder_width
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
            and left_center_ratio <= self.contact_center_ratio
            and right_center_ratio <= self.contact_center_ratio
            and previous_ratio is not None
            and previous_ratio - ratio >= self.minimum_closing_step_ratio
            and contact_vertical_offset <= self.maximum_contact_vertical_offset
        ):
            self._latched = True
            confidence = (self.release_ratio - ratio) / (
                self.release_ratio - self.contact_ratio
            )
            return GestureDetection(
                self.motion_code,
                min(1.0, max(0.0, confidence)),
            )
        return None

    def reset(self) -> None:
        self._armed = False
        self._latched = False
        self._previous_ratio = None


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


def _is_forward_open_palm(hand: HandObservation) -> bool:
    """Return whether an open palm matches the collection neutral marker."""

    if not _is_open_palm(hand) or len(hand.landmarks) < 21:
        return False
    wrist = hand.point(0)
    xs = [landmark.x for landmark in hand.landmarks]
    ys = [landmark.y for landmark in hand.landmarks]
    area = (max(xs) - min(xs)) * (max(ys) - min(ys))
    return (
        0.20 <= wrist.x <= 0.80
        and 0.25 <= wrist.y <= 0.75
        and area >= 0.01
    )


def _is_fist(hand: HandObservation) -> bool:
    return _other_fingers_curled(hand, 155.0)


@dataclass(slots=True)
class OpenToFistDownRule:
    """Detect a right hand changing from an open palm to a fist while lowering."""

    motion_code: str = "MOTION_OPEN_TO_FIST_DOWN"
    movement_threshold: float = 0.235
    maximum_event_vertical_offset: float = 1.0

    _start_y: float | None = None
    _armed: bool = False
    _latched: bool = False

    def update(self, frame: LandmarkFrame) -> GestureDetection | None:
        hand = _hand_for_pose(frame, RIGHT_WRIST, "Right")
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

        pose_wrist = frame.pose.get(RIGHT_WRIST)
        event_vertical_offset = (
            None
            if pose_wrist is None
            else _pose_vertical_offset_from_shoulders(frame, pose_wrist)
        )
        if (
            event_vertical_offset is not None
            and event_vertical_offset > self.maximum_event_vertical_offset
        ):
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


def _joint_angle(
    hand: HandObservation, first: int, middle: int, last: int
) -> float:
    return _angle(hand.point(first), hand.point(middle), hand.point(last))


def landmark_distance(first: Landmark, last: Landmark) -> float:
    """Return normalized 2D distance for future rule implementations."""

    return hypot(first.x - last.x, first.y - last.y)
