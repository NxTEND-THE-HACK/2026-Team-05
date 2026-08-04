"""Recognition worker entrypoint."""

from __future__ import annotations

import logging
import signal
from threading import Event

from .config import Settings
from .delivery.go_api_client import GoApiClient
from .gestures.registry import default_engine
from .inference.mediapipe_detector import MediaPipeDetector
from .observability.logging import configure_logging
from .stream.mjpeg import MjpegFrameSource
from .worker import RecognitionWorker


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    stop_event = Event()
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())

    source = MjpegFrameSource(
        settings.camera_source,
        reconnect_initial_seconds=settings.reconnect_initial_seconds,
        reconnect_max_seconds=settings.reconnect_max_seconds,
    )
    worker = RecognitionWorker(
        camera_id=settings.camera_id,
        source=source,
        detector=MediaPipeDetector(),
        engine=default_engine(),
        client=GoApiClient(
            settings.go_api_url,
            retries=settings.detection_send_retries,
            timeout_seconds=settings.detection_send_timeout_seconds,
        ),
        frame_poll_interval_seconds=settings.frame_poll_interval_seconds,
    )
    logging.getLogger(__name__).info("recognition worker started camera_id=%s", settings.camera_id)
    worker.run(stop_event)


if __name__ == "__main__":
    main()
