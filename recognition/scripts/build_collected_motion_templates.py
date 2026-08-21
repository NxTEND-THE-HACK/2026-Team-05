"""Build a compact motion-template asset from segmented landmark JSONL files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_motion_templates import calibrate_thresholds
from evaluate_recordings import _frame
from gesture_recognition.gestures.temporal import (
    ExponentialMovingAverage,
    HandGapFiller,
    LandmarkNormalizer,
    MotionTemplate,
    TemplateSet,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--segments-dir",
        type=Path,
        required=True,
        help="Directory containing one motion-code directory per segment set.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--visibility-threshold", type=float, default=0.5)
    parser.add_argument("--ema-alpha", type=float, default=0.4)
    parser.add_argument("--default-threshold", type=float)
    return parser.parse_args()


def _read_segment(path: Path) -> MotionTemplate:
    records = []
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                records.append(json.loads(line))
    if not records:
        raise ValueError(f"segment is empty: {path}")
    motion_code = str(records[0]["label"])
    segment_id = str(records[0].get("segment_id", path.stem))
    normalizer = LandmarkNormalizer()
    smoother = ExponentialMovingAverage()
    filler = HandGapFiller()
    frames = []
    for record in records:
        normalized = normalizer.normalize(_frame(record))
        if normalized is None:
            smoother.reset()
            filler.reset()
            continue
        frames.append(filler.update(smoother.update(normalized)).points)
    if not frames:
        raise ValueError(f"segment has no usable normalized frames: {path}")
    return MotionTemplate(motion_code, segment_id, tuple(frames))


def main() -> None:
    args = _parse_args()
    if not 0.0 <= args.visibility_threshold <= 1.0:
        raise SystemExit("--visibility-threshold must be between 0 and 1")
    if not 0.0 < args.ema_alpha <= 1.0:
        raise SystemExit("--ema-alpha must be greater than 0 and at most 1")
    if args.default_threshold is not None and args.default_threshold <= 0:
        raise SystemExit("--default-threshold must be positive")
    paths = sorted(args.segments_dir.glob("*/*.jsonl"))
    if not paths:
        raise SystemExit(f"no segment JSONL files found: {args.segments_dir}")
    templates = tuple(_read_segment(path) for path in paths)
    fallback = (
        0.35 if args.default_threshold is None else args.default_threshold
    )
    thresholds = calibrate_thresholds(templates, fallback=fallback)
    template_set = TemplateSet(templates, thresholds)
    template_set.write_json(args.output)
    print(
        json.dumps(
            {
                "templates": len(templates),
                "motions": sorted({item.motion_code for item in templates}),
                "thresholds": thresholds,
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
