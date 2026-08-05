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

- `POSE_RIGHT_HAND_UP`: right wrist held above the right shoulder for 0.45 s
- `POSE_LEFT_HAND_UP`: left wrist held above the left shoulder for 0.45 s
- `MOTION_SWIPE_RIGHT`: right wrist moves right by 0.12 normalized coordinates
- `MOTION_SWIPE_LEFT`: left wrist moves left by 0.12 normalized coordinates
- `MOTION_FINGER_SNAP`: right-hand curled preparation to extended index and
  partially extended thumb, using relaxed angle thresholds
- `MOTION_THUMBS_UP_MOVE_UP`: right-hand thumbs-up pose followed by upward movement
- `MOTION_THUMBS_DOWN_MOVE_DOWN`: right-hand thumbs-down pose followed by downward movement
- `MOTION_CLAP`: both hands move from apart to a close palm-to-palm position
- `MOTION_OPEN_TO_FIST_DOWN`: right hand changes from an open palm to a fist while lowering

The rules combine Pose and Hands detections. The thumb poses are only start
states; holding a thumbs-up or thumbs-down pose by itself does not emit an
event. Each motion is latched after one event until its release condition is
observed.

## Run locally

```bash
CAMERA_ID=demo-camera-1 \
CAMERA_SOURCE=http://192.168.50.21/stream \
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
