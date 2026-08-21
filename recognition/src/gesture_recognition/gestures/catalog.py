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

# The normal worker startup uses this allowlist.  Other motions remain in the
# catalogue so their templates and explicit test/monitor configurations are
# still available without being enabled in production by default.
NORMAL_STARTUP_MOTION_CODES = (
    "POSE_RIGHT_HAND_UP",
    "POSE_LEFT_HAND_UP",
    "MOTION_SWIPE_RIGHT",
    "MOTION_SWIPE_LEFT",
    "MOTION_THUMBS_UP_MOVE_UP",
    "MOTION_THUMBS_DOWN_MOVE_DOWN",
    "MOTION_FINGER_SNAP",
)

NORMAL_STARTUP_DISABLED_MOTION_CODES = frozenset(
    motion_code
    for motion_code in MOTION_CODES
    if motion_code not in NORMAL_STARTUP_MOTION_CODES
)
