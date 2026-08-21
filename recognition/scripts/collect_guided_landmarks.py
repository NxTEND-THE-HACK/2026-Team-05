"""Collect labeled MediaPipe landmark segments with a guided camera protocol."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import time
from datetime import datetime
from pathlib import Path
from threading import Event

from gesture_recognition.domain.models import HandObservation, Landmark, LandmarkFrame
from gesture_recognition.inference.mediapipe_detector import MediaPipeDetector
from gesture_recognition.stream.factory import create_frame_source


logger = logging.getLogger("guided-landmark-collector")

MOTIONS = (
    (
        "POSE_RIGHT_HAND_UP",
        "右手上げ",
        "右手を上げて、その姿勢を保つ",
    ),
    (
        "POSE_LEFT_HAND_UP",
        "左手上げ",
        "左手を上げて、その姿勢を保つ",
    ),
    (
        "MOTION_SWIPE_RIGHT",
        "右スワイプ",
        "右スワイプを1回行う",
    ),
    (
        "MOTION_SWIPE_LEFT",
        "左スワイプ",
        "左スワイプを1回行う",
    ),
    (
        "MOTION_THUMBS_UP_MOVE_UP",
        "Goodから上",
        "Goodの形から上へ動かす",
    ),
    (
        "MOTION_THUMBS_DOWN_MOVE_DOWN",
        "Badから下",
        "Badの形から下へ動かす",
    ),
)


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


def _frame_to_record(
    frame: LandmarkFrame,
    *,
    label: str,
    segment_id: str,
    sequence: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "label": label,
        "segment_id": segment_id,
        "captured_at": frame.captured_at.isoformat(),
        "sequence": sequence,
        "pose": {
            name: _landmark_to_dict(landmark)
            for name, landmark in frame.pose.items()
        },
        "hands": [_hand_to_dict(hand) for hand in frame.hands],
    }


def _write_status(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for attempt in range(5):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.02 * (attempt + 1))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-source", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--status-path", type=Path)
    parser.add_argument("--samples-per-motion", type=int, default=10)
    parser.add_argument("--initial-wait-seconds", type=float, default=15.0)
    parser.add_argument("--neutral-seconds", type=float, default=1.2)
    parser.add_argument("--countdown-seconds", type=float, default=2.0)
    parser.add_argument("--target-seconds", type=float, default=2.5)
    parser.add_argument("--reset-seconds", type=float, default=1.5)
    parser.add_argument("--poll-interval", type=float, default=0.001)
    parser.add_argument(
        "--pose-model-path",
        default="models/pose_landmarker_full.task",
    )
    parser.add_argument(
        "--hand-model-path",
        default="models/hand_landmarker.task",
    )
    args = parser.parse_args()
    if args.samples_per_motion < 1:
        parser.error("--samples-per-motion must be positive")
    for name in (
        "initial_wait_seconds",
        "neutral_seconds",
        "countdown_seconds",
        "target_seconds",
        "reset_seconds",
        "poll_interval",
    ):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if args.status_path is None:
        args.status_path = args.output.with_suffix(".status.json")
    return args


def main() -> None:
    args = _parse_args()
    if args.output.exists():
        raise SystemExit(
            f"output already exists; choose a new path: {args.output}"
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    stop_event = Event()
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())

    source = create_frame_source(
        camera_source=args.camera_source,
        stale_after_seconds=3.0,
    )
    detector = MediaPipeDetector(
        pose_model_path=args.pose_model_path,
        hand_model_path=args.hand_model_path,
    )
    total_segments = len(MOTIONS) * args.samples_per_motion
    saved_records = 0
    sequence = 0
    current: dict[str, object] = {}
    last_status_write = 0.0

    def write_status(
        *,
        state: str,
        phase: str,
        phase_text: str,
        motion_index: int = 0,
        motion_name: str = "",
        sample_number: int = 0,
        phase_remaining: float = 0.0,
        segment_records: int = 0,
        message: str | None = None,
    ) -> None:
        nonlocal last_status_write
        now = time.monotonic()
        if now < last_status_write and phase == current.get("phase"):
            return
        last_status_write = now + 0.1
        current.update(
            {
                "phase": phase,
                "phase_text": phase_text,
                "motion_index": motion_index,
                "motion_total": len(MOTIONS),
                "motion_name": motion_name,
                "sample_number": sample_number,
                "samples_per_motion": args.samples_per_motion,
                "segment_index": (
                    (motion_index - 1) * args.samples_per_motion + sample_number
                    if motion_index and sample_number
                    else 0
                ),
                "segments_total": total_segments,
                "phase_remaining_seconds": round(max(0.0, phase_remaining), 1),
                "segment_records": segment_records,
                "saved_records": saved_records,
                "output": str(args.output),
                "message": message,
                "updated_at": datetime.now().astimezone().isoformat(),
            }
        )
        _write_status(args.status_path, {"state": state, **current})

    def run_phase(
        *,
        phase: str,
        phase_text: str,
        duration: float,
        label: str,
        motion_index: int,
        motion_name: str,
        sample_number: int,
        segment_id: str,
        output: object,
        capture: bool,
    ) -> int:
        nonlocal sequence, saved_records
        segment_records = 0
        started = time.monotonic()
        deadline = started + duration
        while not stop_event.is_set():
            now = time.monotonic()
            remaining = deadline - now
            if remaining <= 0:
                break
            write_status(
                state="running",
                phase=phase,
                phase_text=phase_text,
                motion_index=motion_index,
                motion_name=motion_name,
                sample_number=sample_number,
                phase_remaining=remaining,
                segment_records=segment_records,
            )
            frame = source.read_latest(after_sequence=sequence)
            if frame is None:
                stop_event.wait(args.poll_interval)
                continue
            sequence = frame.sequence
            try:
                landmarks = detector.detect(frame)
            except ValueError:
                continue
            if capture:
                output.write(
                    json.dumps(
                        _frame_to_record(
                            landmarks,
                            label=label,
                            segment_id=segment_id,
                            sequence=sequence,
                        ),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                output.flush()
                segment_records += 1
                saved_records += 1
        return segment_records

    try:
        source.start()
        with args.output.open("x", encoding="utf-8") as output:
            write_status(
                state="preparing",
                phase="initial_wait",
                phase_text="準備中。普段の姿勢で待ってください。",
                phase_remaining=args.initial_wait_seconds,
            )
            run_phase(
                phase="initial_wait",
                phase_text="準備中。普段の姿勢で待ってください。",
                duration=args.initial_wait_seconds,
                label="",
                motion_index=0,
                motion_name="",
                sample_number=0,
                segment_id="",
                output=output,
                capture=False,
            )

            for motion_index, (code, name, instruction) in enumerate(
                MOTIONS,
                start=1,
            ):
                for sample_number in range(1, args.samples_per_motion + 1):
                    segment_id = f"{code}_{sample_number:02d}"
                    run_phase(
                        phase="neutral",
                        phase_text="普段の姿勢に戻ってください。",
                        duration=args.neutral_seconds,
                        label=code,
                        motion_index=motion_index,
                        motion_name=name,
                        sample_number=sample_number,
                        segment_id=segment_id,
                        output=output,
                        capture=False,
                    )
                    run_phase(
                        phase="countdown",
                        phase_text=f"次は「{name}」です。準備してください。",
                        duration=args.countdown_seconds,
                        label=code,
                        motion_index=motion_index,
                        motion_name=name,
                        sample_number=sample_number,
                        segment_id=segment_id,
                        output=output,
                        capture=False,
                    )
                    records = run_phase(
                        phase="target",
                        phase_text=f"今すぐ {instruction}。",
                        duration=args.target_seconds,
                        label=code,
                        motion_index=motion_index,
                        motion_name=name,
                        sample_number=sample_number,
                        segment_id=segment_id,
                        output=output,
                        capture=True,
                    )
                    run_phase(
                        phase="reset",
                        phase_text="パーで手を前に出してください。",
                        duration=args.reset_seconds,
                        label=code,
                        motion_index=motion_index,
                        motion_name=name,
                        sample_number=sample_number,
                        segment_id=segment_id,
                        output=output,
                        capture=False,
                    )
                    logger.info(
                        "completed motion=%s sample=%s records=%s",
                        code,
                        sample_number,
                        records,
                    )

            write_status(
                state="completed",
                phase="completed",
                phase_text="収集完了です。",
                motion_index=len(MOTIONS),
                motion_name=MOTIONS[-1][1],
                sample_number=args.samples_per_motion,
                segment_records=0,
                message="全ポーズの収集が完了しました。",
            )
    finally:
        source.stop()
        detector.close()
        if stop_event.is_set():
            write_status(
                state="stopped",
                phase="stopped",
                phase_text="収集中断",
                message="収集を中断しました。保存済みデータは残っています。",
            )
        logger.info("collection stopped records=%s output=%s", saved_records, args.output)


if __name__ == "__main__":
    main()
