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
CAMERA_SOURCE=http://192.168.50.21/stream
# For a temporary local-camera test, set CAMERA_WEBCAM_INDEX=0 instead.
CAMERA_WEBCAM_INDEX=
CAMERA_WEBCAM_PROFILE=micon
CAMERA_WEBCAM_FPS=15
CAMERA_WEBCAM_JPEG_QUALITY=80
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

One worker process is started per camera. The default input is the HTTP MJPEG
URL in `CAMERA_SOURCE`. For temporary local testing, set
`CAMERA_WEBCAM_INDEX` to a Windows camera index; the explicit local-camera
setting takes precedence over `CAMERA_SOURCE`. The worker does not store video.

When `CAMERA_WEBCAM_PROFILE=micon`, local frames are center-cropped to 4:3,
resized to 800x600, capped at 15 FPS, and encoded with OpenCV JPEG quality 80.
The ESP32 quality value and OpenCV quality value are different scales, so this
is a practical approximation of the firmware's quality 8 setting. The actual
local receive FPS is reported by the monitor and state file. Override the
local output rate or JPEG quality with `CAMERA_WEBCAM_FPS` and
`CAMERA_WEBCAM_JPEG_QUALITY` when matching a measured device rate.

```text
MJPEG URL -> latest-frame buffer -> MediaPipe Pose + Hands
          -> shoulder normalization -> EMA smoothing
          -> 2-second sliding window -> DTW + k-NN
          -> UNKNOWN / confirmation / cooldown
          -> POST /internal/detections
```

The runtime uses the fixed set of 11 motion codes below. It does not accept
user-defined motions or add new motion codes at runtime. The reference asset
`models/motion_samples.json` contains five normalized landmark time series per
motion; it contains no camera frames.

The default temporal-recognition settings are:

```text
TARGET_FPS=15
WINDOW_FRAMES=30
INFERENCE_STRIDE_FRAMES=3
EMA_ALPHA=0.4
LANDMARK_VISIBILITY=0.5
KNN_K=3
CONFIRMATION_COUNT=2
RECOGNITION_COOLDOWN_SECONDS=1
RECOGNITION_RESET_GAP_SECONDS=1.5
```

Thresholds are stored per motion in the reference asset. A classification
whose nearest selected-motion distance exceeds that threshold is treated as
`UNKNOWN` and is not sent to the Go API. The settings are tunable through the
environment; changing them does not change the `/internal/detections` API.

The legacy fixed-rule implementation remains available as a compatibility
fallback and for the recording evaluator. Its motion-code catalogue is:

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

## Build reference templates

To rebuild the checked-in normalized template asset from labeled landmark
recordings, run this from the `recognition` directory:

```bash
PYTHONPATH=src python scripts/build_motion_templates.py \
  --data-dir data \
  --output models/motion_samples.json \
  --samples-per-motion 10 \
  --ema-alpha 0.4
```

The input files are expected to be JSONL landmark recordings with optional
`segment_id` values. The builder deterministically selects five segments per
motion and writes only the shoulder-normalized feature sequences. Use
`--threshold MOTION_CODE=VALUE` to tune an individual UNKNOWN threshold from
real-device replay results.

## Evaluate collected recordings

The existing landmark recordings can be replayed without a camera. Segmented
files are evaluated one event at a time; unsegmented files are reported as
exploratory counts rather than accuracy benchmarks.

```bash
PYTHONPATH=src python scripts/evaluate_recordings.py \
  --output data/gesture_evaluation_20260806.json
```

The evaluator reports Pose/Hands coverage, detection counts, and whether each
known segment produced exactly one detection. The runtime engine resets
gesture state after a 1.5-second capture gap so omitted waiting frames do not
join two recorded gestures while absorbing temporary recording gaps.

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

For a USB or built-in camera, use the local-camera compatibility profile:

```powershell
$env:CAMERA_WEBCAM_INDEX = "0"
$env:CAMERA_WEBCAM_PROFILE = "micon"
$env:PYTHONPATH = "src"
python scripts/monitor_detections.py --webcam-index 0 --camera-profile micon
```

The monitor prints source, connection state, output size, target FPS, and
measured receive FPS. Its state JSON contains the same camera information.

The monitor dashboard also shows camera connection status. This status is
kept inside the Python process and is not sent to the Go API. The status is
based on actual MJPEG frame reception:

- `CONNECTED`: frames are arriving
- `CONNECTING`: the first connection is being attempted
- `RECONNECTING`: the stream ended or failed and a retry is scheduled
- `STALE`: no frame arrived within `CAMERA_STALE_AFTER_SECONDS`
- `STOPPED`: the Python monitor or worker has stopped

`CAMERA_STALE_AFTER_SECONDS` defaults to 3 seconds. The monitor equivalent can
be overridden with `--stale-after-seconds 3`.

## Run locally

```bash
CAMERA_ID=demo-camera-1 \
CAMERA_SOURCE=http://192.168.50.21/stream \
GO_API_URL=http://192.168.50.11:8080/internal/detections \
python -m gesture_recognition.main
```

To run the normal worker from a local camera without sending detection events
to Go:

```powershell
$env:CAMERA_WEBCAM_INDEX = "0"
$env:CAMERA_WEBCAM_PROFILE = "micon"
python -m gesture_recognition.main --no-delivery
```

Landmark recording also accepts `--webcam-index 0 --camera-profile micon` in
place of `--camera-source`.

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
