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

## Runtime architecture

One worker process is started per camera. `CAMERA_SOURCE` must be an HTTP
MJPEG URL, so an ESP32 camera and the Windows demo PC can use the same input
path. The Windows PC should expose its webcam as an MJPEG stream; the worker
does not store video.

```text
MJPEG URL -> latest-frame buffer -> MediaPipe Pose + Hands
          -> fixed gesture rules -> POST /internal/detections
```

The provisional fixed motion codes are:

- `POSE_RIGHT_HAND_UP`: right wrist held above the right shoulder for 0.6 s
- `MOTION_SWIPE_RIGHT`: right wrist moves right by 0.18 normalized coordinates

The rules combine Pose and Hands detections. A static pose is latched after
one event until the user returns to the release posture.

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

Use a separate env file for each camera. The Go API and PostgreSQL are not
embedded in this image.
