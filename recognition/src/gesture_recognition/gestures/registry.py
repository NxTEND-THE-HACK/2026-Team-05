"""Default fixed gesture set for the MVP."""

from __future__ import annotations

from .base import GestureRule
from .engine import GestureEngine
from .rules import RightHandRaisedRule, SwipeRightRule


def default_rules() -> tuple[GestureRule, ...]:
    return (RightHandRaisedRule(), SwipeRightRule())


def default_engine() -> GestureEngine:
    return GestureEngine(default_rules())
