"""Explicitly disabled detection delivery for local recognition tests."""

from __future__ import annotations


class NullDeliveryClient:
    """Accept detection events without making an outbound request."""

    def send(self, _event: object) -> None:
        return None
