"""FFmpeg progress output parser.

Parses the key=value format from ffmpeg's -progress output.
"""


def parse_progress_line(line: str) -> dict | None:
    """Parse a single line from ffmpeg progress output.

    FFmpeg with -progress pipe:1 outputs lines in key=value format:
    - frame=123
    - fps=30.0
    - out_time_ms=5000000 (microseconds)
    - progress=continue or progress=end

    Args:
        line: Single line from ffmpeg progress output

    Returns:
        Dictionary with parsed key-value pair, or None if not parseable
    """
    line = line.strip()
    if not line or "=" not in line:
        return None

    try:
        key, value = line.split("=", 1)
        return {key: value}
    except ValueError:
        return None


def calculate_percent(out_time_ms: int, total_ms: int) -> float:
    """Calculate progress percentage.

    Args:
        out_time_ms: Current output time in microseconds
        total_ms: Total expected output time in microseconds

    Returns:
        Progress percentage (0.0 to 100.0)
    """
    if total_ms <= 0:
        return 0.0
    return min(100.0, (out_time_ms / total_ms) * 100.0)


def parse_out_time_ms(value: str) -> int | None:
    """Parse out_time_ms value from progress output.

    Args:
        value: String value of out_time_ms

    Returns:
        Microseconds as integer, or None if invalid
    """
    try:
        return int(value)
    except ValueError:
        return None
