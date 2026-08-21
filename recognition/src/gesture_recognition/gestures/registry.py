"""Build the runtime gesture engine and retain the legacy rule registry."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from .base import GestureEngineLike
from .base import GestureRule
from .engine import GestureEngine
from .hybrid_engine import HybridGestureEngine
from .temporal_engine import TemporalGestureEngine
from .temporal import MotionTemplate, TemplateSet
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

# These motions were recorded as delimited samples and tuned against the
# resulting landmark trajectories.  They must not also be classified by the
# older template model, whose broad windows caused the Good/Bad motions to
# overlap with right swipes.  Finger snap is included here because its
# microphone-free pose rule is tuned from the collected landmark data.
COLLECTED_SEMANTIC_MOTIONS = frozenset(
    {
        "POSE_RIGHT_HAND_UP",
        "POSE_LEFT_HAND_UP",
        "MOTION_SWIPE_RIGHT",
        "MOTION_SWIPE_LEFT",
        "MOTION_THUMBS_UP_MOVE_UP",
        "MOTION_THUMBS_DOWN_MOVE_DOWN",
        "MOTION_FINGER_SNAP",
    }
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
    """Return the tuned semantic engine plus any remaining template motions.

    The collected motions use the stricter semantic rules.  If the
    model asset also contains motions outside that set, those are kept in a
    separate temporal engine so their state cannot make the collected
    motions fire.  The fixed rule engine remains a fallback when no model
    asset is present.
    """

    disabled = frozenset(
        motion_code.strip()
        for motion_code in disabled_motions
        if motion_code.strip()
    )
    path = _resolve_template_path(templates_path)
    if path.is_file():
        semantic_rules = tuple(
            rule
            for rule in default_rules(disabled_motions=disabled)
            if rule.motion_code in COLLECTED_SEMANTIC_MOTIONS
        )
        template_engine = _remaining_template_engine(
            path,
            disabled=disabled,
            temporal_options=temporal_options,
        )
        semantic_engine = GestureEngine(semantic_rules)
        if template_engine is not None:
            return HybridGestureEngine(semantic_engine, template_engine)
        return semantic_engine

    logger.warning(
        "motion template file not found; using legacy gesture rules path=%s",
        path,
    )
    return GestureEngine(default_rules(disabled_motions=disabled))


def _remaining_template_engine(
    path: Path,
    *,
    disabled: frozenset[str],
    temporal_options: dict[str, object],
) -> TemporalGestureEngine | None:
    """Build the temporal side after removing data-backed motion codes."""

    template_set = TemplateSet.from_json(path)
    excluded = disabled | COLLECTED_SEMANTIC_MOTIONS
    templates: tuple[MotionTemplate, ...] = tuple(
        template
        for template in template_set.templates
        if template.motion_code not in excluded
    )
    if not templates:
        return None
    thresholds = {
        motion_code: threshold
        for motion_code, threshold in template_set.thresholds.items()
        if motion_code not in excluded
    }
    remaining = TemplateSet(templates, thresholds, template_set.schema_version)
    return TemporalGestureEngine(remaining, **temporal_options)


def _resolve_template_path(templates_path: str | Path | None) -> Path:
    if templates_path is None:
        return DEFAULT_TEMPLATE_PATH
    path = Path(templates_path)
    if path.is_absolute() or path.exists():
        return path
    bundled_path = DEFAULT_TEMPLATE_PATH.parent / path
    return bundled_path if bundled_path.exists() else path
