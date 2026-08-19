from io import BytesIO
from threading import Event
from time import monotonic, sleep

from gesture_recognition.sound.source import SoundEventStream, iter_ndjson_lines


def test_iter_ndjson_lines_handles_fragmented_messages() -> None:
    payload = (
        b'{"type":"heartbeat","uptime_ms":1}\n'
        b'{"type":"sound","sequence":2,"uptime_ms":3}\n'
    )

    class ChunkedStream(BytesIO):
        def read1(self, size: int = -1) -> bytes:
            return super().read(4 if size > 4 else size)

    assert list(iter_ndjson_lines(ChunkedStream(payload))) == [
        b'{"type":"heartbeat","uptime_ms":1}',
        b'{"type":"sound","sequence":2,"uptime_ms":3}',
    ]


def test_iter_ndjson_lines_prefers_non_buffering_read1() -> None:
    class StreamingResponse:
        def __init__(self) -> None:
            self.chunks = iter(
                (
                    b'{"type":"heart',
                    b'beat","uptime_ms":1}\n',
                    b"",
                )
            )

        def read1(self, _size: int) -> bytes:
            return next(self.chunks)

        def read(self, _size: int) -> bytes:
            raise AssertionError("buffer-filling read() must not be used")

    assert list(iter_ndjson_lines(StreamingResponse())) == [
        b'{"type":"heartbeat","uptime_ms":1}'
    ]


def _wait_until(predicate, timeout: float = 1.0) -> bool:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return True
        sleep(0.01)
    return predicate()


class _BlockingStream:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.release = Event()
        self._first_read = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _size: int) -> bytes:
        if self._first_read:
            self._first_read = False
            return self.payload
        self.release.wait(1.0)
        return b""


def test_sound_source_receives_events_deduplicates_and_reports_stale() -> None:
    stream = _BlockingStream(
        b'{"type":"heartbeat","uptime_ms":10}\n'
        b'{"type":"sound","sequence":1,"uptime_ms":11}\n'
        b'{"type":"sound","sequence":1,"uptime_ms":12}\n'
        b'not-json\n'
    )
    source = SoundEventStream(
        "http://camera:81/sound-events",
        opener=lambda *_args, **_kwargs: stream,
        stale_after_seconds=0.1,
    )

    source.start()
    try:
        assert _wait_until(lambda: source.get_status().events_received == 1)
        events = source.read_events()
        assert len(events) == 1
        assert events[0].sequence == 1
        assert events[0].uptime_ms == 11
        status = source.get_status()
        assert status.state == "CONNECTED"
        assert status.last_message_at is not None
        assert status.last_event_at is not None
        assert status.last_event_sequence == 1
        assert status.last_event_uptime_ms == 11
        assert status.to_payload()["events_received"] == 1
        assert _wait_until(lambda: source.get_status().state == "STALE")
    finally:
        stream.release.set()
        source.stop()

    assert source.get_status().state == "STOPPED"


class _EmptyStream:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _size: int) -> bytes:
        return b""


class _ClosableBlockingStream:
    def __init__(self) -> None:
        self.read_started = Event()
        self.closed = Event()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _size: int) -> bytes:
        self.read_started.set()
        self.closed.wait(1.0)
        return b""

    def close(self) -> None:
        self.closed.set()


def test_sound_source_stop_closes_the_active_response() -> None:
    stream = _ClosableBlockingStream()
    source = SoundEventStream(
        "http://camera:81/sound-events",
        opener=lambda *_args, **_kwargs: stream,
    )

    source.start()
    assert stream.read_started.wait(1.0)
    source.stop()

    assert stream.closed.is_set()
    assert source.get_status().state == "STOPPED"


def test_sound_source_reports_reconnect_backoff() -> None:
    source = SoundEventStream(
        "http://camera:81/sound-events",
        opener=lambda *_args, **_kwargs: _EmptyStream(),
        reconnect_initial_seconds=0.2,
        reconnect_max_seconds=0.2,
    )

    source.start()
    try:
        assert _wait_until(lambda: source.get_status().state == "RECONNECTING")
        status = source.get_status()
        assert status.reconnect_count >= 1
        assert status.last_error == "sound event stream ended"
        assert status.retry_in_seconds is not None
        assert status.retry_in_seconds > 0
    finally:
        source.stop()
