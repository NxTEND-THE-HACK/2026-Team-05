"""Build compact normalized motion templates from labeled landmark recordings.

The input recordings may contain the original MediaPipe output, but the
generated template file contains only normalized landmark coordinates. No
camera frames or raw landmark metadata are copied into the runtime asset.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from gesture_recognition.domain.models import HandObservation, Landmark, LandmarkFrame
from gesture_recognition.gestures.catalog import MOTION_CODES
from gesture_recognition.gestures.temporal import (
    ExponentialMovingAverage,
    LandmarkNormalizer,
    MotionTemplate,
    TemplateSet,
)


RECORDING_FILES = {
    "POSE_RIGHT_HAND_UP": "pose_right_hand_up_20260806_retake10_raised_segments_10.jsonl",
    "POSE_LEFT_HAND_UP": "pose_left_hand_up_20260806_retake10_raised_segments_10.jsonl",
    "MOTION_SWIPE_RIGHT": "motion_swipe_right_20260806_retake10_segments_10.jsonl",
    "MOTION_SWIPE_LEFT": "motion_swipe_left_20260806_retake10_segments_10.jsonl",
    "MOTION_FINGER_SNAP": "motion_finger_snap_20260806_retake10_segments_10.jsonl",
    "MOTION_THUMBS_UP_MOVE_UP": "motion_thumbs_up_move_up_20260806_retake10_segments_10.jsonl",
    "MOTION_THUMBS_DOWN_MOVE_DOWN": "motion_thumbs_down_move_down_20260806_retake10_segments_10.jsonl",
    "MOTION_CLAP": "motion_clap_20260806_retake10_segments_10.jsonl",
    "MOTION_OPEN_TO_FIST_DOWN": "motion_open_to_fist_down_20260806_retake10_segments_10.jsonl",
    "MOTION_HAND_ROTATE_RIGHT": "motion_hand_rotate_right_20260806_retake10_segments_10.jsonl",
    "MOTION_HAND_ROTATE_LEFT": "motion_hand_rotate_left_20260806_retake10_segments_10.jsonl",
}


def _landmark(value: dict[str, Any]) -> Landmark:
    visibility = value.get("visibility")
    return Landmark(
        float(value["x"]),
        float(value["y"]),
        float(value.get("z", 0.0)),
        None if visibility is None else float(visibility),
    )


def _frame(record: dict[str, Any]) -> LandmarkFrame:
    return LandmarkFrame(
        datetime.fromisoformat(str(record["captured_at"])),
        {
            str(name): _landmark(value)
            for name, value in record.get("pose", {}).items()
        },
        tuple(
            HandObservation(
                str(hand.get("handedness", "Unknown")),
                tuple(_landmark(value) for value in hand.get("landmarks", [])),
            )
            for hand in record.get("hands", [])
        ),
    )


def _read_segments(path: Path) -> dict[str, list[LandmarkFrame]]:
    segments: dict[str, list[LandmarkFrame]] = defaultdict(list)
    with path.open(encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            segment_id = record.get("segment_id")
            key = "full" if segment_id is None else str(segment_id)
            segments[key].append(_frame(record))
    return dict(segments)


def _select_segment_ids(segment_ids: list[str], samples_per_motion: int) -> list[str]:
    if len(segment_ids) <= samples_per_motion:
        return segment_ids
    positions = {
        round(index * (len(segment_ids) - 1) / (samples_per_motion - 1))
        for index in range(samples_per_motion)
    }
    return [segment_ids[position] for position in sorted(positions)]


def _parse_thresholds(values: list[str], default: float) -> dict[str, float]:
    thresholds = {motion_code: default for motion_code in MOTION_CODES}
    for value in values:
        try:
            motion_code, raw_threshold = value.split("=", 1)
            threshold = float(raw_threshold)
        except ValueError as exc:
            raise SystemExit("--threshold must use MOTION_CODE=VALUE") from exc
        if motion_code not in thresholds:
            raise SystemExit(f"unsupported motion code in --threshold: {motion_code}")
        if threshold <= 0:
            raise SystemExit("threshold values must be positive")
        thresholds[motion_code] = threshold
    return thresholds


def build_templates(
    data_dir: Path,
    *,
    samples_per_motion: int = 5,
    visibility_threshold: float = 0.5,
    ema_alpha: float = 0.4,
    thresholds: dict[str, float] | None = None,
) -> TemplateSet:
    if samples_per_motion < 1:
        raise ValueError("samples_per_motion must be positive")
    normalizer = LandmarkNormalizer(visibility_threshold=visibility_threshold)
    smoother = ExponentialMovingAverage(ema_alpha)
    templates: list[MotionTemplate] = []

    for motion_code in MOTION_CODES:
        path = data_dir / RECORDING_FILES[motion_code]
        if not path.is_file():
            raise FileNotFoundError(f"recording not found: {path}")
        segments = _read_segments(path)
        segment_ids = _select_segment_ids(sorted(segments), samples_per_motion)
        for segment_id in segment_ids:
            smoother.reset()
            normalized_frames = []
            for frame in segments[segment_id]:
                normalized = normalizer.normalize(frame)
                if normalized is None:
                    smoother.reset()
                    continue
                normalized_frames.append(smoother.update(normalized).points)
            if not normalized_frames:
                raise ValueError(
                    f"recording segment has no usable shoulder-anchored frames: "
                    f"{path.name} segment={segment_id}"
                )
            templates.append(
                MotionTemplate(
                    motion_code,
                    f"sample_{segment_id}",
                    tuple(normalized_frames),
                )
            )

    return TemplateSet(
        tuple(templates),
        thresholds or {
            motion_code: 0.35 for motion_code in MOTION_CODES
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, default=Path("data"), help="JSONL recording directory"
    )
    parser.add_argument(
        "--output", type=Path, default=Path("models/motion_samples.json")
    )
    parser.add_argument("--samples-per-motion", type=int, default=5)
    parser.add_argument("--visibility-threshold", type=float, default=0.5)
    parser.add_argument("--ema-alpha", type=float, default=0.4)
    parser.add_argument("--default-threshold", type=float, default=0.35)
    parser.add_argument(
        "--threshold",
        action="append",
        default=[],
        metavar="MOTION_CODE=VALUE",
        help="Override one motion's DTW UNKNOWN threshold; repeatable",
    )
    args = parser.parse_args()
    if not 0.0 <= args.visibility_threshold <= 1.0:
        raise SystemExit("--visibility-threshold must be between 0 and 1")
    if not 0.0 < args.ema_alpha <= 1.0:
        raise SystemExit("--ema-alpha must be greater than 0 and at most 1")
    if args.default_threshold <= 0:
        raise SystemExit("--default-threshold must be positive")

    template_set = build_templates(
        args.data_dir,
        samples_per_motion=args.samples_per_motion,
        visibility_threshold=args.visibility_threshold,
        ema_alpha=args.ema_alpha,
        thresholds=_parse_thresholds(args.threshold, args.default_threshold),
    )
    template_set.write_json(args.output)
    print(
        f"wrote {len(template_set.templates)} templates for "
        f"{len(MOTION_CODES)} motions to {args.output}"
    )


if __name__ == "__main__":
    main()
