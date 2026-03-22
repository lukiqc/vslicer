"""Validation functions for VSlicer domain models."""

import ipaddress
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from ..config import get_config
from .models import ClipSpec, ExportOptions

# Security limits
MAX_URL_LENGTH = 8192  # Prevent DoS via extremely long URLs
ALLOWED_VIDEO_EXTENSIONS = {
    ".3g2",
    ".3gp",
    ".avi",
    ".flv",
    ".m2ts",
    ".m3u8",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpd",
    ".mpeg",
    ".mpg",
    ".mts",
    ".ogv",
    ".ts",
    ".webm",
    ".wmv",
}


def _host_matches(host: str, entry: str) -> bool:
    if entry.startswith("."):
        return host.endswith(entry)
    return host == entry


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _probe_remote_video(url: str) -> tuple[bool, str]:
    config = get_config()
    for stream_selector in ("v:0", "a:0"):
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    stream_selector,
                    "-show_entries",
                    "stream=codec_type",
                    "-of",
                    "csv=p=0",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=config.ffprobe_timeout_seconds,
            )
        except FileNotFoundError:
            return False, "ffprobe not found. Please install ffmpeg."
        except subprocess.TimeoutExpired:
            return False, "ffprobe timed out while probing the URL"

        if result.returncode == 0 and result.stdout.strip():
            return True, ""

    return False, "URL does not contain a readable video or audio stream"


def validate_url(
    url: str,
    strict_webm: bool = False,
    allow_file: bool = False,
    allowed_hosts: tuple[str, ...] | None = None,
    blocked_hosts: tuple[str, ...] | None = None,
    local_only: bool | None = None,
) -> tuple[bool, str]:
    """Validate a video URL.

    Args:
        url: URL to validate
        strict_webm: If True, require .webm extension
        allow_file: If True, allow file:// URLs (disabled by default for security)

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
    """
    # Check URL length to prevent DoS
    if len(url) > MAX_URL_LENGTH:
        return False, f"URL exceeds maximum length of {MAX_URL_LENGTH} characters"

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL format: {e}"

    config = get_config()
    if allowed_hosts is None:
        allowed_hosts = config.allowed_hosts
    if blocked_hosts is None:
        blocked_hosts = config.blocked_hosts
    if local_only is None:
        local_only = config.local_only

    # Determine allowed schemes
    allowed_schemes = ["http", "https"]
    if allow_file:
        allowed_schemes.append("file")

    if parsed.scheme not in allowed_schemes:
        scheme_list = ", ".join(allowed_schemes)
        return False, f"URL must use {scheme_list}, got: {parsed.scheme}"

    # file:// URLs don't need netloc, but http/https do
    if parsed.scheme in ("http", "https") and not parsed.netloc:
        return False, "URL must have a network location (domain)"

    if parsed.scheme in ("http", "https"):
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            return False, "URL must have a valid hostname"

        if local_only and not _is_loopback(host):
            return (
                False,
                "URL must resolve to localhost when local-only mode is enabled",
            )

        if blocked_hosts and any(_host_matches(host, entry) for entry in blocked_hosts):
            return False, "URL host is blocked by policy"

        if allowed_hosts and not any(
            _host_matches(host, entry) for entry in allowed_hosts
        ):
            return False, "URL host is not in the allowed list"

        extension = Path(parsed.path).suffix.lower()
        if extension and extension not in ALLOWED_VIDEO_EXTENSIONS:
            return False, "URL does not appear to target a video resource"

        if config.validate_remote_media and extension in ALLOWED_VIDEO_EXTENSIONS:
            ok, error = _probe_remote_video(url)
            if not ok:
                return False, error

    if strict_webm and not parsed.path.lower().endswith(".webm"):
        return (
            False,
            "URL must point to a .webm file (use strict_webm=False to allow other formats)",
        )

    return True, ""


def _probe_local_video(path: Path) -> tuple[bool, str]:
    config = get_config()
    for stream_selector in ("v:0", "a:0"):
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    stream_selector,
                    "-show_entries",
                    "stream=codec_type",
                    "-of",
                    "csv=p=0",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=config.ffprobe_timeout_seconds,
            )
        except FileNotFoundError:
            return False, "ffprobe not found. Please install ffmpeg."
        except subprocess.TimeoutExpired:
            return False, "ffprobe timed out while probing the media file"

        if result.returncode == 0 and result.stdout.strip():
            return True, ""

    return False, "File does not contain a readable video or audio stream"


