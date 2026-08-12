"""The fixed motion catalogue supported by the recognition worker."""

from __future__ import annotations

MOTION_CODES = (
    "POSE_RIGHT_HAND_UP",
    "POSE_LEFT_HAND_UP",
    "MOTION_SWIPE_RIGHT",
    "MOTION_SWIPE_LEFT",
    "MOTION_FINGER_SNAP",
    "MOTION_THUMBS_UP_MOVE_UP",
    "MOTION_THUMBS_DOWN_MOVE_DOWN",
    "MOTION_CLAP",
    "MOTION_OPEN_TO_FIST_DOWN",
    "MOTION_HAND_ROTATE_RIGHT",
    "MOTION_HAND_ROTATE_LEFT",
)

SUPPORTED_MOTION_CODES = frozenset(MOTION_CODES)
