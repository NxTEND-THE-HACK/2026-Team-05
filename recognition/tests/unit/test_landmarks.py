from datetime import datetime, timezone

from gesture_recognition.domain.models import HandObservation, Landmark, LandmarkFrame


def test_landmark_frame_keeps_pose_and_hand_data() -> None:
    wrist = Landmark(0.4, 0.2)
    hand = HandObservation("Right", tuple([wrist] * 21))
    frame = LandmarkFrame(
        captured_at=datetime(2026, 8, 5, tzinfo=timezone.utc),
        pose={"RIGHT_WRIST": wrist},
        hands=(hand,),
    )

    assert frame.pose["RIGHT_WRIST"].y == 0.2
    assert frame.hands[0].point(0) == wrist
