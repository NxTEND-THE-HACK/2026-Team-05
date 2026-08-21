"""Split one raw MediaPipe JSONL recording at forward open-palm markers."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from math import atan2, degrees
from pathlib import Path
from typing import Any

from gesture_recognition.domain.models import HandObservation, Landmark


MOTIONS = (
    ("POSE_RIGHT_HAND_UP", "右手上げ"),
    ("POSE_LEFT_HAND_UP", "左手上げ"),
    ("MOTION_SWIPE_RIGHT", "右スワイプ"),
    ("MOTION_SWIPE_LEFT", "左スワイプ"),
    ("MOTION_THUMBS_UP_MOVE_UP", "Goodから上"),
    ("MOTION_THUMBS_DOWN_MOVE_DOWN", "Badから下"),
    ("MOTION_FINGER_SNAP", "指パッチン"),
)


@dataclass(frozen=True, slots=True)
class MarkerRun:
    start: int
    end: int

    @property
    def frame_count(self) -> int:
        return self.end - self.start + 1


def _angle(first: Landmark, middle: Landmark, last: Landmark) -> float:
    first_angle = atan2(first.y - middle.y, first.x - middle.x)
    last_angle = atan2(last.y - middle.y, last.x - middle.x)
    value = abs(degrees(first_angle - last_angle))
    return 360.0 - value if value > 180.0 else value


def _is_open_palm(hand: HandObservation) -> bool:
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--samples-per-motion", type=int, default=10)
    parser.add_argument("--palm-area-threshold", type=float, default=0.01)
    parser.add_argument("--palm-min-wrist-x", type=float, default=0.20)
    parser.add_argument("--palm-max-wrist-x", type=float, default=0.80)
    parser.add_argument("--palm-min-wrist-y", type=float, default=0.25)
    parser.add_argument("--palm-max-wrist-y", type=float, default=0.75)
    parser.add_argument("--min-marker-frames", type=int, default=5)
    parser.add_argument("--merge-gap-frames", type=int, default=2)
    args = parser.parse_args()
    if args.samples_per_motion < 1:
        parser.error("--samples-per-motion must be positive")
    if args.palm_area_threshold <= 0:
        parser.error("--palm-area-threshold must be positive")
    if args.min_marker_frames < 1:
        parser.error("--min-marker-frames must be positive")
    if args.merge_gap_frames < 0:
        parser.error("--merge-gap-frames must not be negative")
    return args


def _hand(record: dict[str, Any]) -> HandObservation:
    return HandObservation(
        str(record.get("handedness", "Unknown")),
        tuple(
            Landmark(
                float(value["x"]),
                float(value["y"]),
                float(value.get("z", 0.0)),
                None
                if value.get("visibility") is None
                else float(value["visibility"]),
            )
            for value in record.get("landmarks", [])
        ),
    )


def _hand_area(hand: HandObservation) -> float:
    if len(hand.landmarks) < 21:
        return 0.0
    xs = [item.x for item in hand.landmarks]
    ys = [item.y for item in hand.landmarks]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def _is_forward_palm_marker(
    record: dict[str, Any],
    *,
    area_threshold: float,
    min_wrist_x: float,
    max_wrist_x: float,
    min_wrist_y: float,
    max_wrist_y: float,
) -> bool:
    for raw_hand in record.get("hands", []):
        hand = _hand(raw_hand)
        if len(hand.landmarks) < 21 or not _is_open_palm(hand):
            continue
        wrist = hand.point(0)
        if not min_wrist_x <= wrist.x <= max_wrist_x:
            continue
        if not min_wrist_y <= wrist.y <= max_wrist_y:
            continue
        if _hand_area(hand) >= area_threshold:
            return True
    return False


def _marker_runs(
    flags: list[bool],
    *,
    minimum_frames: int,
    merge_gap_frames: int,
) -> list[MarkerRun]:
    raw_runs: list[MarkerRun] = []
    start: int | None = None
    for index, flag in enumerate(flags):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            raw_runs.append(MarkerRun(start, index - 1))
            start = None
    if start is not None:
        raw_runs.append(MarkerRun(start, len(flags) - 1))

    merged: list[MarkerRun] = []
    for run in raw_runs:
        if (
            merged
            and run.start - merged[-1].end - 1 <= merge_gap_frames
        ):
            previous = merged[-1]
            merged[-1] = MarkerRun(previous.start, run.end)
        else:
            merged.append(run)
    return [run for run in merged if run.frame_count >= minimum_frames]


def _duration(records: list[dict[str, Any]]) -> float:
    if len(records) < 2:
        return 0.0
    first = datetime.fromisoformat(str(records[0]["captured_at"]))
    last = datetime.fromisoformat(str(records[-1]["captured_at"]))
    return round((last - first).total_seconds(), 3)


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )


def _motion_for_segment(
    index: int,
    *,
    samples_per_motion: int,
) -> tuple[str, str, int] | None:
    motion_index = index // samples_per_motion
    if motion_index >= len(MOTIONS):
        return None
    sample_number = index % samples_per_motion + 1
    code, name = MOTIONS[motion_index]
    return code, name, sample_number


def main() -> None:
    args = _parse_args()
    if not args.input.is_file():
        raise SystemExit(f"input not found: {args.input}")
    if args.output_dir.exists():
        raise SystemExit(
            f"output directory already exists; choose a new path: "
            f"{args.output_dir}"
        )

    records: list[dict[str, Any]] = []
    with args.input.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            record["_raw_line"] = line_number
            records.append(record)
    if not records:
        raise SystemExit("input contains no records")

    flags = [
        _is_forward_palm_marker(
            record,
            area_threshold=args.palm_area_threshold,
            min_wrist_x=args.palm_min_wrist_x,
            max_wrist_x=args.palm_max_wrist_x,
            min_wrist_y=args.palm_min_wrist_y,
            max_wrist_y=args.palm_max_wrist_y,
        )
        for record in records
    ]
    markers = _marker_runs(
        flags,
        minimum_frames=args.min_marker_frames,
        merge_gap_frames=args.merge_gap_frames,
    )
    expected_segments = len(MOTIONS) * args.samples_per_motion
    segments: list[dict[str, Any]] = []
    for index, (before, after) in enumerate(zip(markers, markers[1:])):
        start = before.end + 1
        end = after.start - 1
        if end < start:
            continue
        motion = _motion_for_segment(
            index,
            samples_per_motion=args.samples_per_motion,
        )
        if motion is None:
            code, name, sample_number = "UNASSIGNED", "未割り当て", index + 1
        else:
            code, name, sample_number = motion
        segment_id = f"{code}_{sample_number:02d}"
        segment_records = []
        for record in records[start : end + 1]:
            output_record = {
                key: value
                for key, value in record.items()
                if key != "_raw_line"
            }
            output_record["source_label"] = output_record.get("label")
            output_record["label"] = code
            output_record["segment_id"] = segment_id
            segment_records.append(output_record)
        segments.append(
            {
                "index": index + 1,
                "code": code,
                "name": name,
                "sample_number": sample_number,
                "segment_id": segment_id,
                "start_raw_line": records[start]["_raw_line"],
                "end_raw_line": records[end]["_raw_line"],
                "frames": len(segment_records),
                "duration_seconds": _duration(segment_records),
                "records": segment_records,
            }
        )

    args.output_dir.mkdir(parents=True)
    all_records: list[dict[str, Any]] = []
    for segment in segments:
        code = str(segment["code"])
        sample_number = int(segment["sample_number"])
        segment_dir = args.output_dir / code
        segment_dir.mkdir(exist_ok=True)
        filename = f"sample_{sample_number:02d}.jsonl"
        path = segment_dir / filename
        segment["file"] = str(path.relative_to(args.output_dir))
        segment_records = segment.pop("records")
        _write_jsonl(path, segment_records)
        all_records.extend(segment_records)

    all_path = args.output_dir / "all_segments.jsonl"
    _write_jsonl(all_path, all_records)

    counts = {code: 0 for code, _ in MOTIONS}
    frame_counts = {code: 0 for code, _ in MOTIONS}
    for segment in segments:
        code = str(segment["code"])
        if code in counts:
            counts[code] += 1
            frame_counts[code] += int(segment["frames"])
    verification = {
        "expected_segments": expected_segments,
        "marker_runs": len(markers),
        "expected_marker_runs": expected_segments + 1,
        "segments_created": len(segments),
        "all_motion_counts_are_expected": (
            len(markers) == expected_segments + 1
            and len(segments) == expected_segments
            and all(value == args.samples_per_motion for value in counts.values())
        ),
        "counts": counts,
        "frame_counts": frame_counts,
    }
    manifest = {
        "schema_version": 1,
        "input": str(args.input),
        "output_dir": str(args.output_dir),
        "split_rule": {
            "marker": "open palm with a forward-sized, centered hand",
            "palm_area_threshold": args.palm_area_threshold,
            "wrist_x_range": [args.palm_min_wrist_x, args.palm_max_wrist_x],
            "wrist_y_range": [args.palm_min_wrist_y, args.palm_max_wrist_y],
            "min_marker_frames": args.min_marker_frames,
            "merge_gap_frames": args.merge_gap_frames,
        },
        "discarded_before_first_marker_frames": markers[0].start
        if markers
        else len(records),
        "discarded_marker_frames": sum(run.frame_count for run in markers),
        "discarded_after_last_marker_frames": (
            len(records) - markers[-1].end - 1 if markers else 0
        ),
        "markers": [
            {
                "start_raw_line": run.start + 1,
                "end_raw_line": run.end + 1,
                "frames": run.frame_count,
            }
            for run in markers
        ],
        "verification": verification,
        "segments": segments,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary_lines = [
        "# MediaPipeランドマーク分割結果",
        "",
        f"入力: `{args.input}`",
        f"出力: `{args.output_dir}`",
        "",
        "## 確認結果",
        "",
        f"- rawフレーム数: {len(records)}",
        f"- パー区切り: {len(markers)}回",
        f"- 作成セグメント: {len(segments)}個",
        f"- 6種類×10回を満たす: {'はい' if verification['all_motion_counts_are_expected'] else 'いいえ'}",
        "",
        "| 動作 | セグメント数 | フレーム数 |",
        "|---|---:|---:|",
    ]
    for code, name in MOTIONS:
        summary_lines.append(
            f"| {name} (`{code}`) | {counts[code]} | {frame_counts[code]} |"
        )
    summary_lines.extend(
        [
            "",
            "各セグメントは `動作コード/sample_01.jsonl` の形式で保存しています。",
            "`all_segments.jsonl` は全セグメントをまとめたファイル、"
            "`manifest.json` は区切り位置と検証結果です。",
        ]
    )
    (args.output_dir / "summary.md").write_text(
        "\n".join(summary_lines) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(verification, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
