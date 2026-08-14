"""Record pose and hand landmarks for a labeled static-pose dataset."""

from __future__ import annotations

import argparse
import json
import logging
import signal
from pathlib import Path
from threading import Event

from gesture_recognition.domain.models import HandObservation, Landmark, LandmarkFrame
from gesture_recognition.inference.mediapipe_detector import MediaPipeDetector
from gesture_recognition.stream.factory import create_frame_source

logger = logging.getLogger("pose-recorder")


def _landmark_to_dict(landmark: Landmark) -> dict[str, float | None]:
    return {
        "x": landmark.x,
        "y": landmark.y,
        "z": landmark.z,
        "visibility": landmark.visibility,
    }


def _hand_to_dict(hand: HandObservation) -> dict[str, object]:
    return {
        "handedness": hand.handedness,
        "landmarks": [_landmark_to_dict(item) for item in hand.landmarks],
    }


def _frame_to_record(frame: LandmarkFrame, label: str, sequence: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "label": label,
        "captured_at": frame.captured_at.isoformat(),
        "sequence": sequence,
        "pose": {
            name: _landmark_to_dict(landmark)
            for name, landmark in frame.pose.items()
        },
        "hands": [_hand_to_dict(hand) for hand in frame.hands],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record MediaPipe landmarks from an MJPEG or local camera."
    )
    parser.add_argument("--camera-source")
    parser.add_argument("--webcam-index", type=int)
    parser.add_argument("--camera-profile", default="micon")
    parser.add_argument("--camera-fps", type=float)
    parser.add_argument("--jpeg-quality", type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--label", default="POSE_RIGHT_HAND_UP")
    parser.add_argument(
        "--pose-model-path", default="models/pose_landmarker_full.task"
    )
    parser.add_argument("--hand-model-path", default="models/hand_landmarker.task")
    parser.add_argument("--poll-interval", type=float, default=0.01)
    args = parser.parse_args()
    if args.camera_source is None and args.webcam_index is None:
        parser.error("one of --camera-source or --webcam-index is required")
    if args.camera_source is not None and args.webcam_index is not None:
        parser.error("--camera-source and --webcam-index cannot be combined")
    return args


def main() -> None:
    args = _parse_args()
    if args.poll_interval <= 0:
        raise SystemExit("--poll-interval must be positive")
    if args.webcam_index is not None and args.webcam_index < 0:
        raise SystemExit("--webcam-index must not be negative")
    if args.camera_fps is not None and args.camera_fps <= 0:
        raise SystemExit("--camera-fps must be positive")
    if args.jpeg_quality is not None and not 1 <= args.jpeg_quality <= 100:
        raise SystemExit("--jpeg-quality must be between 1 and 100")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)

    stop_event = Event()
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())

    try:
        source = create_frame_source(
            camera_source=args.camera_source,
            webcam_index=args.webcam_index,
            webcam_profile=args.camera_profile,
            webcam_fps=args.camera_fps,
            webcam_jpeg_quality=args.jpeg_quality,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    detector = MediaPipeDetector(
        pose_model_path=args.pose_model_path,
        hand_model_path=args.hand_model_path,
    )
    sequence = 0
    records = 0

    source.start()
    try:
        with args.output.open("a", encoding="utf-8") as output:
            logger.info("recording label=%s output=%s", args.label, args.output)
            while not stop_event.is_set():
                frame = source.read_latest(after_sequence=sequence)
                if frame is None:
                    stop_event.wait(args.poll_interval)
                    continue
                sequence = frame.sequence

                try:
                    landmarks = detector.detect(frame)
                except ValueError as exc:
                    logger.warning("skipping invalid frame: %s", exc)
                    continue

                output.write(
                    json.dumps(
                        _frame_to_record(landmarks, args.label, sequence),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                output.flush()
                records += 1
                if records % 30 == 0:
                    logger.info("recorded_frames=%s", records)
    finally:
        source.stop()
        detector.close()
        logger.info("recording stopped frames=%s output=%s", records, args.output)


if __name__ == "__main__":
    main()
