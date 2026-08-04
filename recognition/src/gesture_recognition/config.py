"""Environment-based worker configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from collections.abc import Mapping


class ConfigurationError(ValueError):
    """Raised when required worker configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    camera_id: str
    camera_source: str
    go_api_url: str
    log_level: str = "INFO"
    reconnect_initial_seconds: float = 1.0
    reconnect_max_seconds: float = 30.0
    detection_send_retries: int = 3
    detection_send_timeout_seconds: float = 3.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if env is None else env

        camera_id = _required(values, "CAMERA_ID")
        camera_source = _required(values, "CAMERA_SOURCE")
        go_api_url = values.get(
            "GO_API_URL", "http://127.0.0.1:8080/internal/detections"
        )

        initial = _positive_float(values, "RECONNECT_INITIAL_SECONDS", 1.0)
        maximum = _positive_float(values, "RECONNECT_MAX_SECONDS", 30.0)
        if maximum < initial:
            raise ConfigurationError(
                "RECONNECT_MAX_SECONDS must be greater than or equal to "
                "RECONNECT_INITIAL_SECONDS"
            )

        retries = _non_negative_int(values, "DETECTION_SEND_RETRIES", 3)
        timeout = _positive_float(
            values, "DETECTION_SEND_TIMEOUT_SECONDS", 3.0
        )

        return cls(
            camera_id=camera_id,
            camera_source=camera_source,
            go_api_url=go_api_url,
            log_level=values.get("LOG_LEVEL", "INFO").upper(),
            reconnect_initial_seconds=initial,
            reconnect_max_seconds=maximum,
            detection_send_retries=retries,
            detection_send_timeout_seconds=timeout,
        )


def _required(values: Mapping[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise ConfigurationError(f"{key} is required")
    return value


def _positive_float(
    values: Mapping[str, str], key: str, default: float
) -> float:
    raw = values.get(key)
    try:
        value = default if raw is None else float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be a number") from exc
    if value <= 0:
        raise ConfigurationError(f"{key} must be greater than zero")
    return value


def _non_negative_int(
    values: Mapping[str, str], key: str, default: int
) -> int:
    raw = values.get(key)
    try:
        value = default if raw is None else int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be an integer") from exc
    if value < 0:
        raise ConfigurationError(f"{key} must not be negative")
    return value
