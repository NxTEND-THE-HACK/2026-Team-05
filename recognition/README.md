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
