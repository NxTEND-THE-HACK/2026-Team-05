"""Run live recognition and print detections without delivering any events."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import signal
import time
from datetime import datetime
from pathlib import Path
from threading import Event

from gesture_recognition.domain.models import LandmarkFrame
from gesture_recognition.gestures.registry import default_engine
from gesture_recognition.inference.mediapipe_detector import MediaPipeDetector
from gesture_recognition.stream.base import SourceStatus
from gesture_recognition.stream.factory import create_frame_source


logger = logging.getLogger(__name__)

DEFAULT_CAMERA_SOURCE = "http://10.0.1.107/stream"


MOTION_NAMES = {
    "POSE_RIGHT_HAND_UP": "右手上げ",
    "POSE_LEFT_HAND_UP": "左手上げ",
    "MOTION_SWIPE_RIGHT": "右スワイプ",
    "MOTION_SWIPE_LEFT": "左スワイプ",
    "MOTION_FINGER_SNAP": "指パッチン",
    "MOTION_THUMBS_UP_MOVE_UP": "Goodから上",
    "MOTION_THUMBS_DOWN_MOVE_DOWN": "Badから下",
    "MOTION_CLAP": "拍手",
    "MOTION_OPEN_TO_FIST_DOWN": "パーからグーで下げる",
    "MOTION_HAND_ROTATE_RIGHT": "右回し",
    "MOTION_HAND_ROTATE_LEFT": "左回し",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--camera-source",
        default=None,
        help="HTTP MJPEG URL (default: the configured demo camera URL)",
    )
    parser.add_argument(
        "--webcam-index",
        type=int,
        help="Open a local USB or built-in camera instead of MJPEG",
    )
    parser.add_argument(
        "--camera-profile",
        default="micon",
        help="Local-camera output profile (default: micon)",
    )
    parser.add_argument(
        "--camera-fps",
        type=float,
        help="Override the local-camera output FPS",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        help="Override the local-camera OpenCV JPEG quality (1-100)",
    )
    parser.add_argument(
        "--disable-motion",
        dest="disabled_motions",
        action="append",
        choices=tuple(MOTION_NAMES),
        default=[],
        metavar="MOTION_CODE",
        help="Disable a motion code; repeat this option for multiple motions",
    )
    parser.add_argument("--pose-model-path", default="models/pose_landmarker_full.task")
    parser.add_argument("--hand-model-path", default="models/hand_landmarker.task")
    parser.add_argument("--poll-interval", type=float, default=0.01)
    parser.add_argument("--stale-after-seconds", type=float, default=3.0)
    parser.add_argument(
        "--state-path",
        type=Path,
        default=Path("data/monitor_detections_live.json"),
    )
    parser.add_argument(
        "--overlay-path",
        type=Path,
        default=Path("data/monitor_landmarks.jpg"),
        help="Path for the latest MediaPipe landmark overlay JPEG",
    )
    return parser.parse_args()


def _format_timestamp(value: datetime) -> str:
    return value.astimezone().strftime("%H:%M:%S")


_POSE_CONNECTIONS = (
    ("NOSE", "LEFT_EYE_INNER"),
    ("LEFT_EYE_INNER", "LEFT_EYE"),
    ("LEFT_EYE", "LEFT_EYE_OUTER"),
    ("LEFT_EYE_OUTER", "LEFT_EAR"),
    ("NOSE", "RIGHT_EYE_INNER"),
    ("RIGHT_EYE_INNER", "RIGHT_EYE"),
    ("RIGHT_EYE", "RIGHT_EYE_OUTER"),
    ("RIGHT_EYE_OUTER", "RIGHT_EAR"),
    ("MOUTH_LEFT", "MOUTH_RIGHT"),
    ("LEFT_SHOULDER", "RIGHT_SHOULDER"),
    ("LEFT_SHOULDER", "LEFT_ELBOW"),
    ("LEFT_ELBOW", "LEFT_WRIST"),
    ("LEFT_WRIST", "LEFT_PINKY"),
    ("LEFT_WRIST", "LEFT_INDEX"),
    ("LEFT_WRIST", "LEFT_THUMB"),
    ("RIGHT_SHOULDER", "RIGHT_ELBOW"),
    ("RIGHT_ELBOW", "RIGHT_WRIST"),
    ("RIGHT_WRIST", "RIGHT_PINKY"),
    ("RIGHT_WRIST", "RIGHT_INDEX"),
    ("RIGHT_WRIST", "RIGHT_THUMB"),
    ("LEFT_SHOULDER", "LEFT_HIP"),
    ("RIGHT_SHOULDER", "RIGHT_HIP"),
    ("LEFT_HIP", "RIGHT_HIP"),
    ("LEFT_HIP", "LEFT_KNEE"),
    ("LEFT_KNEE", "LEFT_ANKLE"),
    ("LEFT_ANKLE", "LEFT_HEEL"),
    ("LEFT_ANKLE", "LEFT_FOOT_INDEX"),
    ("RIGHT_HIP", "RIGHT_KNEE"),
    ("RIGHT_KNEE", "RIGHT_ANKLE"),
    ("RIGHT_ANKLE", "RIGHT_HEEL"),
    ("RIGHT_ANKLE", "RIGHT_FOOT_INDEX"),
)

_HAND_CONNECTIONS = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 4),
    (0, 5),
    (5, 6),
    (6, 7),
    (7, 8),
    (0, 9),
    (9, 10),
    (10, 11),
    (11, 12),
    (0, 13),
    (13, 14),
    (14, 15),
    (15, 16),
    (0, 17),
    (17, 18),
    (18, 19),
    (19, 20),
    (5, 9),
    (9, 13),
    (13, 17),
)


def _write_landmark_overlay(
    path: Path,
    frame_data: bytes,
    landmarks: LandmarkFrame,
) -> None:
    """Write the latest camera frame with MediaPipe points drawn on it."""

    import cv2
    import numpy as np

    image = cv2.imdecode(
        np.frombuffer(frame_data, dtype=np.uint8),
        cv2.IMREAD_COLOR,
    )
    if image is None:
        raise ValueError("frame does not contain a decodable JPEG image")

    height, width = image.shape[:2]
    # The monitor should show only the inferred landmarks, not the camera image.
    image = np.zeros_like(image)

    def point(landmark: object) -> tuple[int, int] | None:
        x = float(getattr(landmark, "x"))
        y = float(getattr(landmark, "y"))
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        if not -0.1 <= x <= 1.1 or not -0.1 <= y <= 1.1:
            return None
        return (
            max(0, min(width - 1, int(round(x * width)))),
            max(0, min(height - 1, int(round(y * height)))),
        )

    pose_points = {
        name: point(landmark)
        for name, landmark in landmarks.pose.items()
    }
    for item in pose_points.values():
        if item is not None:
            cv2.circle(image, item, 5, (40, 220, 90), -1, cv2.LINE_AA)

    hand_count = 0
    hand_point_count = 0
    for hand in landmarks.hands:
        hand_count += 1
        hand_points = [point(item) for item in hand.landmarks]
        hand_point_count += sum(item is not None for item in hand_points)
        color = (
            (255, 180, 40)
            if hand.handedness.lower() == "right"
            else (40, 180, 255)
        )
        for item in hand_points:
            if item is not None:
                cv2.circle(image, item, 4, color, -1, cv2.LINE_AA)

    path.parent.mkdir(parents=True, exist_ok=True)
    success, encoded = cv2.imencode(
        ".jpg",
        image,
        [cv2.IMWRITE_JPEG_QUALITY, 85],
    )
    if not success:
        raise RuntimeError("failed to encode landmark overlay JPEG")
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(encoded.tobytes())
    for attempt in range(5):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


def _write_state(
    path: Path,
    *,
    status: str,
    history: list[dict[str, object]],
    camera_status: SourceStatus | None = None,
    landmark_status: dict[str, object] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "appliance_delivery": False,
        "updated_at": datetime.now().astimezone().isoformat(),
        "camera": (
            None if camera_status is None else camera_status.to_payload()
        ),
        "landmarks": landmark_status,
        "latest": history[-1] if history else None,
        "history": list(reversed(history[-50:])),
    }
    temporary = path.with_name(
        f"{path.name}.{os.getpid()}.tmp"
    )
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for attempt in range(5):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


def _print_camera_status(
    status: SourceStatus,
    previous_signature: tuple[object, ...] | None = None,
) -> tuple[object, ...]:
    payload = status.to_payload()
    signature = (
        payload.get("source_type"),
        payload.get("profile"),
        payload.get("device_index"),
        payload.get("state"),
        payload.get("receive_fps"),
        payload.get("target_fps"),
        payload.get("frame_width"),
        payload.get("frame_height"),
    )
    if signature != previous_signature:
        target_fps = payload.get("target_fps")
        fps_text = f"{payload.get('receive_fps', 0)}"
        if target_fps is not None:
            fps_text += f"/{target_fps}"
        print(
            "[camera] "
            f"source={payload.get('source_type')} "
            f"profile={payload.get('profile') or '-'} "
            f"state={payload.get('state')} "
            f"fps={fps_text} "
            f"size={payload.get('frame_width') or '-'}x{payload.get('frame_height') or '-'}",
            flush=True,
        )
    return signature


def main() -> None:
    args = _parse_args()
    if args.poll_interval <= 0 or args.stale_after_seconds <= 0:
        raise SystemExit("poll and stale thresholds must be positive")
    if args.camera_source is not None and args.webcam_index is not None:
        raise SystemExit("--camera-source and --webcam-index cannot be combined")
    if args.webcam_index is not None and args.webcam_index < 0:
        raise SystemExit("--webcam-index must not be negative")
    if args.camera_fps is not None and args.camera_fps <= 0:
        raise SystemExit("--camera-fps must be positive")
    if args.jpeg_quality is not None and not 1 <= args.jpeg_quality <= 100:
        raise SystemExit("--jpeg-quality must be between 1 and 100")

    stop_event = Event()
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())

    try:
        source = create_frame_source(
            camera_source=args.camera_source or DEFAULT_CAMERA_SOURCE,
            webcam_index=args.webcam_index,
            webcam_profile=args.camera_profile,
            webcam_fps=args.camera_fps,
            webcam_jpeg_quality=args.jpeg_quality,
            stale_after_seconds=args.stale_after_seconds,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    detector = MediaPipeDetector(
        pose_model_path=args.pose_model_path,
        hand_model_path=args.hand_model_path,
    )
    engine = default_engine(disabled_motions=args.disabled_motions)
    sequence = 0
    history: list[dict[str, object]] = []
    landmark_status: dict[str, object] | None = None

    if args.disabled_motions:
        print(
            "[motion] disabled=" + ",".join(args.disabled_motions),
            flush=True,
        )

    source.start()
    initial_camera_status = source.get_status()
    _write_state(
        args.state_path,
        status="running",
        history=history,
        camera_status=initial_camera_status,
        landmark_status=landmark_status,
    )
    last_status_signature = _print_camera_status(initial_camera_status)
    next_state_write = time.monotonic()
    try:
        while not stop_event.is_set():
            now = time.monotonic()
            if now >= next_state_write:
                camera_status = source.get_status()
                _write_state(
                    args.state_path,
                    status="running",
                    history=history,
                    camera_status=camera_status,
                    landmark_status=landmark_status,
                )
                status_signature = _print_camera_status(
                    camera_status,
                    last_status_signature,
                )
                last_status_signature = status_signature
                next_state_write = now + 0.5

            frame = source.read_latest(after_sequence=sequence)
            if frame is None:
                stop_event.wait(args.poll_interval)
                continue
            sequence = frame.sequence

            try:
                landmarks = detector.detect(frame)
            except ValueError:
                continue

            landmark_status = {
                "captured_at": landmarks.captured_at.isoformat(),
                "pose_points": len(landmarks.pose),
                "hand_count": len(landmarks.hands),
                "hand_points": sum(
                    len(hand.landmarks) for hand in landmarks.hands
                ),
            }
            try:
                _write_landmark_overlay(
                    args.overlay_path,
                    frame.data,
                    landmarks,
                )
            except Exception as exc:  # noqa: BLE001 - overlay must not stop recognition
                logger.warning("landmark overlay update failed: %s", exc)

            for detection in engine.update(landmarks):
                name = MOTION_NAMES.get(detection.motion_code, detection.motion_code)
                landmark_status["motion_code"] = detection.motion_code
                landmark_status["confidence"] = round(detection.confidence, 4)
                history.append(
                    {
                        "captured_at": landmarks.captured_at.isoformat(),
                        "name": name,
                        "motion_code": detection.motion_code,
                        "confidence": round(detection.confidence, 4),
                    }
                )
                _write_state(
                    args.state_path,
                    status="running",
                    history=history,
                    camera_status=source.get_status(),
                    landmark_status=landmark_status,
                )
                print(
                    f"{_format_timestamp(landmarks.captured_at)} | "
                    f"{detection.motion_code} | confidence={detection.confidence:.2f}",
                    flush=True,
                )
    finally:
        source.stop()
        detector.close()
        _write_state(
            args.state_path,
            status="stopped",
            history=history,
            camera_status=source.get_status(),
            landmark_status=landmark_status,
        )


if __name__ == "__main__":
    main()
