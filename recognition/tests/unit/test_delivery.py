import json
from datetime import datetime, timezone

from gesture_recognition.delivery.go_api_client import (
    DeliveryError,
    GoApiClient,
)
from gesture_recognition.domain.models import DetectionEvent


class FakeResponse:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_client_sends_json_event() -> None:
    requests = []

    def opener(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    event = DetectionEvent.create(
        camera_id="camera-1",
        motion_code="MOTION_A",
        confidence=0.9,
        detected_at=datetime(2026, 8, 5, tzinfo=timezone.utc),
    )
    GoApiClient("http://go/internal/detections", opener=opener).send(event)

    request, timeout = requests[0]
    assert timeout == 3.0
    assert request.get_method() == "POST"
    assert json.loads(request.data)["event_id"] == str(event.event_id)


def test_client_retries_transport_failure() -> None:
    attempts = 0

    def opener(request, timeout):
        nonlocal attempts
        attempts += 1
        raise OSError("connection refused")

    client = GoApiClient(
        "http://go/internal/detections",
        retries=2,
        sleeper=lambda _: None,
        opener=opener,
    )
    event = DetectionEvent.create(
        camera_id="camera-1", motion_code="MOTION_A", confidence=0.9
    )

    try:
        client.send(event)
    except DeliveryError:
        pass
    else:
        raise AssertionError("delivery should fail")
    assert attempts == 3
