"""Sound-event transport and visual-validation support."""

from .source import SoundEvent, SoundEventStream, SoundSourceStatus
from .validation import (
    SoundValidationCoordinator,
    SoundValidationDecision,
    SoundValidationGate,
    decisions_for_unconfigured_sound,
)

__all__ = [
    "SoundEvent",
    "SoundEventStream",
    "SoundSourceStatus",
    "SoundValidationCoordinator",
    "SoundValidationDecision",
    "SoundValidationGate",
    "decisions_for_unconfigured_sound",
]
