from datetime import datetime, timezone

import pytest

from gesture_recognition.observability.metrics import FrameProcessingMetrics


def test_metrics_count_overwritten_frames_and_inference_rate() -> None:
    now = [0.0]
    metrics = FrameProcessingMetrics(clock=lambda: now[0])
    captured_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    metrics.observe_frame(1)
    metrics.record_inference(0.04, captured_at=captured_at)
    now[0] = 0.1
    metrics.observe_frame(3)
    metrics.record_inference(0.05, captured_at=captured_at)

    payload = metrics.to_payload()

    assert payload["frames_processed"] == 2
    assert payload["frames_output"] == 2
    assert payload["frames_dropped"] == 1
    assert payload["inference_fps"] == 10.0
    assert payload["output_fps"] == 10.0
    assert payload["processing_ratio"] == pytest.approx(66.7, abs=0.1)
    assert payload["last_inference_ms"] == 50.0
    assert payload["average_inference_ms"] == 45.0


def test_metrics_count_inference_errors() -> None:
    metrics = FrameProcessingMetrics(clock=lambda: 1.0)
    captured_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    metrics.observe_frame(1)
    metrics.record_inference(
        0.01,
        captured_at=captured_at,
        success=False,
    )

    payload = metrics.to_payload()

    assert payload["frames_processed"] == 1
    assert payload["frames_output"] == 0
    assert payload["inference_errors"] == 1
    assert payload["last_inference_at"] == captured_at.isoformat()


def test_metrics_report_completed_loop_rate_and_duration() -> None:
    now = [0.0]
    metrics = FrameProcessingMetrics(clock=lambda: now[0])

    metrics.record_loop(0.02)
    now[0] = 0.1
    metrics.record_loop(0.04)

    payload = metrics.to_payload()

    assert payload["loop_fps"] == 10.0
    assert payload["average_loop_ms"] == 30.0


def test_metrics_reject_invalid_values() -> None:
    with pytest.raises(ValueError):
        FrameProcessingMetrics(window_seconds=0)

    metrics = FrameProcessingMetrics()
    with pytest.raises(ValueError):
        metrics.observe_frame(0)
    with pytest.raises(ValueError):
        metrics.record_inference(
            -0.1,
            captured_at=datetime.now(timezone.utc),
        )
    with pytest.raises(ValueError):
        metrics.record_loop(-0.1)
