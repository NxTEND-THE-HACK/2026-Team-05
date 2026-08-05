from datetime import datetime, timedelta, timezone
from threading import Event

from gesture_recognition.domain.models import CapturedFrame, HandObservation, Landmark, LandmarkFrame
from gesture_recognition.gestures.engine import GestureEngine
from gesture_recognition.gestures.rules import RightHandRaisedRule
from gesture_recognition.worker import RecognitionWorker


def _landmark_frame(at: datetime) -> LandmarkFrame:
    pose = {
        "RIGHT_WRIST": Landmark(0.45, 0.2, visibility=0.9),
        "RIGHT_ELBOW": Landmark(0.45, 0.45, visibility=0.9),
        "RIGHT_SHOULDER": Landmark(0.45, 0.55, visibility=0.9),
    }
    hand = HandObservation("Right", tuple(Landmark(0.4, 0.3) for _ in range(21)))
    return LandmarkFrame(at, pose, (hand,))


class FakeSource:
    def __init__(self) -> None:
        self.frames = [
            CapturedFrame(b"one", datetime(2026, 8, 5, tzinfo=timezone.utc), 1),
            CapturedFrame(b"two", datetime(2026, 8, 5, tzinfo=timezone.utc), 2),
        ]
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def read_latest(self, after_sequence: int = 0):
        for frame in self.frames:
            if frame.sequence > after_sequence:
                return frame
        return None


class FakeDetector:
    def __init__(self) -> None:
        self.closed = False
        self.calls = 0

    def detect(self, frame: CapturedFrame) -> LandmarkFrame:
        self.calls += 1
        return _landmark_frame(
            frame.captured_at + timedelta(seconds=frame.sequence * 0.6)
        )

    def close(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(self, stop: Event) -> None:
        self.events = []
        self.stop = stop

    def send(self, event) -> None:
        self.events.append(event)
        self.stop.set()


def test_worker_connects_pipeline_and_delivers_detection() -> None:
    stop = Event()
    source = FakeSource()
    detector = FakeDetector()
    client = FakeClient(stop)
    worker = RecognitionWorker(
        camera_id="camera-1",
        source=source,
        detector=detector,
        engine=GestureEngine((RightHandRaisedRule(hold_seconds=0.5),)),
        client=client,
    )

    worker.run(stop)

    assert source.started is True
    assert source.stopped is True
    assert detector.closed is True
    assert detector.calls == 2
    assert len(client.events) == 1
    assert client.events[0].camera_id == "camera-1"
