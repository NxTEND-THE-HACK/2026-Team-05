"""Evaluate all registered gesture rules."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from ..domain.models import LandmarkFrame
from .base import GestureDetection, GestureRule


class GestureEngine:
    """Keep rule state isolated to one camera worker."""

    def __init__(
        self,
        rules: Iterable[GestureRule],
        *,
        reset_after_gap_seconds: float = 0.75,
    ) -> None:
        if reset_after_gap_seconds <= 0:
            raise ValueError("reset_after_gap_seconds must be positive")
        self._rules = tuple(rules)
        codes = [rule.motion_code for rule in self._rules]
        if len(codes) != len(set(codes)):
            raise ValueError("gesture motion codes must be unique")
        self._reset_after_gap_seconds = reset_after_gap_seconds
        self._last_captured_at: datetime | None = None

    def update(self, frame: LandmarkFrame) -> tuple[GestureDetection, ...]:
        if self._last_captured_at is not None:
            gap_seconds = (frame.captured_at - self._last_captured_at).total_seconds()
            if gap_seconds < 0 or gap_seconds > self._reset_after_gap_seconds:
                for rule in self._rules:
                    rule.reset()
        self._last_captured_at = frame.captured_at

        detections: list[GestureDetection] = []
        for rule in self._rules:
            detection = rule.update(frame)
            if detection is not None:
                detections.append(detection)
        return tuple(detections)

    def reset(self) -> None:
        for rule in self._rules:
            rule.reset()
        self._last_captured_at = None
