from datetime import datetime, timedelta, timezone

from gesture_recognition.gestures.base import GestureDetection
from gesture_recognition.sound.source import SoundEvent
from gesture_recognition.sound.validation import (
    SoundValidationGate,
    decisions_for_unconfigured_sound,
)


NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


def _sound(at: datetime, sequence: int = 1) -> SoundEvent:
    return SoundEvent(sequence, 1000 + sequence, at)


def test_clap_is_confirmed_by_recent_sound_and_event_is_consumed() -> None:
    gate = SoundValidationGate()
    gate.add_events((_sound(NOW - timedelta(seconds=0.1)),))

    decisions = gate.submit(
        (GestureDetection("MOTION_CLAP", 0.9),),
        detected_at=NOW,
        sound_available=True,
        now=NOW,
    )

    assert len(decisions) == 1
    assert decisions[0].accepted is True
    assert decisions[0].result == "confirmed"
    assert decisions[0].sound_event is not None

    second = gate.submit(
        (GestureDetection("MOTION_FINGER_SNAP", 0.8),),
        detected_at=NOW,
        sound_available=True,
        now=NOW + timedelta(seconds=0.3),
    )
    assert len(second) == 1
    assert second[0].result == "rejected_no_sound"
    assert second[0].accepted is False


def test_finger_snap_is_confirmed_by_recent_sound() -> None:
    gate = SoundValidationGate()
    gate.add_events((_sound(NOW - timedelta(seconds=0.05)),))

    decisions = gate.submit(
        (GestureDetection("MOTION_FINGER_SNAP", 0.85),),
        detected_at=NOW,
        sound_available=True,
        now=NOW,
    )

    assert len(decisions) == 1
    assert decisions[0].result == "confirmed"
    assert decisions[0].accepted is True


def test_candidate_waits_for_future_sound_without_blocking() -> None:
    gate = SoundValidationGate(match_after_seconds=0.25)

    assert gate.submit(
        (GestureDetection("MOTION_CLAP", 0.9),),
        detected_at=NOW,
        sound_available=True,
        now=NOW,
    ) == ()

    gate.add_events((_sound(NOW + timedelta(seconds=0.1)),))
    decisions = gate.poll(
        sound_available=True,
        now=NOW + timedelta(seconds=0.1),
    )
    assert [decision.result for decision in decisions] == ["confirmed"]


def test_connected_source_without_sound_rejects_after_grace_period() -> None:
    gate = SoundValidationGate(match_after_seconds=0.25)
    gate.submit(
        (GestureDetection("MOTION_FINGER_SNAP", 0.8),),
        detected_at=NOW,
        sound_available=True,
        now=NOW,
    )

    decisions = gate.poll(
        sound_available=True,
        now=NOW + timedelta(seconds=0.25),
    )
    assert len(decisions) == 1
    assert decisions[0].result == "rejected_no_sound"
    assert decisions[0].accepted is False


def test_unavailable_sound_source_falls_back_to_visual_detection() -> None:
    gate = SoundValidationGate()
    decisions = gate.submit(
        (GestureDetection("MOTION_CLAP", 0.9),),
        detected_at=NOW,
        sound_available=False,
        now=NOW,
    )
    assert len(decisions) == 1
    assert decisions[0].result == "fallback"
    assert decisions[0].accepted is True


def test_unconfigured_sound_records_fallback_only_for_target_motions() -> None:
    decisions = decisions_for_unconfigured_sound(
        (
            GestureDetection("MOTION_CLAP", 0.9),
            GestureDetection("MOTION_SWIPE_RIGHT", 0.7),
        ),
        detected_at=NOW,
    )

    assert [decision.result for decision in decisions] == [
        "fallback",
        "not_required",
    ]
    assert all(decision.accepted for decision in decisions)


def test_pending_candidate_falls_back_when_source_disconnects() -> None:
    gate = SoundValidationGate()
    gate.submit(
        (GestureDetection("MOTION_CLAP", 0.9),),
        detected_at=NOW,
        sound_available=True,
        now=NOW,
    )

    decisions = gate.poll(
        sound_available=False,
        now=NOW + timedelta(seconds=0.1),
    )
    assert [decision.result for decision in decisions] == ["fallback"]


def test_other_motion_is_immediate_and_sound_alone_emits_nothing() -> None:
    gate = SoundValidationGate()
    gate.add_events((_sound(NOW),))
    assert gate.poll(sound_available=True, now=NOW) == ()

    decisions = gate.submit(
        (GestureDetection("MOTION_SWIPE_RIGHT", 0.7),),
        detected_at=NOW,
        sound_available=True,
        now=NOW,
    )
    assert len(decisions) == 1
    assert decisions[0].result == "not_required"
    assert decisions[0].accepted is True
