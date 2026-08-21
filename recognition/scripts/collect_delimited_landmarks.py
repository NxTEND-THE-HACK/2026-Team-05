"""Collect MediaPipe landmarks using a palm pose as a trial delimiter."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import time
from datetime import datetime
from math import atan2, degrees
from pathlib import Path
from threading import Event

from gesture_recognition.domain.models import HandObservation, Landmark, LandmarkFrame
from gesture_recognition.inference.mediapipe_detector import MediaPipeDetector
from gesture_recognition.stream.factory import create_frame_source


logger = logging.getLogger("delimited-landmark-collector")

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


def _angle(first: Landmark, middle: Landmark, last: Landmark) -> float:
    first_angle = atan2(first.y - middle.y, first.x - middle.x)
    last_angle = atan2(last.y - middle.y, last.x - middle.x)
    value = abs(degrees(first_angle - last_angle))
    return 360.0 - value if value > 180.0 else value


def _is_open_palm(hand: HandObservation) -> bool:
    """Return whether a hand has all fingers extended."""

    if len(hand.landmarks) < 21:
        return False
    return (
        _angle(hand.point(2), hand.point(3), hand.point(4)) >= 105.0
        and all(
            _angle(hand.point(mcp), hand.point(pip), hand.point(tip)) >= 140.0
            for mcp, pip, tip in (
                (5, 6, 8),
                (9, 10, 12),
                (13, 14, 16),
                (17, 18, 20),
            )
        )
    )


def _has_open_palm(frame: LandmarkFrame) -> bool:
    return any(_is_open_palm(hand) for hand in frame.hands)


class PalmGate:
    """Turn a continuously held palm into held/released events."""

    def __init__(self, hold_seconds: float, release_seconds: float) -> None:
        self.hold_seconds = hold_seconds
        self.release_seconds = release_seconds
        self._started_at: float | None = None
        self._absent_since: float | None = None
        self._triggered = False

    def reset(self) -> None:
        self._started_at = None
        self._absent_since = None
        self._triggered = False

    def update(self, *, is_palm: bool, now: float) -> str | None:
        if is_palm:
            self._absent_since = None
            if self._started_at is None:
                self._started_at = now
            if (
                not self._triggered
                and now - self._started_at >= self.hold_seconds
            ):
                self._triggered = True
                return "held"
            return None

        if not self._triggered and self._started_at is None:
            return None
        if self._absent_since is None:
            self._absent_since = now
        if now - self._absent_since < self.release_seconds:
            return None

        was_triggered = self._triggered
        self.reset()
        return "released" if was_triggered else None


def _beep(kind: str) -> None:
    """Give optional audio cues without making audio a collection dependency."""

    try:
        import winsound

        if kind == "sample":
            winsound.Beep(880, 120)
        elif kind == "motion":
            winsound.Beep(880, 120)
            winsound.Beep(660, 120)
            winsound.Beep(880, 120)
        elif kind == "complete":
            winsound.Beep(880, 180)
            winsound.Beep(1047, 240)
    except (ImportError, RuntimeError):
        pass


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-source", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--status-path", type=Path)
    parser.add_argument("--samples-per-motion", type=int, default=10)
    parser.add_argument("--initial-wait-seconds", type=float, default=10.0)
    parser.add_argument("--neutral-seconds", type=float, default=1.2)
    parser.add_argument("--target-seconds", type=float, default=2.5)
    parser.add_argument("--palm-hold-seconds", type=float, default=0.8)
    parser.add_argument("--palm-release-seconds", type=float, default=0.25)
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
        "target_seconds",
        "palm_hold_seconds",
        "palm_release_seconds",
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
    state = "preparing"
    phase = "initial_wait"
    completed = False
    motion_index = 1
    sample_number = 1
    segment_records = 0
    phase_deadline = 0.0
    last_status_write = 0.0
    last_status_phase = ""

    def write_status(
        *,
        current_state: str,
        current_phase: str,
        phase_text: str,
        phase_remaining: float = 0.0,
        message: str | None = None,
        force: bool = False,
    ) -> None:
        nonlocal last_status_write, last_status_phase
        now = time.monotonic()
        if (
            not force
            and current_phase == last_status_phase
            and now - last_status_write < 0.2
        ):
            return
        last_status_write = now
        last_status_phase = current_phase
        motion_code, motion_name, instruction = MOTIONS[motion_index - 1]
        _write_status(
            args.status_path,
            {
                "state": current_state,
                "phase": current_phase,
                "phase_text": phase_text,
                "motion_index": motion_index,
                "motion_total": len(MOTIONS),
                "motion_code": motion_code,
                "motion_name": motion_name,
                "instruction": instruction,
                "sample_number": sample_number,
                "samples_per_motion": args.samples_per_motion,
                "segment_index": (
                    (motion_index - 1) * args.samples_per_motion + sample_number
                ),
                "segments_total": total_segments,
                "phase_remaining_seconds": round(
                    max(0.0, phase_remaining), 1
                ),
                "segment_records": segment_records,
                "saved_records": saved_records,
                "output": str(args.output),
                "message": message,
                "updated_at": datetime.now().astimezone().isoformat(),
            },
        )

    palm_gate = PalmGate(
        hold_seconds=args.palm_hold_seconds,
        release_seconds=args.palm_release_seconds,
    )

    try:
        source.start()
        with args.output.open("x", encoding="utf-8") as output:
            preparation_deadline = time.monotonic() + args.initial_wait_seconds
            write_status(
                current_state="preparing",
                current_phase="initial_wait",
                phase_text="準備中です。まもなく最初のパーを検出します。",
                phase_remaining=args.initial_wait_seconds,
                force=True,
            )

            while not stop_event.is_set() and not completed:
                now = time.monotonic()
                frame = source.read_latest(after_sequence=sequence)
                if frame is None:
                    if phase == "initial_wait":
                        write_status(
                            current_state="preparing",
                            current_phase=phase,
                            phase_text="準備中です。まもなく最初のパーを検出します。",
                            phase_remaining=preparation_deadline - now,
                        )
                    stop_event.wait(args.poll_interval)
                    continue

                sequence = frame.sequence
                try:
                    landmarks = detector.detect(frame)
                except ValueError as exc:
                    logger.warning("skipping invalid frame: %s", exc)
                    continue

                if phase == "initial_wait":
                    palm_gate.reset()
                    if now >= preparation_deadline:
                        phase = "waiting_for_first_palm"
                        state = "running"
                        write_status(
                            current_state=state,
                            current_phase=phase,
                            phase_text="最初にパーを前に出して約1秒保持してください。",
                            force=True,
                        )
                    else:
                        write_status(
                            current_state="preparing",
                            current_phase=phase,
                            phase_text="準備中です。まもなく最初のパーを検出します。",
                            phase_remaining=preparation_deadline - now,
                        )
                    continue

                is_palm = _has_open_palm(landmarks)
                palm_event = palm_gate.update(is_palm=is_palm, now=now)

                if phase == "waiting_for_first_palm":
                    write_status(
                        current_state=state,
                        current_phase=phase,
                        phase_text="最初にパーを前に出して約1秒保持してください。",
                    )
                    if palm_event == "held":
                        phase = "waiting_for_first_release"
                        write_status(
                            current_state=state,
                            current_phase=phase,
                            phase_text="パーを下ろして普段の姿勢に戻ってください。",
                            force=True,
                        )
                    continue

                if phase == "waiting_for_first_release":
                    write_status(
                        current_state=state,
                        current_phase=phase,
                        phase_text="パーを下ろして普段の姿勢に戻ってください。",
                    )
                    if palm_event == "released":
                        phase = "neutral"
                        phase_deadline = now + args.neutral_seconds
                        write_status(
                            current_state=state,
                            current_phase=phase,
                            phase_text="普段の姿勢で待ってください。",
                            phase_remaining=args.neutral_seconds,
                            force=True,
                        )
                    continue

                if phase == "neutral":
                    if now >= phase_deadline:
                        phase = "target"
                        phase_deadline = now + args.target_seconds
                        segment_records = 0
                        palm_gate.reset()
                        _beep("sample")
                        write_status(
                            current_state=state,
                            current_phase=phase,
                            phase_text=(
                                f"{MOTIONS[motion_index - 1][2]}。"
                                "今の動作を行ってください。"
                            ),
                            phase_remaining=args.target_seconds,
                            force=True,
                        )
                    else:
                        write_status(
                            current_state=state,
                            current_phase=phase,
                            phase_text="普段の姿勢で待ってください。",
                            phase_remaining=phase_deadline - now,
                        )
                    continue

                if phase == "target":
                    if now >= phase_deadline:
                        phase = "waiting_for_next_palm"
                        palm_gate.reset()
                        write_status(
                            current_state=state,
                            current_phase=phase,
                            phase_text="動作を終え、パーを前に出して約1秒保持してください。",
                            force=True,
                        )
                        continue

                    code = MOTIONS[motion_index - 1][0]
                    segment_id = f"{code}_{sample_number:02d}"
                    output.write(
                        json.dumps(
                            _frame_to_record(
                                landmarks,
                                label=code,
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
                    write_status(
                        current_state=state,
                        current_phase=phase,
                        phase_text=(
                            f"{MOTIONS[motion_index - 1][2]}。"
                            "今の動作を行ってください。"
                        ),
                        phase_remaining=phase_deadline - now,
                    )
                    continue

                if phase == "waiting_for_next_palm":
                    write_status(
                        current_state=state,
                        current_phase=phase,
                        phase_text="動作を終え、パーを前に出して約1秒保持してください。",
                    )
                    if palm_event == "held":
                        logger.info(
                            "completed motion=%s sample=%s records=%s",
                            MOTIONS[motion_index - 1][0],
                            sample_number,
                            segment_records,
                        )
                        if (
                            motion_index == len(MOTIONS)
                            and sample_number == args.samples_per_motion
                        ):
                            completed = True
                            _beep("complete")
                            write_status(
                                current_state="completed",
                                current_phase="completed",
                                phase_text="全ポーズの計測が完了しました。",
                                message="全ポーズの計測が完了しました。",
                                force=True,
                            )
                            continue

                        if sample_number == args.samples_per_motion:
                            motion_index += 1
                            sample_number = 1
                            _beep("motion")
                        else:
                            sample_number += 1
                        phase = "waiting_for_next_release"
                        write_status(
                            current_state=state,
                            current_phase=phase,
                            phase_text="パーを下ろして普段の姿勢に戻ってください。",
                            force=True,
                        )
                    continue

                if phase == "waiting_for_next_release":
                    write_status(
                        current_state=state,
                        current_phase=phase,
                        phase_text="パーを下ろして普段の姿勢に戻ってください。",
                    )
                    if palm_event == "released":
                        phase = "neutral"
                        phase_deadline = now + args.neutral_seconds
                        write_status(
                            current_state=state,
                            current_phase=phase,
                            phase_text="普段の姿勢で待ってください。",
                            phase_remaining=args.neutral_seconds,
                            force=True,
                        )
                    continue

            if stop_event.is_set() and not completed:
                write_status(
                    current_state="stopped",
                    current_phase="stopped",
                    phase_text="計測を停止しました。",
                    message="停止時点までの対象動作フレームを保存しました。",
                    force=True,
                )
    finally:
        source.stop()
        detector.close()
        logger.info(
            "collection stopped records=%s output=%s",
            saved_records,
            args.output,
        )


if __name__ == "__main__":
    main()
