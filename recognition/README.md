# Gesture Recognition Worker

Python worker for the smart-home MVP. The worker receives a camera stream,
recognizes predefined poses or motions, and sends detection events to the Go
API. Video is processed in memory and is not persisted.

## Local setup

```bash
cd recognition
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

## Configuration

The worker is configured with environment variables. A separate process is
started for each camera.

```text
CAMERA_ID=demo-camera-1
CAMERA_SOURCE=http://192.168.10.106/stream
GO_API_URL=http://192.168.50.11:8080/internal/detections
```

See `.env.example` for the complete list of settings.

Before running locally, download the MediaPipe Tasks model assets:

```bash
python scripts/download_models.py --output-dir models
```

The `.task` files are ignored by Git because they are binary assets. Keep
them on the demo machine or build them into the Docker image. Override
`POSE_MODEL_PATH` and `HAND_MODEL_PATH` when using another model directory.

## Runtime architecture

One worker process is started per camera. `CAMERA_SOURCE` must be an HTTP
MJPEG URL, so an ESP32 camera and the Windows demo PC can use the same input
path. The Windows PC should expose its webcam as an MJPEG stream; the worker
does not store video.

```text
MJPEG URL -> latest-frame buffer -> MediaPipe Pose + Hands
          -> fixed gesture rules -> POST /internal/detections
```

The fixed recognition codes are:

- `POSE_RIGHT_HAND_UP`: Pose right wrist held at least 0.23 normalized units
  above the right shoulder for 0.45 s
- `POSE_LEFT_HAND_UP`: Pose left wrist held at least 0.23 normalized units
  above the left shoulder for 0.45 s
- `MOTION_SWIPE_RIGHT`: Pose right wrist moves from the chest toward the person's right
  by 0.18 normalized camera coordinates within 1.50 s of the chest baseline.
  The front-facing stream makes this a decrease in image X; HandLandmarker
  output is not required.
- `MOTION_SWIPE_LEFT`: Pose left wrist moves from the chest toward the person's left
  by 0.18 normalized camera coordinates within 1.50 s of the chest baseline.
  The front-facing stream makes this an increase in image X; HandLandmarker
  output is not required.
- `MOTION_FINGER_SNAP`: right-hand curled preparation to extended index and
  partially extended thumb, with the thumb-middle contact ratio at release
  no greater than 0.50, a matching thumb direction when Hand/Pose agree, and
  a 1.50 s duplicate guard
- `MOTION_THUMBS_UP_MOVE_UP`: right-hand thumbs-up pose followed by upward movement;
  the thumb must be visibly above the wrist
- `MOTION_THUMBS_DOWN_MOVE_DOWN`: right-hand thumbs-down pose followed by downward
  movement. The pose is a short-lived gate; the event is rejected if an upward
  thumb pose appears first or if the wrist has already moved too far below the
  shoulder region
- `MOTION_CLAP`: Pose left/right wrists move from apart to a close position,
  normalized by shoulder width; both wrists must finish near the shoulder
  center (within 0.30 shoulder widths); HandLandmarker output is not required
- `MOTION_OPEN_TO_FIST_DOWN`: right hand changes from an open palm to a fist while
  lowering. The event also requires a chest-region vertical trajectory, which
  prevents a hand that is already near the waist from being mistaken for this motion
- `MOTION_HAND_ROTATE_RIGHT`: both the right palm's wrist-to-middle-finger
  axis and wrist-to-index-finger axis rotate clockwise relative to the right
  forearm by at least 20 degrees from their baselines. The collected right-hand
  recordings also constrain the 0.22–1.16 s timing, Pose-wrist path, vertical
  displacement, raw palm axis, and ring-finger angle envelope; a second frame
  confirms the direction before emitting. A 1.25 s duplicate cooldown and a
  short hand-tracking gap (up to 0.40 s) are applied.
- `MOTION_HAND_ROTATE_LEFT`: both the left palm's wrist-to-middle-finger
  axis and wrist-to-index-finger axis rotate counter-clockwise relative to the
  left forearm by at least 20 degrees from their baselines. The collected
  left-hand recordings constrain the 0.70–3.10 s candidate window, cumulative
  Pose-wrist path, raw middle-finger axis change, and index-finger angle range;
  a 1.25 s duplicate cooldown and a short hand-tracking gap (up to 0.60 s) are
  applied.

The rules combine Pose and Hands detections. The thumb poses are only start
states; holding a thumbs-up or thumbs-down pose by itself does not emit an
event. Pose detections use a 0.75 s duplicate cooldown, and each motion is
latched after one event until its release condition is observed.

## Evaluate collected recordings

The existing landmark recordings can be replayed without a camera. Segmented
files are evaluated one event at a time; unsegmented files are reported as
exploratory counts rather than accuracy benchmarks.

```bash
PYTHONPATH=src python scripts/evaluate_recordings.py \
  --output data/gesture_evaluation_20260806.json
```

The evaluator reports Pose/Hands coverage, detection counts, and whether each
known segment produced exactly one detection. The runtime engine also resets
gesture state after a 0.75-second capture gap so omitted waiting frames do not
join two recorded gestures.

To run the same recordings through every rule and inspect off-diagonal false
positives, add `--cross-check`:

```bash
PYTHONPATH=src python scripts/evaluate_recordings.py \
  --cross-check
```

The report's `cross_check.rules` section lists each rule's own positive count
and false positives produced by the other recordings.

For camera-only testing without appliance delivery, run the monitor below. It
never calls the Go API and prints only detected motions:

```bash
PYTHONPATH=src python scripts/monitor_detections.py \
  --camera-source http://10.0.1.107/stream
```

## Run locally

```bash
CAMERA_ID=demo-camera-1 \
CAMERA_SOURCE=http://192.168.10.106/stream \
GO_API_URL=http://192.168.50.11:8080/internal/detections \
python -m gesture_recognition.main
```

For two cameras, start two processes with different `CAMERA_ID` and
`CAMERA_SOURCE` values. The worker keeps only the newest frame, reconnects
with exponential backoff, and retries event delivery a bounded number of
times.

## Docker

Build the image from this directory and run one container per camera:

```bash
docker build -t gesture-recognition .
docker run --rm --env-file .env.camera-1 gesture-recognition
```

The Docker build downloads the pinned MediaPipe Tasks models into the image.

Use a separate env file for each camera. The Go API and PostgreSQL are not
embedded in this image.
