"""Output profiles for local camera capture."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class WebcamProfile:
    """Capture and output settings for a local webcam source."""

    name: str
    width: int
    height: int
    target_fps: float
    jpeg_quality: int
    aspect_mode: str = "center_crop"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("webcam profile name must not be empty")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("webcam profile dimensions must be positive")
        if self.target_fps <= 0:
            raise ValueError("webcam profile target_fps must be positive")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("webcam profile jpeg_quality must be between 1 and 100")
        if self.aspect_mode != "center_crop":
            raise ValueError(f"unsupported webcam aspect mode: {self.aspect_mode}")


# ESP32 camera quality and OpenCV JPEG quality use different scales. 80 is a
# practical starting point for the documented ESP32 quality=8 setting.
MICON_COMPATIBLE_PROFILE = WebcamProfile(
    name="micon",
    width=800,
    height=600,
    target_fps=15.0,
    jpeg_quality=80,
)

_PROFILES = {
    MICON_COMPATIBLE_PROFILE.name: MICON_COMPATIBLE_PROFILE,
}


def get_webcam_profile(
    name: str,
    *,
    target_fps: float | None = None,
    jpeg_quality: int | None = None,
) -> WebcamProfile:
    """Return a named profile with optional runtime overrides."""

    normalized = name.strip().lower()
    try:
        profile = _PROFILES[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(_PROFILES))
        raise ValueError(
            f"unknown webcam profile {name!r}; supported profiles: {supported}"
        ) from exc

    overridden = replace(
        profile,
        target_fps=profile.target_fps if target_fps is None else target_fps,
        jpeg_quality=(
            profile.jpeg_quality if jpeg_quality is None else jpeg_quality
        ),
    )
    return overridden


def supported_webcam_profiles() -> tuple[str, ...]:
    """Return the names accepted by configuration and CLI entrypoints."""

    return tuple(sorted(_PROFILES))
