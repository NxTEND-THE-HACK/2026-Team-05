"""Build the runtime gesture engine and retain the legacy rule registry."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from .base import GestureEngineLike
from .base import GestureRule
from .engine import GestureEngine
from .temporal_engine import TemporalGestureEngine
from .rules import (
    ClapRule,
    FingerSnapRule,
    HandRotateLeftRule,
    HandRotateRightRule,
    LeftHandRaisedRule,
    OpenToFistDownRule,
    RightHandRaisedRule,
    SwipeLeftRule,
    SwipeRightRule,
    ThumbsDownMoveDownRule,
    ThumbsUpMoveUpRule,
)

logger = logging.getLogger(__name__)
DEFAULT_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3] / "models" / "motion_samples.json"
)


def default_rules(
    *,
    disabled_motions: Iterable[str] = (),
) -> tuple[GestureRule, ...]:
    disabled = frozenset(
        motion_code.strip()
        for motion_code in disabled_motions
        if motion_code.strip()
    )
    rules = (
        RightHandRaisedRule(),
        LeftHandRaisedRule(),
        SwipeRightRule(),
        SwipeLeftRule(),
        FingerSnapRule(),
        ThumbsUpMoveUpRule(),
        ThumbsDownMoveDownRule(),
        ClapRule(),
        OpenToFistDownRule(),
        HandRotateRightRule(),
        HandRotateLeftRule(),
    )
    return tuple(rule for rule in rules if rule.motion_code not in disabled)


def default_engine(
    *,
    templates_path: str | Path | None = None,
    disabled_motions: Iterable[str] = (),
    **temporal_options: object,
) -> GestureEngineLike:
    """Return the temporal engine when templates are available.

    The fixed rule engine remains a deliberate fallback for development
    environments that do not have the template asset yet. A production image
    includes the asset and therefore uses the temporal pipeline by default.
    """

    path = _resolve_template_path(templates_path)
    if path.is_file():
        return TemporalGestureEngine.from_template_file(
            path,
            disabled_motions=disabled_motions,
            **temporal_options,
        )

    logger.warning(
        "motion template file not found; using legacy gesture rules path=%s",
        path,
    )
    return GestureEngine(default_rules(disabled_motions=disabled_motions))


def _resolve_template_path(templates_path: str | Path | None) -> Path:
    if templates_path is None:
        return DEFAULT_TEMPLATE_PATH
    path = Path(templates_path)
    if path.is_absolute() or path.exists():
        return path
    bundled_path = DEFAULT_TEMPLATE_PATH.parent / path
    return bundled_path if bundled_path.exists() else path
