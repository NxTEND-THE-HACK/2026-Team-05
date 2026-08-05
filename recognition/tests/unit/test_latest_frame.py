from datetime import datetime, timezone

from gesture_recognition.stream.latest import LatestFrameStore


def test_store_returns_only_newer_frame() -> None:
    store = LatestFrameStore()
    first = store.put(b"first", datetime(2026, 1, 1, tzinfo=timezone.utc))
    second = store.put(b"second", datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert store.read_latest().data == b"second"
    assert store.read_latest(first.sequence).data == b"second"
    assert store.read_latest(second.sequence) is None
