"""Transport-independent domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class DetectionEvent:
    """A recognized motion sent from Python to the Go backend."""

    camera_id: str
    motion_code: str
    confidence: float
    detected_at: datetime
    event_id: UUID

    @classmethod
    def create(
        cls,
        *,
        camera_id: str,
        motion_code: str,
        confidence: float,
        detected_at: datetime | None = None,
    ) -> "DetectionEvent":
        timestamp = detected_at or datetime.now(timezone.utc)
        return cls(
            camera_id=camera_id,
            motion_code=motion_code,
            confidence=confidence,
            detected_at=timestamp,
            event_id=uuid4(),
        )

    def to_payload(self) -> dict[str, str | float]:
        """Return the JSON-compatible payload expected by the Go API."""

        timestamp = self.detected_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        return {
            "event_id": str(self.event_id),
            "camera_id": self.camera_id,
            "motion_code": self.motion_code,
            "confidence": self.confidence,
            "detected_at": timestamp.astimezone(timezone.utc).isoformat(),
        }
