"""Match microcontroller sound events to visual gesture candidates."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..gestures.base import GestureDetection
from .source import SoundEvent, SoundEventSource, SoundSourceStatus

SOUND_VALIDATED_MOTIONS = frozenset(
    {"MOTION_CLAP", "MOTION_FINGER_SNAP"}
)


@dataclass(frozen=True, slots=True)
class SoundValidationDecision:
    detection: GestureDetection
    detected_at: datetime
    result: str
    accepted: bool
    sound_event: SoundEvent | None = None


def decisions_for_unconfigured_sound(
    detections: Iterable[GestureDetection],
    *,
    detected_at: datetime,
) -> tuple[SoundValidationDecision, ...]:
    """Preserve visual-only behavior while recording targeted fallbacks."""

    return tuple(
        SoundValidationDecision(
            detection,
            detected_at,
            (
                "fallback"
                if detection.motion_code in SOUND_VALIDATED_MOTIONS
                else "not_required"
            ),
            True,
        )
        for detection in detections
    )


@dataclass(frozen=True, slots=True)
class _PendingCandidate:
    detection: GestureDetection
    detected_at: datetime


class SoundValidationGate:
    """Hold sound-sensitive visual detections until matching evidence arrives."""

    def __init__(
        self,
        *,
        match_before_seconds: float = 1.0,
        match_after_seconds: float = 0.25,
    ) -> None:
        if match_before_seconds < 0:
            raise ValueError("match_before_seconds must not be negative")
        if match_after_seconds < 0:
            raise ValueError("match_after_seconds must not be negative")
        self.match_before_seconds = match_before_seconds
        self.match_after_seconds = match_after_seconds
        self._events: deque[SoundEvent] = deque()
        self._pending: deque[_PendingCandidate] = deque()

    def submit(
        self,
        detections: Iterable[GestureDetection],
        *,
        detected_at: datetime,
        sound_available: bool,
        now: datetime | None = None,
    ) -> tuple[SoundValidationDecision, ...]:
        decisions: list[SoundValidationDecision] = []
        for detection in detections:
            if detection.motion_code not in SOUND_VALIDATED_MOTIONS:
                decisions.append(
                    SoundValidationDecision(
                        detection,
                        detected_at,
                        "not_required",
                        True,
                    )
                )
            elif not sound_available:
                decisions.append(
                    SoundValidationDecision(
                        detection,
                        detected_at,
                        "fallback",
                        True,
                    )
                )
            else:
                self._pending.append(_PendingCandidate(detection, detected_at))
        decisions.extend(
            self.poll(sound_available=sound_available, now=now)
        )
        return tuple(decisions)

    def add_events(self, events: Iterable[SoundEvent]) -> None:
        self._events.extend(events)

    def poll(
        self,
        *,
        sound_available: bool,
        now: datetime | None = None,
    ) -> tuple[SoundValidationDecision, ...]:
        current = now or datetime.now(timezone.utc)
        decisions: list[SoundValidationDecision] = []

        if not sound_available:
            while self._pending:
                candidate = self._pending.popleft()
                decisions.append(
                    SoundValidationDecision(
                        candidate.detection,
                        candidate.detected_at,
                        "fallback",
                        True,
                    )
                )
            self._prune_events(current)
            return tuple(decisions)

        remaining: deque[_PendingCandidate] = deque()
        while self._pending:
            candidate = self._pending.popleft()
            event = self._take_nearest_event(candidate)
            if event is not None:
                decisions.append(
                    SoundValidationDecision(
                        candidate.detection,
                        candidate.detected_at,
                        "confirmed",
                        True,
                        event,
                    )
                )
                continue

            expires_at = candidate.detected_at + timedelta(
                seconds=self.match_after_seconds
            )
            if current >= expires_at:
                decisions.append(
                    SoundValidationDecision(
                        candidate.detection,
                        candidate.detected_at,
                        "rejected_no_sound",
                        False,
                    )
                )
            else:
                remaining.append(candidate)
        self._pending = remaining
        self._prune_events(current)
        return tuple(decisions)

    def reset(self) -> None:
        self._events.clear()
        self._pending.clear()

    def _take_nearest_event(
        self,
        candidate: _PendingCandidate,
    ) -> SoundEvent | None:
        earliest = candidate.detected_at - timedelta(
            seconds=self.match_before_seconds
        )
        latest = candidate.detected_at + timedelta(
            seconds=self.match_after_seconds
        )
        matches = [
            (index, event)
            for index, event in enumerate(self._events)
            if earliest <= event.received_at <= latest
        ]
        if not matches:
            return None
        index, event = min(
            matches,
            key=lambda item: abs(
                (item[1].received_at - candidate.detected_at).total_seconds()
            ),
        )
        del self._events[index]
        return event

    def _prune_events(self, now: datetime) -> None:
        retention = self.match_before_seconds + self.match_after_seconds + 1.0
        oldest = now - timedelta(seconds=retention)
        while self._events and self._events[0].received_at < oldest:
            self._events.popleft()


class SoundValidationCoordinator:
    """Connect a live event source to a pure sound-validation gate."""

    def __init__(
        self,
        source: SoundEventSource,
        *,
        match_before_seconds: float = 1.0,
        match_after_seconds: float = 0.25,
    ) -> None:
        self.source = source
        self.gate = SoundValidationGate(
            match_before_seconds=match_before_seconds,
            match_after_seconds=match_after_seconds,
        )

    def start(self) -> None:
        self.gate.reset()
        self.source.start()

    def stop(self) -> None:
        self.source.stop()
        self.gate.reset()

    def submit(
        self,
        detections: Iterable[GestureDetection],
        *,
        detected_at: datetime,
        now: datetime | None = None,
    ) -> tuple[SoundValidationDecision, ...]:
        self.gate.add_events(self.source.read_events())
        return self.gate.submit(
            detections,
            detected_at=detected_at,
            sound_available=self.get_status().available,
            now=now,
        )

    def poll(
        self,
        *,
        now: datetime | None = None,
    ) -> tuple[SoundValidationDecision, ...]:
        self.gate.add_events(self.source.read_events())
        return self.gate.poll(
            sound_available=self.get_status().available,
            now=now,
        )

    def get_status(self) -> SoundSourceStatus:
        return self.source.get_status()
