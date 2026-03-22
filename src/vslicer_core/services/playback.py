"""Playback-related helpers.

These helpers are UI-agnostic and keep only core validation logic.
"""

from ..domain.models import ClipSpec
from ..domain.validate import validate_clip_spec


def build_clip_spec(url: str, in_mark: float, out_mark: float) -> ClipSpec:
    """Build and validate a ClipSpec from timestamps.

    Args:
        url: Video URL
        in_mark: IN point (seconds)
        out_mark: OUT point (seconds)

    Returns:
        Validated ClipSpec

    Raises:
        ValueError: If the clip spec is invalid
    """
    spec = ClipSpec(url=url, in_time=in_mark, out_time=out_mark)
    is_valid, error = validate_clip_spec(spec)
    if not is_valid:
        raise ValueError(error)
    return spec
