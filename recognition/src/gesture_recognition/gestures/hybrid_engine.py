"""Compose the data-backed semantic rules with optional template rules."""

from __future__ import annotations

from ..domain.models import LandmarkFrame
from .base import GestureDetection, GestureEngineLike


class HybridGestureEngine:
    """Run two independent engines without sharing their state.

    The collected motions have semantic trajectory rules
    that are stricter and cheaper than the legacy template classifier.  Other
    motions may still be supplied by the existing template asset while the
    semantic engine handles the collected codes.  The registry removes duplicate
    template codes before constructing this wrapper.
    """

    def __init__(
        self,
        semantic_engine: GestureEngineLike,
        template_engine: GestureEngineLike | None = None,
    ) -> None:
        self._semantic_engine = semantic_engine
        self._template_engine = template_engine

    def update(self, frame: LandmarkFrame) -> tuple[GestureDetection, ...]:
        detections = list(self._semantic_engine.update(frame))
        if self._template_engine is not None:
            detections.extend(self._template_engine.update(frame))
        return tuple(detections)

    def reset(self) -> None:
        self._semantic_engine.reset()
        if self._template_engine is not None:
            self._template_engine.reset()
