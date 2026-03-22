"""VSlicer - Frame-accurate video clipping tool.

Main application entry point.
"""

import argparse
import json
import shutil
import sys

from vslicer_core.clipboard import read_url_from_clipboard
from vslicer_core.config import (
    cleanup_temp_artifacts,
    get_config,
    get_config_summary,
    get_logger,
    setup_logging,
)
from vslicer_core.domain.models import ClipSpec
from vslicer_core.domain.validate import validate_url
from vslicer_core.mpv.client import MPVClient
from vslicer_core.mpv.ipc import create_transport, generate_ipc_path
from vslicer_core.mpv.process import MPVProcess
from vslicer_core.services.export import run_export as run_core_export
from vslicer_core.services.playback import build_clip_spec

from .ui.controls import display_prompt, parse_input
from .ui.prompts import confirm_export, prompt_export_options, prompt_url
from .ui.status import (
    console,
    display_help,
    display_playback_status,
    print_error,
    print_info,
    print_success,
)

logger = get_logger(__name__)
_CONFIG = get_config()


def check_dependencies() -> bool:
    """Check if required external dependencies are installed.

    Returns:
        True if all dependencies are available
    """
    missing = []

    if not shutil.which("mpv"):
        missing.append("mpv")

    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")

    if missing:
        print_error("Missing required dependencies:")
        for dep in missing:
            console.print(f"  - {dep}")

        console.print("\n[bold]Installation instructions:[/bold]")
        console.print("  Linux/WSL: sudo apt install mpv ffmpeg")
        console.print("  Windows: Download from mpv.io and ffmpeg.org")
        console.print("  macOS: brew install mpv ffmpeg")
        return False

    return True


def get_video_url(args: argparse.Namespace) -> str | None:
    """Get video URL from arguments, clipboard, or user input.

    Args:
        args: Command-line arguments

    Returns:
        Valid video URL or None
    """
    # Check command-line argument first
    if args.url:
        is_valid, error = validate_url(args.url, strict_webm=_CONFIG.strict_webm)
        if not is_valid:
            print_error(f"Invalid URL: {error}")
            return None
        return args.url

    # Try clipboard
    clipboard_url = read_url_from_clipboard(strict_webm=_CONFIG.strict_webm)
    if clipboard_url:
        print_info(f"Found URL in clipboard: {clipboard_url}")
        return clipboard_url

    # Prompt user
    url = prompt_url()
    is_valid, error = validate_url(url, strict_webm=_CONFIG.strict_webm)
    if not is_valid:
        print_error(f"Invalid URL: {error}")
        return None

    return url


def main_loop(client: MPVClient) -> ClipSpec | None:
    """Main control loop for video playback and IN/OUT marking.

    Args:
        client: Connected MPV client

    Returns:
        ClipSpec with IN/OUT points, or None if cancelled
    """
    in_mark: float | None = None
    out_mark: float | None = None
    paused = False

    console.print("\n" + "=" * 60, style="bold cyan")
    console.print("🎬 VIDEO LOADED - mpv window is open", style="bold green")
    console.print("=" * 60, style="bold cyan")
    console.print(
        "\n[bold yellow]⚠️  IMPORTANT: Type commands in THIS TERMINAL, not in the mpv window![/bold yellow]"
    )
    console.print(
        "[dim]The mpv window is for viewing only. All controls are here in the terminal.[/dim]\n"
    )
    display_help()

    while True:
        # Get current time
        time_pos = client.get_time_pos()
        if time_pos is None:
            time_pos = 0.0

        # Display status
        console.print("\n" + "=" * 60)
        display_playback_status(time_pos, in_mark, out_mark, paused)
        console.print("=" * 60)

        # Get user input
        try:
            user_input = display_prompt()
            action = parse_input(user_input)

            if action == "play_pause":
                if paused:
                    client.play()
                    paused = False
                    print_info("Playing")
                else:
                    client.pause()
                    paused = True
                    print_info("Paused")

            elif action == "frame_forward":
                if not paused:
                    client.pause()
                    paused = True
                client.frame_step()
                print_info("Frame step forward")

            elif action == "frame_backward":
                if not paused:
                    client.pause()
                    paused = True
                client.frame_back_step()
                print_info("Frame step backward")

            elif action == "mark_in":
                in_mark = client.get_time_pos()
                if in_mark is not None:
                    print_success(f"IN marked at {in_mark:.3f}s")
                else:
                    print_error("Could not get current time position")

            elif action == "mark_out":
                out_mark = client.get_time_pos()
                if out_mark is not None:
                    print_success(f"OUT marked at {out_mark:.3f}s")
                else:
                    print_error("Could not get current time position")

            elif action == "export":
                if in_mark is None or out_mark is None:
                    print_error("Please mark both IN and OUT points first")
                    continue

                try:
                    clip_spec = build_clip_spec(
                        url="", in_mark=in_mark, out_mark=out_mark
                    )
                except ValueError as exc:
                    print_error(f"Invalid clip: {exc}")
                    continue

                print_success("Ready to export!")
                return clip_spec

            elif action == "help":
                display_help()

            elif action == "quit":
                print_info("Quitting...")
                return None

            elif action == "unknown":
                print_error(f"Unknown command: {user_input}")
                print_info("Press 'h' for help")

        except KeyboardInterrupt:
            print_info("\nInterrupted. Press 'q' to quit.")
            continue
        except EOFError:
            print_info("\nQuitting...")
            return None


