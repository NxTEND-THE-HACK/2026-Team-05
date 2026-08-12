"""Stateful sliding-window motion recognition engine."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable

from ..domain.models import LandmarkFrame
from .base import GestureDetection
from .temporal import (
    ExponentialMovingAverage,
    KNNMotionClassifier,
    LandmarkNormalizer,
    MotionTemplate,
    SlidingWindow,
    TemplateSet,
)

logger = logging.getLogger(__name__)


class TemporalGestureEngine:
    """Classify normalized landmark windows and emit confirmed detections.

    Frames are sampled at ``target_fps`` before entering the window. A
    classification is attempted every ``inference_stride_frames`` sampled
    frames once the window is full. The same known result must be observed
    ``confirmation_count`` times before it is emitted.
    """

    def __init__(
        self,
        templates: TemplateSet | Iterable[MotionTemplate],
        *,
        thresholds: dict[str, float] | None = None,
        target_fps: float = 15.0,
        window_frames: int = 30,
        inference_stride_frames: int = 3,
        ema_alpha: float = 0.4,
        landmark_visibility: float = 0.5,
        k: int = 3,
        confirmation_count: int = 2,
        cooldown_seconds: float = 1.0,
        reset_after_gap_seconds: float = 0.75,
    ) -> None:
        if isinstance(templates, TemplateSet):
            template_items = templates.templates
            configured_thresholds = templates.thresholds
        else:
            template_items = tuple(templates)
            configured_thresholds = {}
        if thresholds is not None:
            configured_thresholds = dict(configured_thresholds)
            configured_thresholds.update(thresholds)
        if target_fps <= 0:
            raise ValueError("target_fps must be positive")
        if window_frames < 1:
            raise ValueError("window_frames must be positive")
        if inference_stride_frames < 1:
            raise ValueError("inference_stride_frames must be positive")
        if confirmation_count < 1:
            raise ValueError("confirmation_count must be positive")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must not be negative")
        if reset_after_gap_seconds <= 0:
            raise ValueError("reset_after_gap_seconds must be positive")

        self.target_fps = target_fps
        self.window_frames = window_frames
        self.inference_stride_frames = inference_stride_frames
        self.confirmation_count = confirmation_count
        self.cooldown_seconds = cooldown_seconds
        self.reset_after_gap_seconds = reset_after_gap_seconds
        self._sample_interval_seconds = 1.0 / target_fps
        self._normalizer = LandmarkNormalizer(
            visibility_threshold=landmark_visibility
        )
        self._smoother = ExponentialMovingAverage(ema_alpha)
        self._window = SlidingWindow(window_frames)
        self._classifier = KNNMotionClassifier(
            template_items,
            k=k,
            thresholds=configured_thresholds,
        )
        self._last_captured_at: datetime | None = None
        self._last_sampled_at: datetime | None = None
        self._sampled_frame_count = 0
        self._pending_motion: str | None = None
        self._pending_count = 0
        self._last_emitted_at: dict[str, datetime] = {}

    @classmethod
    def from_template_file(
        cls,
        path: str | Path,
        **kwargs: object,
    ) -> "TemporalGestureEngine":
        return cls(TemplateSet.from_json(path), **kwargs)

    def update(self, frame: LandmarkFrame) -> tuple[GestureDetection, ...]:
        self._reset_for_capture_gap(frame.captured_at)
        self._last_captured_at = frame.captured_at

        if not self._should_sample(frame.captured_at):
            return ()

        normalized = self._normalizer.normalize(frame)
        if normalized is None:
            # A frame without a reliable shoulder anchor cannot be compared
            # safely. Do not let the old sequence bridge that gap.
            self._clear_sequence()
            return ()

        self._last_sampled_at = frame.captured_at
        self._sampled_frame_count += 1
        self._window.append(self._smoother.update(normalized))
        if (
            not self._window.is_full
            or self._sampled_frame_count % self.inference_stride_frames != 0
        ):
            return ()

        result = self._classifier.classify(self._window.snapshot())
        return self._confirm(result.motion_code, result.confidence, frame.captured_at)

    def reset(self) -> None:
        self._clear_sequence()
        self._last_captured_at = None
        self._last_emitted_at.clear()

    @property
    def window(self) -> SlidingWindow:
        return self._window

    @property
    def sampled_frame_count(self) -> int:
        return self._sampled_frame_count

    def _reset_for_capture_gap(self, captured_at: datetime) -> None:
        if self._last_captured_at is None:
            return
        elapsed = (captured_at - self._last_captured_at).total_seconds()
        if elapsed < 0 or elapsed > self.reset_after_gap_seconds:
            self._clear_sequence()

    def _should_sample(self, captured_at: datetime) -> bool:
        if self._last_sampled_at is None:
            return True
        elapsed = (captured_at - self._last_sampled_at).total_seconds()
        # Timestamps generated from a 15 FPS stream are often represented as
        # repeating binary fractions (for example 1 / 15). The small epsilon
        # prevents an exact target-rate frame from being skipped by rounding.
        return elapsed + 1e-6 >= self._sample_interval_seconds

    def _clear_sequence(self) -> None:
        self._window.clear()
        self._smoother.reset()
        self._last_sampled_at = None
        self._sampled_frame_count = 0
        self._pending_motion = None
        self._pending_count = 0

    def _confirm(
        self,
        motion_code: str | None,
        confidence: float,
        captured_at: datetime,
    ) -> tuple[GestureDetection, ...]:
        if motion_code is None:
            self._pending_motion = None
            self._pending_count = 0
            return ()

        if motion_code == self._pending_motion:
            self._pending_count += 1
        else:
            self._pending_motion = motion_code
            self._pending_count = 1
        if self._pending_count < self.confirmation_count:
            return ()

        previous = self._last_emitted_at.get(motion_code)
        if (
            previous is not None
            and (captured_at - previous).total_seconds() < self.cooldown_seconds
        ):
            return ()

        self._last_emitted_at[motion_code] = captured_at
        logger.debug(
            "motion confirmed motion_code=%s confidence=%.3f",
            motion_code,
            confidence,
        )
        return (GestureDetection(motion_code, confidence),)
