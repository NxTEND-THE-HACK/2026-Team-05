"""Default fixed gesture set for the MVP."""

from __future__ import annotations

from .base import GestureRule
from .engine import GestureEngine
from .rules import (
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


def default_rules() -> tuple[GestureRule, ...]:
    return (
        RightHandRaisedRule(),
        LeftHandRaisedRule(),
        SwipeRightRule(),
        SwipeLeftRule(),
        FingerSnapRule(),
        ThumbsUpMoveUpRule(),
        ThumbsDownMoveDownRule(),
        ClapRule(),
        OpenToFistDownRule(),
        HandRotateRightRule(),
        HandRotateLeftRule(),
    )


def default_engine() -> GestureEngine:
    return GestureEngine(default_rules())