def run_export(url: str, clip_spec: ClipSpec) -> bool:
    """Run the export process.

    Args:
        url: Video URL
        clip_spec: Clip specification with IN/OUT points

    Returns:
        True if export succeeded
    """
    # Set URL in clip spec
    clip_spec.url = url

    # Get export options from user
    export_options = prompt_export_options(clip_spec)

    # Confirm with user
    if not confirm_export(clip_spec, export_options):
        print_info("Export cancelled")
        return False

    # Run export
    print_info("Starting export...")

    def progress_callback(data: dict):
        """Progress callback for export."""
        # Simple progress display
        if "out_time_ms" in data:
            console.print(".", end="", style="cyan")

    try:
        result = run_core_export(
            clip_spec,
            export_options,
            on_progress=progress_callback,
        )
    except ValueError as exc:
        print_error(f"Invalid export options: {exc}")
        return False

    console.print()  # New line after progress dots

    if result.ok:
        print_success(f"Export complete: {result.output_path}")
        return True
    else:
        print_error(f"Export failed: {result.error}")
        if result.ffmpeg_log:
            logger.error(f"FFmpeg log:\n{result.ffmpeg_log}")
        return False


def main() -> int:
    """Main entry point for VSlicer CLI.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    parser = argparse.ArgumentParser(
        description="VSlicer - Frame-accurate video clipping tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  vslicer https://example.com/video.webm
  vslicer  # Will try to read URL from clipboard
        """,
    )

    parser.add_argument("url", nargs="?", help="Video URL (optional)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print resolved configuration and exit",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(debug=args.debug)
    cleanup_temp_artifacts()
    if args.print_config:
        print(json.dumps(get_config_summary(), indent=2))
        return 0

    # Check dependencies
    if not check_dependencies():
        return 1

    # Get video URL
    url = get_video_url(args)
    if not url:
        return 1

    # Create IPC transport and path
    ipc_path = generate_ipc_path()
    transport = create_transport()

    # Start mpv process
    mpv_process = MPVProcess()

    try:
        print_info(f"Starting mpv with video: {url}")
        mpv_process.start(url, ipc_path)

        # Connect to mpv
        print_info("Connecting to mpv...")
        client = MPVClient(transport)
        client.connect(ipc_path)

        print_success("Connected to mpv!")

        # Main control loop
        clip_spec = main_loop(client)

        if clip_spec is None:
            print_info("No export requested")
            return 0

        # Export
        success = run_export(url, clip_spec)

        return 0 if success else 1

    except FileNotFoundError as e:
        print_error(str(e))
        return 1
    except RuntimeError as e:
        print_error(f"Runtime error: {e}")
        return 1
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        logger.exception("Unexpected error")
        return 1
    finally:
        # Cleanup
        if mpv_process.is_running():
            print_info("Stopping mpv...")
            mpv_process.stop()


if __name__ == "__main__":
    sys.exit(main())
