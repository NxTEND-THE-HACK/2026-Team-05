"""Recognition worker entrypoint."""

from __future__ import annotations

import argparse
import logging
import signal
from collections.abc import Sequence
from threading import Event

from .config import Settings
from .delivery.go_api_client import GoApiClient
from .delivery.null import NullDeliveryClient
from .gestures.registry import default_engine
from .inference.mediapipe_detector import MediaPipeDetector
from .observability.logging import configure_logging
from .sound.source import SoundEventStream
from .sound.validation import SoundValidationCoordinator
from .stream.factory import create_frame_source
from .worker import RecognitionWorker


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-delivery",
        action="store_true",
        help="recognize motions without sending events to the Go API",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    stop_event = Event()
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())

    source = create_frame_source(
        camera_source=settings.camera_source,
        webcam_index=settings.webcam_index,
        webcam_profile=settings.webcam_profile,
        webcam_fps=settings.webcam_fps,
        webcam_jpeg_quality=settings.webcam_jpeg_quality,
        reconnect_initial_seconds=settings.reconnect_initial_seconds,
        reconnect_max_seconds=settings.reconnect_max_seconds,
        stale_after_seconds=settings.camera_stale_after_seconds,
    )
    sound_validator = None
    if settings.sound_event_source is not None:
        sound_validator = SoundValidationCoordinator(
            SoundEventStream(
                settings.sound_event_source,
                reconnect_initial_seconds=settings.reconnect_initial_seconds,
                reconnect_max_seconds=settings.reconnect_max_seconds,
                stale_after_seconds=settings.sound_stale_after_seconds,
            ),
            match_before_seconds=settings.sound_match_before_seconds,
            match_after_seconds=settings.sound_match_after_seconds,
        )
    worker = RecognitionWorker(
        camera_id=settings.camera_id,
        source=source,
        detector=MediaPipeDetector(
            pose_model_path=settings.pose_model_path,
            hand_model_path=settings.hand_model_path,
        ),
        engine=default_engine(
            templates_path=settings.motion_samples_path,
            target_fps=settings.target_fps,
            window_frames=settings.window_frames,
            inference_stride_frames=settings.inference_stride_frames,
            ema_alpha=settings.ema_alpha,
            landmark_visibility=settings.landmark_visibility,
            k=settings.knn_k,
            confirmation_count=settings.confirmation_count,
            cooldown_seconds=settings.recognition_cooldown_seconds,
            reset_after_gap_seconds=settings.recognition_reset_gap_seconds,
        ),
        client=(
            NullDeliveryClient()
            if args.no_delivery
            else GoApiClient(
                settings.go_api_url,
                retries=settings.detection_send_retries,
                timeout_seconds=settings.detection_send_timeout_seconds,
            )
        ),
        frame_poll_interval_seconds=settings.frame_poll_interval_seconds,
        sound_validator=sound_validator,
    )
    logging.getLogger(__name__).info(
        "recognition worker started camera_id=%s delivery=%s sound_validation=%s",
        settings.camera_id,
        "disabled" if args.no_delivery else "go-api",
        "enabled" if sound_validator is not None else "disabled",
    )
    worker.run(stop_event)


if __name__ == "__main__":
    main()
