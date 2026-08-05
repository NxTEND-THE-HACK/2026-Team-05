"""Evaluate all registered gesture rules."""

from __future__ import annotations

from collections.abc import Iterable

from ..domain.models import LandmarkFrame
from .base import GestureDetection, GestureRule


class GestureEngine:
    """Keep rule state isolated to one camera worker."""

    def __init__(self, rules: Iterable[GestureRule]) -> None:
        self._rules = tuple(rules)
        codes = [rule.motion_code for rule in self._rules]
        if len(codes) != len(set(codes)):
            raise ValueError("gesture motion codes must be unique")

    def update(self, frame: LandmarkFrame) -> tuple[GestureDetection, ...]:
        detections: list[GestureDetection] = []
        for rule in self._rules:
            detection = rule.update(frame)
            if detection is not None:
                detections.append(detection)
        return tuple(detections)

    def reset(self) -> None:
        for rule in self._rules:
            rule.reset()
