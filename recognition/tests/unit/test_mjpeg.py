from io import BytesIO
from threading import Event
from time import monotonic, sleep

from gesture_recognition.stream.mjpeg import iter_jpegs
from gesture_recognition.stream.mjpeg import MjpegFrameSource


def test_iter_jpegs_handles_boundaries_split_across_chunks() -> None:
    payload = b"--frame\r\n" + b"\xff\xd8one\xff\xd9" + b"\r\n--frame\r\n"
    payload += b"\xff\xd8two\xff\xd9\r\n"

    class ChunkedStream(BytesIO):
        def read(self, size: int = -1) -> bytes:
            return super().read(3 if size > 3 else size)

    assert list(iter_jpegs(ChunkedStream(payload))) == [
        b"\xff\xd8one\xff\xd9",
        b"\xff\xd8two\xff\xd9",
    ]


def _wait_until(predicate, timeout: float = 1.0) -> bool:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return True
        sleep(0.01)
    return predicate()


class _BlockingStream:
    def __init__(self) -> None:
        self.release = Event()
        self._first_read = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _size: int) -> bytes:
        if self._first_read:
            self._first_read = False
            return b"\xff\xd8frame\xff\xd9"
        self.release.wait(1.0)
        return b""


def test_mjpeg_source_reports_frames_and_receive_status() -> None:
    stream = _BlockingStream()
    source = MjpegFrameSource(
        "http://camera/stream",
        opener=lambda *_args, **_kwargs: stream,
        stale_after_seconds=0.2,
    )

    source.start()
    try:
        assert _wait_until(lambda: source.get_status().frames_received == 1)
        status = source.get_status()
        assert status.state == "CONNECTED"
        assert status.last_connected_at is not None
        assert status.last_frame_at is not None
        assert status.last_frame_age_seconds is not None
        assert status.to_payload()["frames_received"] == 1

        assert _wait_until(lambda: source.get_status().state == "STALE")
    finally:
        stream.release.set()
        source.stop()

    assert source.get_status().state == "STOPPED"


def test_mjpeg_source_reports_reconnect_backoff_and_error() -> None:
    source = MjpegFrameSource(
        "http://camera/stream",
        opener=lambda *_args, **_kwargs: _EmptyStream(),
        reconnect_initial_seconds=0.2,
        reconnect_max_seconds=0.2,
    )

    source.start()
    try:
        assert _wait_until(
            lambda: source.get_status().state == "RECONNECTING"
        )
        status = source.get_status()
        assert status.reconnect_count >= 1
        assert status.last_error == "MJPEG stream ended"
        assert status.retry_in_seconds is not None
        assert status.retry_in_seconds > 0
    finally:
        source.stop()


class _EmptyStream:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _size: int) -> bytes:
        return b""
