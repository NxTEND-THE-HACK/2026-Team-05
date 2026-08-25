"""Extract frames that satisfy the current right-hand-raised pose geometry."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def _angle(first: dict[str, Any], middle: dict[str, Any], last: dict[str, Any]) -> float:
    first_angle = math.atan2(
        first["y"] - middle["y"], first["x"] - middle["x"]
    )
    last_angle = math.atan2(
        last["y"] - middle["y"], last["x"] - middle["x"]
    )
    value = abs(math.degrees(first_angle - last_angle))
    return 360.0 - value if value > 180.0 else value


def _is_raised(record: dict[str, Any], side: str) -> bool:
    pose = record.get("pose", {})
    wrist = pose.get(f"{side.upper()}_WRIST")
    elbow = pose.get(f"{side.upper()}_ELBOW")
    shoulder = pose.get(f"{side.upper()}_SHOULDER")
    if wrist is None or elbow is None or shoulder is None:
        return False

    if any(
        point.get("visibility") is not None and point["visibility"] < 0.5
        for point in (wrist, elbow, shoulder)
    ):
        return False

    return (
        shoulder["y"] - wrist["y"] >= 0.05
        and _angle(wrist, elbow, shoulder) >= 90.0
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter a pose recording to raised-right-hand frames."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--side", choices=("left", "right"), default="right")
    args = parser.parse_args()

    output = args.output or args.input.with_name(
        f"{args.input.stem}_raised{args.input.suffix}"
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    kept = 0
    with args.input.open(encoding="utf-8") as source, output.open(
        "w", encoding="utf-8"
    ) as destination:
        for line in source:
            total += 1
            record = json.loads(line)
            if not _is_raised(record, args.side):
                continue
            destination.write(
                json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )
            kept += 1

    print(f"input_records={total} kept_raised_records={kept} output={output}")


if __name__ == "__main__":
    main()
