"""Extract horizontal swipe sequences from a landmark recording."""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter a recording to horizontal swipe sequences."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--side", choices=("left", "right"), default="right")
    parser.add_argument("--direction", choices=("left", "right"), default="right")
    parser.add_argument("--movement-threshold", type=float, default=0.12)
    parser.add_argument("--reset-margin", type=float, default=0.05)
    parser.add_argument("--history-frames", type=int, default=30)
    parser.add_argument("--min-wrist-visibility", type=float, default=0.5)
    parser.add_argument(
        "--max-missing-frames",
        type=int,
        default=3,
        help="Keep the current gesture state across this many low-confidence frames.",
    )
    args = parser.parse_args()

    if (
        args.movement_threshold <= 0
        or args.reset_margin < 0
        or not 0 <= args.min_wrist_visibility <= 1
    ):
        raise SystemExit("movement thresholds must be non-negative and valid")
    if args.history_frames < 1:
        raise SystemExit("--history-frames must be positive")
    if args.max_missing_frames < 0:
        raise SystemExit("--max-missing-frames must not be negative")

    output = args.output or args.input.with_name(
        f"{args.input.stem}_segments{args.input.suffix}"
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    wrist_name = f"{args.side.upper()}_WRIST"
    direction = 1.0 if args.direction == "right" else -1.0
    history: deque[dict[str, Any]] = deque(maxlen=args.history_frames)
    start_x: float | None = None
    latched = False
    peak_movement: float | None = None
    segment_id = 0
    total = 0
    kept = 0
    segments = 0
    missing_frames = 0

    def write_record(destination: Any, record: dict[str, Any], segment: int, movement: float) -> None:
        nonlocal kept
        enriched = dict(record)
        enriched["segment_id"] = segment
        enriched["swipe_movement"] = movement
        destination.write(
            json.dumps(enriched, ensure_ascii=False, separators=(",", ":"))
            + "\n"
        )
        kept += 1

    with args.input.open(encoding="utf-8") as source, output.open(
        "w", encoding="utf-8"
    ) as destination:
        for line in source:
            total += 1
            record = json.loads(line)
            wrist = record.get("pose", {}).get(wrist_name)
            if wrist is None or float(wrist.get("visibility", 1.0)) < args.min_wrist_visibility:
                missing_frames += 1
                if missing_frames > args.max_missing_frames:
                    start_x = None
                    latched = False
                    peak_movement = None
                    history.clear()
                continue

            missing_frames = 0
            history.append(record)
            if start_x is None:
                start_x = wrist["x"]

            movement = direction * (wrist["x"] - start_x)
            if latched:
                peak_movement = max(peak_movement or movement, movement)
                write_record(destination, record, segment_id, movement)
                if movement <= peak_movement - args.reset_margin:
                    start_x = None
                    latched = False
                    peak_movement = None
                    history.clear()
                continue

            # Re-baseline while the hand is moving back toward the chest so
            # repeated swipes still work when the resting position drifts.
            if movement < 0:
                start_x = wrist["x"]
                movement = 0.0
                history.clear()
                history.append(record)

            if movement >= args.movement_threshold:
                latched = True
                peak_movement = movement
                segment_id += 1
                segments += 1
                for previous in history:
                    previous_wrist = previous["pose"][wrist_name]
                    previous_movement = direction * (
                        previous_wrist["x"] - start_x
                    )
                    write_record(destination, previous, segment_id, previous_movement)
    print(
        f"input_records={total} segments={segments} "
        f"kept_segment_records={kept} output={output}"
    )


if __name__ == "__main__":
    main()
