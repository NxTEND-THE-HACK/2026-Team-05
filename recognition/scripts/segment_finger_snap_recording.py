"""Split a finger-snap landmark recording at forward-palm delimiters."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from math import atan2, degrees
from pathlib import Path
from typing import Any

from gesture_recognition.domain.models import HandObservation, Landmark

MOTION_CODE = "MOTION_FINGER_SNAP"


def _angle(first: Landmark, middle: Landmark, last: Landmark) -> float:
    first_angle = atan2(first.y - middle.y, first.x - middle.x)
    last_angle = atan2(last.y - middle.y, last.x - middle.x)
    value = abs(degrees(first_angle - last_angle))
    return 360.0 - value if value > 180.0 else value


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


def _hand_area(hand: HandObservation) -> float:
    if len(hand.landmarks) < 21:
        return 0.0
    xs = [point.x for point in hand.landmarks]
    ys = [point.y for point in hand.landmarks]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def _is_marker(record: dict[str, Any], args: argparse.Namespace) -> bool:
    for raw_hand in record.get("hands", []):
        hand = _hand(raw_hand)
        if not _is_open_palm(hand):
            continue
        wrist = hand.point(0)
        if not args.min_wrist_x <= wrist.x <= args.max_wrist_x:
            continue
        if not args.min_wrist_y <= wrist.y <= args.max_wrist_y:
            continue
        if _hand_area(hand) >= args.area_threshold:
            return True
    return False


def _marker_runs(
    flags: list[bool],
    *,
    minimum_frames: int,
    merge_gap_frames: int,
) -> list[tuple[int, int]]:
    raw_runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, flag in enumerate(flags):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            raw_runs.append((start, index - 1))
            start = None
    if start is not None:
        raw_runs.append((start, len(flags) - 1))

    merged: list[tuple[int, int]] = []
    for run in raw_runs:
        if (
            merged
            and run[0] - merged[-1][1] - 1 <= merge_gap_frames
        ):
            merged[-1] = (merged[-1][0], run[1])
        else:
            merged.append(run)
    return [run for run in merged if run[1] - run[0] + 1 >= minimum_frames]


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
                json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--area-threshold", type=float, default=0.01)
    parser.add_argument("--min-wrist-x", type=float, default=0.20)
    parser.add_argument("--max-wrist-x", type=float, default=0.80)
    parser.add_argument("--min-wrist-y", type=float, default=0.25)
    parser.add_argument("--max-wrist-y", type=float, default=0.75)
    parser.add_argument("--minimum-marker-frames", type=int, default=5)
    parser.add_argument("--merge-gap-frames", type=int, default=2)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be positive")
    if args.area_threshold <= 0:
        parser.error("--area-threshold must be positive")
    if args.minimum_marker_frames < 1:
        parser.error("--minimum-marker-frames must be positive")
    if args.merge_gap_frames < 0:
        parser.error("--merge-gap-frames must not be negative")
    return args


def main() -> None:
    args = _parse_args()
    if not args.input.is_file():
        raise SystemExit(f"input not found: {args.input}")
    if args.output_dir.exists():
        raise SystemExit(f"output directory already exists: {args.output_dir}")

    records: list[dict[str, Any]] = []
    with args.input.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if line.strip():
                record = json.loads(line)
                record["_raw_line"] = line_number
                records.append(record)
    if not records:
        raise SystemExit("input contains no records")

    flags = [_is_marker(record, args) for record in records]
    markers = _marker_runs(
        flags,
        minimum_frames=args.minimum_marker_frames,
        merge_gap_frames=args.merge_gap_frames,
    )
    segments: list[dict[str, Any]] = []
    for index, (before, after) in enumerate(zip(markers, markers[1:]), start=1):
        start = before[1] + 1
        end = after[0] - 1
        if end < start:
            continue
        segment_id = f"{MOTION_CODE}_{index:02d}"
        segment_records: list[dict[str, Any]] = []
        for record in records[start : end + 1]:
            output_record = {
                key: value for key, value in record.items() if key != "_raw_line"
            }
            output_record["source_label"] = output_record.get("label")
            output_record["label"] = MOTION_CODE
            output_record["segment_id"] = segment_id
            segment_records.append(output_record)
        segments.append(
            {
                "index": index,
                "code": MOTION_CODE,
                "sample_number": index,
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
        segment_dir = args.output_dir / MOTION_CODE
        segment_dir.mkdir(exist_ok=True)
        path = segment_dir / f"sample_{int(segment['sample_number']):02d}.jsonl"
        segment["file"] = str(path.relative_to(args.output_dir))
        segment_records = segment.pop("records")
        _write_jsonl(path, segment_records)
        all_records.extend(segment_records)
    _write_jsonl(args.output_dir / "all_segments.jsonl", all_records)

    verification = {
        "expected_samples": args.samples,
        "marker_runs": len(markers),
        "expected_marker_runs": args.samples + 1,
        "segments_created": len(segments),
        "sample_count_matches": len(segments) == args.samples,
        "total_segment_frames": len(all_records),
    }
    manifest = {
        "schema_version": 1,
        "input": str(args.input),
        "output_dir": str(args.output_dir),
        "label": MOTION_CODE,
        "split_rule": {
            "marker": "forward open palm",
            "area_threshold": args.area_threshold,
            "wrist_x_range": [args.min_wrist_x, args.max_wrist_x],
            "wrist_y_range": [args.min_wrist_y, args.max_wrist_y],
            "minimum_marker_frames": args.minimum_marker_frames,
            "merge_gap_frames": args.merge_gap_frames,
        },
        "verification": verification,
        "markers": [
            {
                "start_raw_line": start + 1,
                "end_raw_line": end + 1,
                "frames": end - start + 1,
            }
            for start, end in markers
        ],
        "segments": segments,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = [
        "# Finger snap landmark segments",
        "",
        f"- input: `{args.input}`",
        f"- output: `{args.output_dir}`",
        f"- marker runs: {len(markers)}",
        f"- segments: {len(segments)}",
        f"- expected samples: {args.samples}",
        f"- count matches: {verification['sample_count_matches']}",
        "",
        "| sample | frames | duration (s) |",
        "|---:|---:|---:|",
    ]
    for segment in segments:
        summary.append(
            f"| {segment['sample_number']} | {segment['frames']} | "
            f"{segment['duration_seconds']} |"
        )
    (args.output_dir / "summary.md").write_text(
        "\n".join(summary) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(verification, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
