"""FFmpeg command builder and execution.

Handles building ffmpeg commands for video export and running them with progress tracking.
"""

import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from ..config import get_config
from ..domain.models import ClipSpec, ExportOptions, ExportResult
from .filters import build_audio_filter, build_crop_filter, build_video_filter
from .progress import parse_progress_line


def get_video_duration(path: str) -> float | None:
    """Get video duration using ffprobe.

    Args:
        path: Video file path

    Returns:
        Duration in seconds, or None if it cannot be determined
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return None

        output = result.stdout.strip()
        if not output:
            return None

        return float(output)

    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None


def get_video_dimensions(url: str) -> tuple[int, int]:
    """Get video dimensions using ffprobe.

    Args:
        url: Video URL or file path

    Returns:
        Tuple of (width, height) in pixels

    Raises:
        RuntimeError: If ffprobe fails or dimensions cannot be parsed
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0",
        url,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "Server returned" in stderr or "HTTP error" in stderr:
                raise RuntimeError(f"Failed to access video URL: {stderr}")
            raise RuntimeError(f"ffprobe failed: {stderr}")

        output = result.stdout.strip()
        if not output:
            raise RuntimeError("ffprobe returned empty output")

        parts = output.split(",")
        if len(parts) != 2:
            raise RuntimeError(f"Unexpected ffprobe output: {output}")

        width = int(parts[0])
        height = int(parts[1])
        return width, height

    except FileNotFoundError as e:
        raise RuntimeError("ffprobe not found. Please install ffmpeg.") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("ffprobe timed out") from e
    except ValueError as e:
        raise RuntimeError(f"Failed to parse video dimensions: {e}") from e


def build_ffmpeg_command(
    spec: ClipSpec, options: ExportOptions, audio_url: str | None = None
) -> list[str]:
    """Build ffmpeg command for exporting a clip.

    Args:
        spec: Clip specification with URL and IN/OUT times
        options: Export options (mode, slowmo, output path, etc.)

    Returns:
        List of command arguments for subprocess
    """
    audio_only = options.output_type == "audio"

    # CRITICAL: Force accurate mode if slow-motion or crop is present
    # Stream copy (fast_copy) cannot be used with filters
    if (
        options.slowmo is not None or options.crop is not None
    ) and options.mode == "fast_copy":
        # Override mode - create new options object
        from dataclasses import replace

        options = replace(options, mode="accurate_reencode")

    cmd = ["ffmpeg", "-y"]  # -y to overwrite (we check beforehand)

    # Input with timestamps
    cmd.extend(["-ss", str(spec.in_time)])
    cmd.extend(["-to", str(spec.out_time)])
    cmd.extend(["-i", spec.url])

    # Calculate slow-motion factor if present
    slowmo_factor = None
    if options.slowmo is not None:
        slowmo_factor = options.slowmo.compute_factor(spec.duration)

    # Base video filter chain
    video_filter = ""
    if not audio_only:
        video_filters = []

        # Add crop filter first (before scale/other filters)
        if options.crop is not None:
            source_width, source_height = get_video_dimensions(spec.url)
            crop_filter = build_crop_filter(
                options.crop.aspect_ratio,
                options.crop.position,
                source_width,
                source_height,
                custom_width_ratio=options.crop.custom_width_ratio,
            )
            video_filters.append(crop_filter)

        if options.video_filter:
            video_filters.append(options.video_filter)
        slowmo_video_filter = build_video_filter(slowmo_factor)
        if slowmo_video_filter:
            video_filters.append(slowmo_video_filter)
        video_filter = ",".join(video_filters) if video_filters else ""

    # Base audio filter chain
    audio_filter = build_audio_filter(slowmo_factor)

    playback_mode = options.playback_mode
    include_audio = True if audio_only else options.include_audio
    include_audio = include_audio and not (
        options.slowmo and options.slowmo.audio_policy == "mute"
    )
    has_separate_audio = audio_url is not None and include_audio
    if has_separate_audio:
        cmd.extend(["-ss", str(spec.in_time)])
        cmd.extend(["-to", str(spec.out_time)])
        cmd.extend(["-i", audio_url])

    # Apply reverse playback filters when requested
    if playback_mode == "reverse":
        video_filter = ",".join(filter(None, [video_filter, "reverse"]))
        if audio_filter:
            audio_filter = ",".join([audio_filter, "areverse"])
        else:
            audio_filter = "areverse"

    use_filter_complex = playback_mode == "pingpong"
    if use_filter_complex:
        filter_parts = []

        if not audio_only:
            if video_filter:
                filter_parts.append(f"[0:v]{video_filter}[v0]")
                video_source = "[v0]"
            else:
                video_source = "[0:v]"

            filter_parts.append(f"{video_source}split=2[vf][vr]")
            filter_parts.append("[vr]reverse[vr2]")
            filter_parts.append("[vf][vr2]concat=n=2:v=1:a=0[vout]")

        audio_map = None
        if include_audio:
            audio_input = "[1:a]" if has_separate_audio else "[0:a]"
            if audio_filter:
                filter_parts.append(f"{audio_input}{audio_filter}[a0]")
                audio_source = "[a0]"
            else:
                audio_source = audio_input

            filter_parts.append(f"{audio_source}asplit=2[af][ar]")
            filter_parts.append("[ar]areverse[ar2]")
            filter_parts.append("[af][ar2]concat=n=2:v=0:a=1[aout]")
            audio_map = "[aout]"

        cmd.extend(["-filter_complex", ";".join(filter_parts)])
        if not audio_only:
            cmd.extend(["-map", "[vout]"])
        if audio_map:
            cmd.extend(["-map", audio_map])
        else:
            cmd.append("-an")
        if audio_only:
            cmd.append("-vn")
    else:
        if video_filter:
            cmd.extend(["-vf", video_filter])

        # Add audio filter or mute based on options
        if not include_audio:
            cmd.append("-an")  # No audio
        else:
            if audio_filter:
                cmd.extend(["-af", audio_filter])
            if has_separate_audio:
                if audio_only:
                    cmd.extend(["-map", "1:a:0"])
                else:
                    cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])
        if audio_only:
            cmd.append("-vn")

    # Codec settings
    # Force accurate mode if filters are present (can't use stream copy with filters)
    has_filters = bool(
        video_filter or audio_filter or use_filter_complex or options.crop
    )
    if audio_only:
        cmd.extend(["-c:a", "libmp3lame", "-q:a", "2"])
    else:
        if options.mode == "fast_copy" and not has_filters:
            cmd.extend(["-c", "copy"])
        else:  # accurate_reencode
            cmd.extend(["-c:v", "libvpx-vp9"])
            cmd.extend(["-crf", "32"])
            cmd.extend(["-b:v", "0"])
            if options.include_audio and not (
                options.slowmo and options.slowmo.audio_policy == "mute"
            ):
                cmd.extend(["-c:a", "libvorbis"])

    # Progress reporting
    cmd.extend(["-progress", "pipe:1", "-nostats"])

    # Output file
    cmd.append(str(options.output_path))

    return cmd


