from datetime import datetime, timezone
from uuid import UUID

from gesture_recognition.domain.models import DetectionEvent


def test_detection_event_payload_matches_go_contract() -> None:
    event = DetectionEvent.create(
        camera_id="camera-1",
        motion_code="MOTION_A",
        confidence=0.93,
        detected_at=datetime(2026, 8, 4, 6, 0, tzinfo=timezone.utc),
    )

    payload = event.to_payload()

    assert UUID(payload["event_id"])
    assert payload == {
        "event_id": payload["event_id"],
        "camera_id": "camera-1",
        "motion_code": "MOTION_A",
        "confidence": 0.93,
        "detected_at": "2026-08-04T06:00:00+00:00",
    }
