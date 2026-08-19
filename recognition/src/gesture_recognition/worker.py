"""Camera recognition worker orchestration."""

from __future__ import annotations

import logging
from threading import Event

from .delivery.go_api_client import DeliveryError
from .domain.models import DetectionEvent
from .gestures.base import GestureEngineLike
from .inference.mediapipe_detector import MediaPipeDetector
from .sound.validation import (
    SoundValidationCoordinator,
    SoundValidationDecision,
    decisions_for_unconfigured_sound,
)
from .stream.base import FrameSource

logger = logging.getLogger(__name__)


class RecognitionWorker:
    """Connect one camera source to inference, rules, and Go delivery."""

    def __init__(
        self,
        *,
        camera_id: str,
        source: FrameSource,
        detector: MediaPipeDetector,
        engine: GestureEngineLike,
        client: object,
        frame_poll_interval_seconds: float = 0.001,
        sound_validator: SoundValidationCoordinator | None = None,
    ) -> None:
        if not camera_id:
            raise ValueError("camera_id must not be empty")
        if frame_poll_interval_seconds <= 0:
            raise ValueError("frame_poll_interval_seconds must be positive")
        self.camera_id = camera_id
        self._source = source
        self._detector = detector
        self._engine = engine
        self._client = client
        self._poll_interval = frame_poll_interval_seconds
        self._sound_validator = sound_validator

    def run(self, stop_event: Event | None = None) -> None:
        stop = stop_event or Event()
        sequence = 0
        self._source.start()
        if self._sound_validator is not None:
            self._sound_validator.start()
        try:
            while not stop.is_set():
                if self._sound_validator is not None:
                    self._handle_decisions(self._sound_validator.poll())

                frame = self._source.read_latest(after_sequence=sequence)
                if frame is None:
                    stop.wait(self._poll_interval)
                    continue
                sequence = frame.sequence

                try:
                    landmarks = self._detector.detect(frame)
                except ValueError as exc:
                    logger.warning("invalid camera frame camera_id=%s error=%s", self.camera_id, exc)
                    continue

                detections = self._engine.update(landmarks)
                if self._sound_validator is None:
                    decisions = decisions_for_unconfigured_sound(
                        detections,
                        detected_at=landmarks.captured_at,
                    )
                else:
                    decisions = self._sound_validator.submit(
                        detections,
                        detected_at=landmarks.captured_at,
                    )
                self._handle_decisions(decisions)
        finally:
            if self._sound_validator is not None:
                self._sound_validator.stop()
            self._source.stop()
            self._detector.close()

    def _handle_decisions(
        self,
        decisions: tuple[SoundValidationDecision, ...],
    ) -> None:
        for decision in decisions:
            if decision.result != "not_required":
                logger.info(
                    "sound validation camera_id=%s motion_code=%s result=%s",
                    self.camera_id,
                    decision.detection.motion_code,
                    decision.result,
                )
            if not decision.accepted:
                continue

            event = DetectionEvent.create(
                camera_id=self.camera_id,
                motion_code=decision.detection.motion_code,
                confidence=decision.detection.confidence,
                detected_at=decision.detected_at,
            )
            try:
                self._client.send(event)
            except DeliveryError as exc:
                logger.error(
                    "detection delivery failed camera_id=%s motion_code=%s error=%s",
                    self.camera_id,
                    event.motion_code,
                    exc,
                )