def run_ffmpeg(
    cmd: list[str],
    on_progress: Callable[[dict], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> ExportResult:
    """Run ffmpeg command with progress tracking.

    Args:
        cmd: FFmpeg command arguments
        on_progress: Optional callback called with progress dict

    Returns:
        ExportResult with success status and output path or error
    """
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        stderr_output: list[str] = []

        def read_stdout() -> None:
            if not process.stdout:
                return
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                progress_data = parse_progress_line(line)
                if progress_data and on_progress:
                    on_progress(progress_data)

        def read_stderr() -> None:
            if not process.stderr:
                return
            for line in process.stderr:
                stderr_output.append(line)

        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        timeout = get_config().ffmpeg_timeout_seconds or None
        start_time = time.time()
        return_code = None
        while True:
            if cancel_event and cancel_event.is_set():
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                stdout_thread.join(timeout=1)
                stderr_thread.join(timeout=1)
                error_msg = "".join(stderr_output) if stderr_output else "Canceled"
                return ExportResult(
                    ok=False,
                    error="Export canceled",
                    ffmpeg_log=error_msg,
                )
            if timeout is not None and (time.time() - start_time) > timeout:
                process.kill()
                process.wait()
                stdout_thread.join(timeout=1)
                stderr_thread.join(timeout=1)
                error_msg = "".join(stderr_output) if stderr_output else "Timed out"
                return ExportResult(
                    ok=False,
                    error="FFmpeg timed out",
                    ffmpeg_log=error_msg,
                )
            try:
                return_code = process.wait(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                continue
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)

        if return_code != 0:
            error_msg = "".join(stderr_output) if stderr_output else "Unknown error"
            return ExportResult(
                ok=False,
                error=f"FFmpeg failed with code {return_code}",
                ffmpeg_log=error_msg,
            )

        # Success - find output path from command
        output_path = Path(cmd[-1])
        return ExportResult(
            ok=True,
            output_path=output_path,
            ffmpeg_log="".join(stderr_output) if stderr_output else None,
        )

    except FileNotFoundError:
        return ExportResult(
            ok=False,
            error="ffmpeg not found. Please install ffmpeg.",
        )
    except Exception as e:
        return ExportResult(
            ok=False,
            error=f"Unexpected error running ffmpeg: {e}",
        )
