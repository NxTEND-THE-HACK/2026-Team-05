"""Download the pinned MediaPipe Tasks model assets for local or demo use."""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.request import urlopen


MODELS = {
    "pose_landmarker_full.task": (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_full/float16/1/pose_landmarker_full.task"
    ),
    "hand_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
        "hand_landmarker/float16/1/hand_landmarker.task"
    ),
}


def download_models(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, url in MODELS.items():
        destination = output_dir / filename
        temporary = destination.with_suffix(destination.suffix + ".part")
        if destination.is_file() and destination.stat().st_size > 0:
            print(f"exists: {destination}")
            continue
        print(f"download: {url}")
        with urlopen(url, timeout=60) as response, temporary.open("wb") as file:
            while chunk := response.read(1024 * 1024):
                file.write(chunk)
        temporary.replace(destination)
        print(f"saved: {destination}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("models"),
    )
    args = parser.parse_args()
    download_models(args.output_dir)


if __name__ == "__main__":
    main()
