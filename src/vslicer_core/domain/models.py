"""Domain models for VSlicer.

Core data structures representing clips, export options, and results.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class ClipSpec:
    """Specification for a video clip with IN/OUT points."""

    url: str
    in_time: float  # seconds
    out_time: float  # seconds

    @property
    def duration(self) -> float:
        """Calculate clip duration in seconds."""
        return self.out_time - self.in_time


@dataclass
class CropOptions:
    """Options for cropping video to vertical aspect ratio.

    Used for converting landscape videos to portrait for social media.
    Supports preset aspect ratios or custom width via edge dragging.
    """

    aspect_ratio: Literal["9:16", "4:5", "1:1", "custom"]
    position: float  # 0.0 = left edge, 0.5 = center, 1.0 = right edge
    custom_width_ratio: float | None = (
        None  # For custom mode: crop width as ratio of source width
    )

    def __post_init__(self):
        """Validate position and custom_width_ratio."""
        if not 0.0 <= self.position <= 1.0:
            raise ValueError(
                f"Position must be between 0.0 and 1.0, got {self.position}"
            )
        if self.aspect_ratio == "custom" and self.custom_width_ratio is None:
            raise ValueError("custom_width_ratio required for custom aspect ratio")
        if (
            self.custom_width_ratio is not None
            and not 0.0 < self.custom_width_ratio <= 1.0
        ):
            raise ValueError(
                f"custom_width_ratio must be between 0.0 and 1.0, got {self.custom_width_ratio}"
            )


@dataclass
class SlowMoOptions:
    """Options for slow-motion export.

    Either factor or target_duration should be specified, not both.
    - factor: Slow-motion factor (e.g., 5.0 = 5x slower, output 5x longer)
    - target_duration: Desired output duration in seconds
    """

    factor: float | None = None
    target_duration: float | None = None
    audio_policy: Literal["stretch", "mute", "drop"] = "stretch"

    def __post_init__(self):
        """Validate that exactly one of factor or target_duration is set."""
        if self.factor is not None and self.target_duration is not None:
            raise ValueError("Cannot specify both factor and target_duration")
        if self.factor is None and self.target_duration is None:
            raise ValueError("Must specify either factor or target_duration")
        if self.factor is not None and self.factor <= 0:
            raise ValueError(f"Factor must be positive, got {self.factor}")
        if self.target_duration is not None and self.target_duration <= 0:
            raise ValueError(
                f"Target duration must be positive, got {self.target_duration}"
            )

    def compute_factor(self, clip_duration: float) -> float:
        """Compute the slow-motion factor for the given clip duration."""
        if self.factor is not None:
            return self.factor
        assert self.target_duration is not None
        return self.target_duration / clip_duration


@dataclass
class ExportOptions:
    """Options for exporting a clip."""

    mode: Literal["fast_copy", "accurate_reencode"]
    output_path: Path
    output_type: Literal["video", "audio"] = "video"
    slowmo: SlowMoOptions | None = None
    include_audio: bool = True
    video_filter: str | None = None
    playback_mode: Literal["forward", "reverse", "pingpong"] = "forward"
    crop: CropOptions | None = None


@dataclass
class ExportResult:
    """Result of an export operation."""

    ok: bool
    output_path: Path | None = None
    error: str | None = None
    ffmpeg_log: str | None = None
