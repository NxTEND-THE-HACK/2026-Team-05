"""Stateful sliding-window motion recognition engine."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable

from ..domain.models import LandmarkFrame
from .base import GestureDetection
from .temporal import (
    ClassificationResult,
    ExponentialMovingAverage,
    HandGapFiller,
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
    frames once the shortest registered template can be compared. The same
    known result must be observed ``confirmation_count`` times before it is
    emitted, except for an approximate-exact match to a registered sequence.
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
        reset_after_gap_seconds: float = 1.5,
        minimum_window_frames: int | None = None,
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
        if minimum_window_frames is None:
            minimum_window_frames = window_frames
        if not 1 <= minimum_window_frames <= window_frames:
            raise ValueError(
                "minimum_window_frames must be between 1 and window_frames"
            )

        self.target_fps = target_fps
        self.window_frames = window_frames
        self.inference_stride_frames = inference_stride_frames
        self.confirmation_count = confirmation_count
        self.cooldown_seconds = cooldown_seconds
        self.minimum_window_frames = minimum_window_frames
        # Keep enough history for the longest registered sample so a short
        # prefix cannot be mistaken for a different motion. The configured
        # 30-frame window is still used as the earliest generic completion
        # point; longer samples simply receive more temporal context.
        self.history_frames = max(
            window_frames,
            max(len(template.frames) for template in template_items),
        )
        self.reset_after_gap_seconds = reset_after_gap_seconds
        self._sample_interval_seconds = 1.0 / target_fps
        self._normalizer = LandmarkNormalizer(
            visibility_threshold=landmark_visibility
        )
        self._smoother = ExponentialMovingAverage(ema_alpha)
        self._window = SlidingWindow(self.history_frames)
        self._classifier = KNNMotionClassifier(
            template_items,
            k=k,
            thresholds=configured_thresholds,
            # The specification calls for k-NN majority voting. Requiring all
            # k samples to have the same label rejects too many valid motion
            # variants, especially when a newly registered motion has only a
            # small number of examples.
            require_full_consensus=False,
        )
        self._hand_gap_filler = HandGapFiller()
        self._last_captured_at: datetime | None = None
        self._last_sampled_at: datetime | None = None
        self._sampled_frame_count = 0
        self._pending_motion: str | None = None
        self._pending_count = 0
        self._last_classification: ClassificationResult | None = None
        self._last_emitted_at: dict[str, datetime] = {}

    @classmethod
    def from_template_file(
        cls,
        path: str | Path,
        *,
        disabled_motions: Iterable[str] = (),
        **kwargs: object,
    ) -> "TemporalGestureEngine":
        template_set = TemplateSet.from_json(path).excluding(disabled_motions)
        window_frames = int(kwargs.get("window_frames", 30))
        kwargs.setdefault(
            "minimum_window_frames",
            min(
                window_frames,
                min(len(template.frames) for template in template_set.templates),
            ),
        )
        return cls(template_set, **kwargs)

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
        smoothed = self._smoother.update(normalized)
        self._window.append(self._hand_gap_filler.update(smoothed))
        if len(self._window) < self.minimum_window_frames:
            return ()

        is_inference_frame = (
            self._sampled_frame_count - self.minimum_window_frames
        ) % self.inference_stride_frames == 0
        if not is_inference_frame:
            return self._refine_candidate(frame.captured_at)

        result = self._classifier.classify(self._window.snapshot())
        self._last_classification = result
        return self._handle_classification(result, frame.captured_at)

    def _handle_classification(
        self,
        result: ClassificationResult,
        captured_at: datetime,
    ) -> tuple[GestureDetection, ...]:
        window_is_warm = len(self._window) < self.history_frames
        strong_consensus = (
            result.is_near_exact
            and self.minimum_window_frames < self.window_frames
        )
        if window_is_warm and not strong_consensus:
            # A short prefix of a dynamic gesture often resembles another
            # registered motion. Wait for the complete temporal context
            # instead of allowing a high-confidence prefix to fire.
            self._pending_motion = None
            self._pending_count = 0
            return ()
        return self._confirm(
            result.motion_code,
            result.confidence,
            captured_at,
            immediate=strong_consensus,
        )

    def _refine_candidate(
        self,
        captured_at: datetime,
    ) -> tuple[GestureDetection, ...]:
        """Check a promising candidate on skipped frames for exact completion.

        The regular classifier still runs at the configured stride. A motion
        can finish between two stride frames, though, so a promising recent
        candidate gets one additional exact-template check. Approximate
        results from this path are never emitted; it only closes the sampling
        gap when the registered sequence is actually complete.
        """

        if self.minimum_window_frames >= self.window_frames:
            return ()
        previous = self._last_classification
        if (
            previous is None
            or previous.motion_code is None
            or previous.confidence < 0.5
        ):
            return ()
        result = self._classifier.classify(self._window.snapshot())
        if not result.is_near_exact:
            return ()
        self._last_classification = result
        return self._confirm(
            result.motion_code,
            result.confidence,
            captured_at,
            immediate=True,
        )

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

    def _clear_sequence(self, *, reset_sampled_count: bool = True) -> None:
        self._window.clear()
        self._smoother.reset()
        self._hand_gap_filler.reset()
        self._last_sampled_at = None
        if reset_sampled_count:
            self._sampled_frame_count = 0
        self._pending_motion = None
        self._pending_count = 0
        self._last_classification = None

    def _confirm(
        self,
        motion_code: str | None,
        confidence: float,
        captured_at: datetime,
        *,
        immediate: bool = False,
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
        if immediate:
            self._pending_count = self.confirmation_count
        elif self._pending_count < self.confirmation_count:
            return ()

        previous = self._last_emitted_at.get(motion_code)
        if (
            previous is not None
            and (captured_at - previous).total_seconds() < self.cooldown_seconds
        ):
            self._clear_sequence(reset_sampled_count=False)
            return ()

        self._last_emitted_at[motion_code] = captured_at
        logger.debug(
            "motion confirmed motion_code=%s confidence=%.3f",
            motion_code,
            confidence,
        )
        detection = GestureDetection(motion_code, confidence)
        # A confirmed event marks the end of the current sequence. Clear the
        # temporal evidence before the next gesture. The counter belongs to
        # the sequence as well; restarting it lets a new template align from
        # its first frame instead of inheriting the previous gesture's phase.
        # Per-motion cooldown state is kept separately.
        self._clear_sequence()
        return (detection,)
