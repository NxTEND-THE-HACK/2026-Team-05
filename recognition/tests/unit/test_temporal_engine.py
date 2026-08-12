from datetime import datetime, timedelta, timezone

from gesture_recognition.domain.models import Landmark, LandmarkFrame
from gesture_recognition.gestures.catalog import MOTION_CODES
from gesture_recognition.gestures.temporal import (
    LandmarkNormalizer,
    MotionTemplate,
    TemplateSet,
)
from gesture_recognition.gestures.temporal_engine import TemporalGestureEngine


def _raw_frame(at: datetime, *, wrist_x: float = 0.3) -> LandmarkFrame:
    return LandmarkFrame(
        at,
        {
            "LEFT_SHOULDER": Landmark(0.7, 0.5, visibility=0.9),
            "RIGHT_SHOULDER": Landmark(0.3, 0.5, visibility=0.9),
            "RIGHT_WRIST": Landmark(wrist_x, 0.3, visibility=0.9),
        },
        (),
    )


def _engine(
    *,
    threshold: float = 0.35,
    confirmation_count: int = 2,
) -> TemporalGestureEngine:
    start = datetime(2026, 8, 12, tzinfo=timezone.utc)
    normalized = LandmarkNormalizer().normalize(_raw_frame(start))
    assert normalized is not None
    template = MotionTemplate(
        MOTION_CODES[0],
        "sample-1",
        (normalized.points,),
    )
    return TemporalGestureEngine(
        TemplateSet((template,), {MOTION_CODES[0]: threshold}),
        confirmation_count=confirmation_count,
    )


def _feed(
    engine: TemporalGestureEngine,
    *,
    start: datetime,
    count: int,
    wrist_x: float = 0.3,
) -> list[str]:
    detections: list[str] = []
    for index in range(count):
        results = engine.update(
            _raw_frame(
                start + timedelta(seconds=index / 15),
                wrist_x=wrist_x,
            )
        )
        detections.extend(result.motion_code for result in results)
    return detections


def test_temporal_engine_uses_window_stride_and_confirmation() -> None:
    start = datetime(2026, 8, 12, tzinfo=timezone.utc)
    engine = _engine()

    detections = _feed(engine, start=start, count=32)
    assert detections == []
    detections.extend(
        _feed(
            engine,
            start=start + timedelta(seconds=32 / 15),
            count=3,
        )
    )

    assert detections == [MOTION_CODES[0]]
    assert engine.sampled_frame_count == 35


def test_temporal_engine_applies_per_motion_cooldown() -> None:
    start = datetime(2026, 8, 12, tzinfo=timezone.utc)
    engine = _engine()
    detections = _feed(engine, start=start, count=35)
    assert detections == [MOTION_CODES[0]]

    # The classifier keeps seeing the same motion, but a second event inside
    # one second must be suppressed.
    assert _feed(
        engine,
        start=start + timedelta(seconds=35 / 15),
        count=12,
    ) == []


def test_temporal_engine_resets_window_after_capture_gap() -> None:
    start = datetime(2026, 8, 12, tzinfo=timezone.utc)
    engine = _engine()
    assert _feed(engine, start=start, count=30) == []

    gap_frame = _raw_frame(start + timedelta(seconds=3))
    assert engine.update(gap_frame) == ()
    assert engine.sampled_frame_count == 1


def test_temporal_engine_does_not_emit_unknown_windows() -> None:
    start = datetime(2026, 8, 12, tzinfo=timezone.utc)
    engine = _engine(threshold=0.001, confirmation_count=1)

    assert _feed(engine, start=start, count=35, wrist_x=0.6) == []
