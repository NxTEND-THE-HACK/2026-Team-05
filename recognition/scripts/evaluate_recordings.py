"""Replay the existing landmark recordings against the live gesture rules.

This is intentionally an event-level evaluator. Frame counts alone are
misleading because one gesture contributes many consecutive frames. Files
with ``segment_id`` are evaluated one segment at a time; unsegmented files
are reported as exploratory recordings rather than accuracy benchmarks.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from gesture_recognition.domain.models import HandObservation, Landmark, LandmarkFrame
from gesture_recognition.gestures.base import GestureRule
from gesture_recognition.gestures.engine import GestureEngine
from gesture_recognition.gestures.rules import (
    ClapRule,
    FingerSnapRule,
    HandRotateLeftRule,
    HandRotateRightRule,
    LeftHandRaisedRule,
    OpenToFistDownRule,
    RightHandRaisedRule,
    SwipeLeftRule,
    SwipeRightRule,
    ThumbsDownMoveDownRule,
    ThumbsUpMoveUpRule,
)


RuleFactory = Callable[[], GestureRule]


@dataclass(frozen=True, slots=True)
class RecordingSpec:
    filename: str
    motion_code: str
    factory: RuleFactory


DEFAULT_RECORDINGS = (
    RecordingSpec(
        "pose_right_hand_up_20260806_retake10_raised_segments_10.jsonl",
        "POSE_RIGHT_HAND_UP",
        RightHandRaisedRule,
    ),
    RecordingSpec(
        "pose_left_hand_up_20260806_retake10_raised_segments_10.jsonl",
        "POSE_LEFT_HAND_UP",
        LeftHandRaisedRule,
    ),
    RecordingSpec(
        "motion_swipe_left_20260806_retake10_segments_10.jsonl",
        "MOTION_SWIPE_LEFT",
        SwipeLeftRule,
    ),
    RecordingSpec(
        "motion_swipe_right_20260806_retake10_segments_10.jsonl",
        "MOTION_SWIPE_RIGHT",
        SwipeRightRule,
    ),
    RecordingSpec(
        "motion_finger_snap_20260806_retake10_segments_10.jsonl",
        "MOTION_FINGER_SNAP",
        FingerSnapRule,
    ),
    RecordingSpec(
        "motion_thumbs_up_move_up_20260806_retake10_segments_10.jsonl",
        "MOTION_THUMBS_UP_MOVE_UP",
        ThumbsUpMoveUpRule,
    ),
    RecordingSpec(
        "motion_thumbs_down_move_down_20260806_retake10_segments_10.jsonl",
        "MOTION_THUMBS_DOWN_MOVE_DOWN",
        ThumbsDownMoveDownRule,
    ),
    RecordingSpec(
        "motion_clap_20260806_retake10_segments_10.jsonl",
        "MOTION_CLAP",
        ClapRule,
    ),
    RecordingSpec(
        "motion_open_to_fist_down_20260806_retake10_segments_10.jsonl",
        "MOTION_OPEN_TO_FIST_DOWN",
        OpenToFistDownRule,
    ),
    RecordingSpec(
        "motion_hand_rotate_right_20260806_retake10_segments_10.jsonl",
        "MOTION_HAND_ROTATE_RIGHT",
        HandRotateRightRule,
    ),
    RecordingSpec(
        "motion_hand_rotate_left_20260806_retake10_segments_10.jsonl",
        "MOTION_HAND_ROTATE_LEFT",
        HandRotateLeftRule,
    ),
)


def _landmark(value: dict[str, object]) -> Landmark:
    return Landmark(
        float(value["x"]),
        float(value["y"]),
        float(value.get("z", 0.0)),
        None if value.get("visibility") is None else float(value["visibility"]),
    )


def _frame(record: dict[str, object]) -> LandmarkFrame:
    pose = record.get("pose", {})
    hands = record.get("hands", [])
    return LandmarkFrame(
        datetime.fromisoformat(str(record["captured_at"])),
        {
            str(name): _landmark(value)
            for name, value in pose.items()
        },
        tuple(
            HandObservation(
                str(hand.get("handedness", "Unknown")),
                tuple(_landmark(value) for value in hand.get("landmarks", [])),
            )
            for hand in hands
        ),
    )


def _read_records(path: Path) -> list[tuple[dict[str, object], LandmarkFrame]]:
    records: list[tuple[dict[str, object], LandmarkFrame]] = []
    with path.open(encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            records.append((record, _frame(record)))
    return records


def _evaluate_segment(
    records: list[tuple[dict[str, object], LandmarkFrame]],
    factory: RuleFactory,
) -> int:
    rule = factory()
    return sum(rule.update(frame) is not None for _, frame in records)


def _segment_records(
    records: list[tuple[dict[str, object], LandmarkFrame]],
) -> dict[object, list[tuple[dict[str, object], LandmarkFrame]]]:
    segment_records: dict[object, list[tuple[dict[str, object], LandmarkFrame]]] = defaultdict(list)
    for record, frame in records:
        segment_records[record.get("segment_id")].append((record, frame))
    return segment_records


def evaluate(path: Path, spec: RecordingSpec) -> dict[str, object]:
    records = _read_records(path)
    segment_records = _segment_records(records)

    has_segments = set(segment_records) != {None}
    segment_hits: dict[str, int] = {}
    if has_segments:
        for segment_id, items in sorted(segment_records.items(), key=lambda pair: str(pair[0])):
            if segment_id is not None:
                segment_hits[str(segment_id)] = _evaluate_segment(items, spec.factory)
        detections = sum(segment_hits.values())
    else:
        engine = GestureEngine((spec.factory(),))
        detections = sum(
            len(engine.update(frame))
            for _, frame in records
        )

    labels = Counter(str(record.get("label", "")) for record, _ in records)
    pose_frames = sum(bool(record.get("pose")) for record, _ in records)
    hand_frames = sum(bool(record.get("hands")) for record, _ in records)
    expected_segments = len(segment_hits) if has_segments else None
    return {
        "file": path.name,
        "motion_code": spec.motion_code,
        "frames": len(records),
        "pose_coverage": round(pose_frames / max(len(records), 1), 4),
        "hand_coverage": round(hand_frames / max(len(records), 1), 4),
        "labels": dict(labels),
        "segmented": has_segments,
        "expected_segments": expected_segments,
        "detections": detections,
        "segments_with_one_detection": (
            sum(value == 1 for value in segment_hits.values())
            if has_segments
            else None
        ),
        "segments_with_no_detection": (
            sum(value == 0 for value in segment_hits.values())
            if has_segments
            else None
        ),
        "segments_with_duplicate_detection": (
            sum(value > 1 for value in segment_hits.values())
            if has_segments
            else None
        ),
        "segment_hits": segment_hits if has_segments else None,
    }


def cross_check(
    data_dir: Path,
    specs: tuple[RecordingSpec, ...] = DEFAULT_RECORDINGS,
) -> dict[str, object]:
    """Replay each segmented recording through every registered rule.

    Counts are emitted detections, matching the default evaluator's event-level
    ``detections`` field. A rule's detections on its matching recording are
    positive counts; detections on another recording are off-diagonal false
    positives.
    """

    rule_codes = [spec.motion_code for spec in specs]
    positive_counts = {motion_code: 0 for motion_code in rule_codes}
    false_positive_counts = {
        motion_code: Counter()
        for motion_code in rule_codes
    }
    segmented_recordings: list[dict[str, object]] = []

    for recording_spec in specs:
        path = data_dir / recording_spec.filename
        if not path.exists():
            continue

        segment_records = _segment_records(_read_records(path))
        if set(segment_records) == {None}:
            continue

        counts_by_rule: dict[str, int] = {}
        for rule_spec in specs:
            counts_by_rule[rule_spec.motion_code] = sum(
                _evaluate_segment(items, rule_spec.factory)
                for segment_id, items in sorted(
                    segment_records.items(), key=lambda pair: str(pair[0])
                )
                if segment_id is not None
            )

        segmented_recordings.append(
            {
                "file": path.name,
                "motion_code": recording_spec.motion_code,
                "segments": sum(
                    segment_id is not None for segment_id in segment_records
                ),
                "detections_by_rule": counts_by_rule,
            }
        )
        for rule_code, count in counts_by_rule.items():
            if rule_code == recording_spec.motion_code:
                positive_counts[rule_code] += count
            elif count:
                false_positive_counts[rule_code][recording_spec.motion_code] += count

    return {
        "count_unit": "detections",
        "segmented_recordings": segmented_recordings,
        "rules": [
            {
                "motion_code": rule_code,
                "positive_count": positive_counts[rule_code],
                "off_diagonal_false_positives": dict(
                    false_positive_counts[rule_code]
                ),
                "off_diagonal_total": sum(false_positive_counts[rule_code].values()),
            }
            for rule_code in rule_codes
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Directory containing the existing JSONL recordings.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    parser.add_argument(
        "--cross-check",
        action="store_true",
        help="Replay segmented recordings through every registered rule.",
    )
    args = parser.parse_args()

    report = {
        "schema_version": 1,
        "reset_after_gap_seconds": 0.75,
        "recordings": [],
    }
    for spec in DEFAULT_RECORDINGS:
        path = args.data_dir / spec.filename
        if not path.exists():
            continue
        report["recordings"].append(evaluate(path, spec))
    if args.cross_check:
        report["cross_check"] = cross_check(args.data_dir)

    body = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body, encoding="utf-8")
    else:
        print(body, end="")


if __name__ == "__main__":
    main()
