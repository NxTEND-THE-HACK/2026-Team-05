"""HTTP client for the Go detection endpoint."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..domain.models import DetectionEvent

logger = logging.getLogger(__name__)

UrlOpener = Callable[..., object]


class DeliveryError(RuntimeError):
    """Raised after all delivery attempts have failed."""


class NonRetryableDeliveryError(DeliveryError):
    """Raised for a client-side HTTP error that should not be retried."""


class GoApiClient:
    """Send detection events with bounded retry behavior."""

    def __init__(
        self,
        url: str,
        *,
        retries: int = 3,
        timeout_seconds: float = 3.0,
        opener: UrlOpener = urlopen,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if not url:
            raise ValueError("Go API URL must not be empty")
        if retries < 0:
            raise ValueError("retries must not be negative")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.url = url
        self._retries = retries
        self._timeout = timeout_seconds
        self._opener = opener
        self._sleeper = sleeper

    def send(self, event: DetectionEvent) -> None:
        body = json.dumps(event.to_payload()).encode("utf-8")
        request = Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        for attempt in range(self._retries + 1):
            try:
                with self._opener(request, timeout=self._timeout) as response:  # type: ignore[union-attr]
                    status = getattr(response, "status", 200)
                    if 200 <= status < 300:
                        return
                    if 400 <= status < 500:
                        raise NonRetryableDeliveryError(
                            f"Go API rejected event status={status}"
                        )
                    raise DeliveryError(f"Go API server error status={status}")
            except HTTPError as exc:
                if 400 <= exc.code < 500:
                    raise NonRetryableDeliveryError(
                        f"Go API rejected event status={exc.code}"
                    ) from exc
                error: Exception = exc
            except (URLError, TimeoutError, OSError, DeliveryError) as exc:
                if isinstance(exc, NonRetryableDeliveryError):
                    raise
                error = exc

            if attempt >= self._retries:
                raise DeliveryError(
                    f"failed to deliver event_id={event.event_id} "
                    f"after {attempt + 1} attempts"
                ) from error

            delay = min(2.0, 0.2 * (2**attempt))
            logger.warning(
                "detection delivery failed event_id=%s attempt=%d retry_in=%.1fs error=%s",
                event.event_id,
                attempt + 1,
                delay,
                error,
            )
            self._sleeper(delay)