def validate_local_media_path(path: Path, probe: bool = True) -> tuple[bool, str]:
    """Validate a local media file path.

    Args:
        path: Local file path to validate
        probe: If True, run ffprobe to confirm a video stream exists

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
    """
    if not path.exists():
        return False, f"File not found: {path}"
    if not path.is_file():
        return False, f"Path is not a file: {path}"

    extension = path.suffix.lower()
    if extension and extension not in ALLOWED_VIDEO_EXTENSIONS:
        return False, "File does not appear to be a supported media format"

    if probe:
        return _probe_local_video(path)

    return True, ""


def validate_clip_spec(spec: ClipSpec, min_duration: float = 0.05) -> tuple[bool, str]:
    """Validate a ClipSpec.

    Args:
        spec: ClipSpec to validate
        min_duration: Minimum allowed duration in seconds

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
    """
    if spec.in_time < 0:
        return False, f"IN time must be non-negative, got {spec.in_time}"

    if spec.out_time < 0:
        return False, f"OUT time must be non-negative, got {spec.out_time}"

    if spec.out_time <= spec.in_time:
        return (
            False,
            f"OUT time ({spec.out_time}) must be after IN time ({spec.in_time})",
        )

    duration = spec.duration
    if duration < min_duration:
        return (
            False,
            f"Clip duration ({duration:.3f}s) is below minimum ({min_duration}s)",
        )

    return True, ""


def validate_output_path(
    output_path: Path, base_dir: Path | None = None
) -> tuple[bool, str]:
    """Validate an output file path for security.

    Args:
        output_path: Path to validate
        base_dir: If provided, ensure output stays within this directory

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
    """
    # Resolve to absolute path to detect traversal
    try:
        resolved = output_path.resolve()
    except (OSError, ValueError) as e:
        return False, f"Invalid output path: {e}"

    # Check for path traversal if base_dir is specified
    if base_dir is not None:
        try:
            base_resolved = base_dir.resolve()
            # Ensure the resolved path starts with the base directory
            resolved.relative_to(base_resolved)
        except ValueError:
            return False, f"Output path escapes base directory: {output_path}"

    # Check for suspicious path components
    path_str = str(output_path)
    if ".." in path_str:
        # Double-check: the resolved path should not have changed significantly
        if resolved != output_path.absolute():
            return False, "Path traversal detected in output path"

    return True, ""


def validate_export_options(
    options: ExportOptions, base_dir: Path | None = None
) -> tuple[bool, str]:
    """Validate export options.

    Args:
        options: ExportOptions to validate
        base_dir: If provided, ensure output stays within this directory

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
    """
    # Check output path
    output_path = options.output_path

    # Validate path for security issues
    path_valid, path_error = validate_output_path(output_path, base_dir)
    if not path_valid:
        return False, path_error

    # Check if parent directory exists
    parent_dir = output_path.parent
    if not parent_dir.exists():
        return False, f"Output directory does not exist: {parent_dir}"

    if not parent_dir.is_dir():
        return False, f"Output parent path is not a directory: {parent_dir}"

    # Check if file already exists
    if output_path.exists():
        return False, f"Output file already exists (will not overwrite): {output_path}"

    if options.output_type == "audio" and not options.include_audio:
        return False, "Audio-only export requires audio to be enabled"

    if options.output_type == "audio" and output_path.suffix.lower() != ".mp3":
        return False, "Audio-only export requires a .mp3 output filename"

    # Check if directory is writable (approximate check)
    if not parent_dir.stat().st_mode & 0o200:  # Owner write bit
        return False, f"Output directory is not writable: {parent_dir}"

    # Validate slowmo options if present
    if options.slowmo is not None:
        try:
            # This will validate via SlowMoOptions.__post_init__
            pass  # Already validated in dataclass
        except ValueError as e:
            return False, f"Invalid slow-motion options: {e}"

    if options.output_type == "audio" and options.slowmo is not None:
        if options.slowmo.audio_policy == "mute":
            return False, "Audio-only export cannot mute audio"

    return True, ""
