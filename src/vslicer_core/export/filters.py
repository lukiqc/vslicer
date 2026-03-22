"""FFmpeg filter builders for video and audio processing.

The most critical component is the atempo chain builder, which handles audio
slow-motion within ffmpeg's atempo filter limits [0.5, 2.0].
"""


def build_setpts_filter(factor: float) -> str:
    """Build setpts filter for video time stretching.

    Args:
        factor: Slow-motion factor (e.g., 5.0 = 5x slower, output 5x longer)

    Returns:
        Filter string like "setpts=5.0*PTS"
    """
    return f"setpts={factor}*PTS"


def build_atempo_chain(slowmo_factor: float) -> str:
    """Build atempo filter chain for audio time stretching.

    ffmpeg's atempo filter accepts only [0.5, 2.0] per instance.
    For slow-motion, we need tempo = 1/slowmo_factor (tempo < 1 slows down).
    We chain multiple atempo filters to achieve the target tempo.

    Algorithm:
    1. Calculate target tempo = 1 / slowmo_factor
    2. While tempo < 0.5: apply atempo=0.5, tempo /= 0.5 (or tempo *= 2)
    3. While tempo > 2.0: apply atempo=2.0, tempo /= 2.0
    4. Apply remaining tempo if it's not 1.0 (identity)

    Examples:
    - slowmo_factor=0.5 (2x speed) → tempo=2.0 → "atempo=2.0"
    - slowmo_factor=1.0 (normal) → tempo=1.0 → "" (no filter needed)
    - slowmo_factor=2.0 (2x slow) → tempo=0.5 → "atempo=0.5"
    - slowmo_factor=5.0 (5x slow) → tempo=0.2 → "atempo=0.5,atempo=0.5,atempo=0.8"
    - slowmo_factor=10.0 (10x slow) → tempo=0.1 → chain of 4 filters
    - slowmo_factor=0.25 (4x speed) → tempo=4.0 → "atempo=2.0,atempo=2.0"

    Args:
        slowmo_factor: Slow-motion factor (e.g., 5.0 = 5x slower)

    Returns:
        Comma-separated atempo filter chain, e.g. "atempo=0.5,atempo=0.5,atempo=0.8"
        Returns empty string if no tempo change needed (factor == 1.0)
    """
    if slowmo_factor == 1.0:
        return ""  # No tempo change needed

    tempo = 1.0 / slowmo_factor
    chain = []

    # Handle tempo < 0.5 (very slow playback)
    while tempo < 0.5 - 1e-9:  # Small epsilon for floating point comparison
        chain.append("0.5")
        tempo /= 0.5  # Equivalent to tempo *= 2

    # Handle tempo > 2.0 (fast playback / speedup)
    while tempo > 2.0 + 1e-9:  # Small epsilon for floating point comparison
        chain.append("2.0")
        tempo /= 2.0

    # Add remaining tempo if it's not identity (1.0)
    # Use tolerance for floating point comparison
    if abs(tempo - 1.0) > 1e-9:
        chain.append(f"{tempo:.10f}".rstrip("0").rstrip("."))

    if not chain:
        return ""

    return f"atempo={',atempo='.join(chain)}"


def build_video_filter(slowmo_factor: float | None = None) -> str:
    """Build complete video filter string.

    Args:
        slowmo_factor: Optional slow-motion factor

    Returns:
        Video filter string for ffmpeg -vf parameter, or empty string if no filter needed
    """
    if slowmo_factor is None or slowmo_factor == 1.0:
        return ""
    return build_setpts_filter(slowmo_factor)


def build_audio_filter(slowmo_factor: float | None = None) -> str:
    """Build complete audio filter string.

    Args:
        slowmo_factor: Optional slow-motion factor

    Returns:
        Audio filter string for ffmpeg -af parameter, or empty string if no filter needed
    """
    if slowmo_factor is None or slowmo_factor == 1.0:
        return ""
    return build_atempo_chain(slowmo_factor)


def build_crop_filter(
    aspect_ratio: str,
    position: float,
    source_width: int,
    source_height: int,
    custom_width_ratio: float | None = None,
) -> str:
    """Build ffmpeg crop filter for converting to vertical aspect ratio.

    Calculates crop dimensions to achieve target aspect ratio while keeping
    full source height. Position determines which horizontal slice to keep.

    Args:
        aspect_ratio: Target aspect ratio ("9:16", "4:5", "1:1", or "custom")
        position: Horizontal position, 0.0 = left edge, 0.5 = center, 1.0 = right edge
        source_width: Source video width in pixels
        source_height: Source video height in pixels
        custom_width_ratio: For custom mode, crop width as ratio of source width (0.0-1.0)

    Returns:
        FFmpeg crop filter string like "crop=608:1080:336:0"

    Examples:
        >>> build_crop_filter("9:16", 0.5, 1920, 1080)
        'crop=608:1080:656:0'
        >>> build_crop_filter("9:16", 0.0, 1920, 1080)
        'crop=608:1080:0:0'
        >>> build_crop_filter("1:1", 0.5, 1920, 1080)
        'crop=1080:1080:420:0'
        >>> build_crop_filter("custom", 0.5, 1920, 1080, custom_width_ratio=0.5)
        'crop=960:1080:480:0'
    """
    crop_height = source_height

    if aspect_ratio == "custom":
        if custom_width_ratio is None:
            raise ValueError("custom_width_ratio required for custom aspect ratio")
        crop_width = int(source_width * custom_width_ratio)
    else:
        # Parse aspect ratio from presets
        ratio_map = {
            "9:16": 9 / 16,
            "4:5": 4 / 5,
            "1:1": 1 / 1,
        }
        target_ratio = ratio_map.get(aspect_ratio)
        if target_ratio is None:
            raise ValueError(f"Unsupported aspect ratio: {aspect_ratio}")

        # Calculate crop width from aspect ratio (keep full height)
        crop_width = int(crop_height * target_ratio)

    # Ensure crop width doesn't exceed source width
    if crop_width > source_width:
        crop_width = source_width

    # Calculate x offset based on position
    # position=0.0 -> x=0 (left edge)
    # position=1.0 -> x=source_width-crop_width (right edge)
    # position=0.5 -> centered
    max_x = source_width - crop_width
    x_offset = int(max_x * position)

    # y offset is always 0 (top of frame)
    y_offset = 0

    return f"crop={crop_width}:{crop_height}:{x_offset}:{y_offset}"
