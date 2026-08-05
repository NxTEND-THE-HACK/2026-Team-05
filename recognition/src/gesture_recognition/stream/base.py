"""Interfaces shared by camera input implementations."""

from __future__ import annotations

from typing import Protocol

from ..domain.models import CapturedFrame


class FrameSource(Protocol):
    """A source that makes the newest camera frame available."""

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def read_latest(self, after_sequence: int = 0) -> CapturedFrame | None: ...
