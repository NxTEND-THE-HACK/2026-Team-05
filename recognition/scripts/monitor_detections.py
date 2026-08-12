"""Run live recognition and print detections without delivering any events."""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from datetime import datetime
from pathlib import Path
from threading import Event

from gesture_recognition.gestures.registry import default_engine
from gesture_recognition.inference.mediapipe_detector import MediaPipeDetector
from gesture_recognition.stream.mjpeg import MjpegFrameSource, MjpegSourceStatus


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
    parser.add_argument("--camera-source", default="http://10.0.1.107/stream")
    parser.add_argument("--pose-model-path", default="models/pose_landmarker_full.task")
    parser.add_argument("--hand-model-path", default="models/hand_landmarker.task")
    parser.add_argument("--poll-interval", type=float, default=0.01)
    parser.add_argument("--stale-after-seconds", type=float, default=3.0)
    parser.add_argument(
        "--state-path",
        type=Path,
        default=Path("data/monitor_detections_live.json"),
    )
    return parser.parse_args()


def _format_timestamp(value: datetime) -> str:
    return value.astimezone().strftime("%H:%M:%S")


def _write_state(
    path: Path,
    *,
    status: str,
    history: list[dict[str, object]],
    camera_status: MjpegSourceStatus | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "appliance_delivery": False,
        "updated_at": datetime.now().astimezone().isoformat(),
        "camera": (
            None if camera_status is None else camera_status.to_payload()
        ),
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


def main() -> None:
    args = _parse_args()
    if args.poll_interval <= 0 or args.stale_after_seconds <= 0:
        raise SystemExit("poll and stale thresholds must be positive")

    stop_event = Event()
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())

    source = MjpegFrameSource(
        args.camera_source,
        stale_after_seconds=args.stale_after_seconds,
    )
    detector = MediaPipeDetector(
        pose_model_path=args.pose_model_path,
        hand_model_path=args.hand_model_path,
    )
    engine = default_engine()
    sequence = 0
    history: list[dict[str, object]] = []

    source.start()
    _write_state(
        args.state_path,
        status="running",
        history=history,
        camera_status=source.get_status(),
    )
    next_state_write = time.monotonic()
    try:
        while not stop_event.is_set():
            now = time.monotonic()
            if now >= next_state_write:
                _write_state(
                    args.state_path,
                    status="running",
                    history=history,
                    camera_status=source.get_status(),
                )
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

            for detection in engine.update(landmarks):
                name = MOTION_NAMES.get(detection.motion_code, detection.motion_code)
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
        )


if __name__ == "__main__":
    main()
