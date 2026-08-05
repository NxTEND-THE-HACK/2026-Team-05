from io import BytesIO

from gesture_recognition.stream.mjpeg import iter_jpegs


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
