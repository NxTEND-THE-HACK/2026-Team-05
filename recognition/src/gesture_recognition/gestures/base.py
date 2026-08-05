"""Interfaces and results for gesture rules."""

from __future__ import annotations

from typing import Protocol
from dataclasses import dataclass

from ..domain.models import LandmarkFrame


@dataclass(frozen=True, slots=True)
class GestureDetection:
    """A gesture recognized in one frame."""

    motion_code: str
    confidence: float


class GestureRule(Protocol):
    """Stateful rule evaluated once per processed frame."""

    motion_code: str

    def update(self, frame: LandmarkFrame) -> GestureDetection | None: ...

    def reset(self) -> None: ...
