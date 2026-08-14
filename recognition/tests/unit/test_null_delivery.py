from gesture_recognition.delivery.null import NullDeliveryClient


def test_null_delivery_client_does_not_send() -> None:
    assert NullDeliveryClient().send(object()) is None
