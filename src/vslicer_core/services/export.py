"""Export-related helpers.

Keeps ffmpeg wiring and validation in one place for both CLI and GUI.
"""

import shutil
import subprocess
import threading
import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

from ..config import (
    get_config,
    get_cookies_browser,
    get_logger,
    get_media_access_policy,
)
from ..domain.models import ClipSpec, ExportOptions, ExportResult
from ..domain.validate import ALLOWED_VIDEO_EXTENSIONS, validate_export_options
from ..export.ffmpeg import build_ffmpeg_command, run_ffmpeg


def _is_direct_media_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https", "", "file"):
        return False
    extension = Path(parsed.path).suffix.lower()
    return bool(extension and extension in ALLOWED_VIDEO_EXTENSIONS)


def _resolve_media_urls(
    url: str, include_audio: bool, audio_only: bool
) -> tuple[str | None, str | None]:
    if shutil.which("yt-dlp") is None:
        return None, None
    if audio_only:
        fmt = "bestaudio/best"
    else:
        fmt = "bestvideo+bestaudio/best" if include_audio else "bestvideo/best"
    config = get_config()
    timeout = config.ytdlp_timeout_seconds or None
    extra_args: list[str] = []
    if config.enable_cookie_fallback and get_media_access_policy() == "allow":
        extra_args.extend(["--cookies-from-browser", get_cookies_browser()])
    try:
        result = subprocess.run(
            ["yt-dlp", "-f", fmt, "-g", *extra_args, url],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return None, None
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return None, None
    if include_audio and len(lines) >= 2:
        return lines[0], lines[1]
    return lines[0], None


def resolve_input_urls(
    url: str, include_audio: bool, audio_only: bool
) -> tuple[str, str | None]:
    """Resolve URLs that require external helpers (e.g., Instagram/YouTube pages)."""
    if _is_direct_media_url(url):
        return url, None

    video_url, audio_url = _resolve_media_urls(
        url, include_audio=include_audio, audio_only=audio_only
    )
    if video_url:
        if audio_only:
            return video_url, None
        return video_url, audio_url

    logger = get_logger(__name__)
    logger.warning(
        "Failed to resolve URL via yt-dlp; using original URL",
        extra={"event_id": "export.resolve_failed", "url": url[:200]},
    )
    return url, None


def build_export_command(spec: ClipSpec, options: ExportOptions) -> list[str]:
    """Build an ffmpeg command after validating export options.

    Args:
        spec: ClipSpec to export
        options: Export options

    Returns:
        ffmpeg command list

    Raises:
        ValueError: If export options are invalid
    """
    is_valid, error = validate_export_options(options)
    if not is_valid:
        raise ValueError(error)
    resolved_video, resolved_audio = resolve_input_urls(
        spec.url,
        include_audio=options.include_audio,
        audio_only=options.output_type == "audio",
    )
    resolved_spec = replace(spec, url=resolved_video)
    return build_ffmpeg_command(resolved_spec, options, audio_url=resolved_audio)


def run_export(
    spec: ClipSpec,
    options: ExportOptions,
    on_progress: Callable[[dict], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> ExportResult:
    """Validate, build, and run an export.

    Args:
        spec: ClipSpec to export
        options: Export options
        on_progress: Optional progress callback

    Returns:
        ExportResult

    Raises:
        ValueError: If export options are invalid
    """
    logger = get_logger(__name__)
    context_id = uuid.uuid4().hex
    logger.info(
        "Export started",
        extra={
            "event_id": "export.start",
            "context_id": context_id,
            "output_path": str(options.output_path),
            "mode": options.mode,
            "playback_mode": options.playback_mode,
        },
    )
    try:
        cmd = build_export_command(spec, options)
    except ValueError as exc:
        logger.error(
            "Export failed",
            extra={
                "event_id": "export.fail",
                "context_id": context_id,
                "error": str(exc),
                "output_path": str(options.output_path),
            },
        )
        raise

    result = run_ffmpeg(cmd, on_progress=on_progress, cancel_event=cancel_event)
    if result.ok:
        logger.info(
            "Export completed",
            extra={
                "event_id": "export.complete",
                "context_id": context_id,
                "output_path": str(result.output_path),
            },
        )
    else:
        logger.error(
            "Export failed",
            extra={
                "event_id": "export.fail",
                "context_id": context_id,
                "error": result.error,
                "output_path": str(options.output_path),
            },
        )
    return result
