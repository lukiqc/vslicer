"""User input prompts for VSlicer.

Uses rich library for interactive prompts.
"""

import datetime
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt

from vslicer_core.domain.models import ClipSpec, ExportOptions, SlowMoOptions

console = Console()


def prompt_url() -> str:
    """Prompt user for video URL.

    Returns:
        Video URL
    """
    return Prompt.ask("[cyan]Enter video URL[/cyan]")


def prompt_export_options(spec: ClipSpec) -> ExportOptions:
    """Prompt user for export options.

    Args:
        spec: ClipSpec with IN/OUT points

    Returns:
        ExportOptions configured by user
    """
    console.print("\n[bold]Export Configuration[/bold]\n")

    # Export type
    console.print("Export type:")
    console.print("  [1] Video")
    console.print("  [2] Audio-only (MP3)")
    export_type_choice = Prompt.ask("Choose type", choices=["1", "2"], default="1")
    output_type = "audio" if export_type_choice == "2" else "video"

    # Slow motion (ask first to determine mode)
    slowmo = None
    if Confirm.ask("Apply slow-motion?", default=False):
        slowmo = prompt_slowmo_options(spec)
        if output_type == "audio" and slowmo and slowmo.audio_policy == "mute":
            console.print(
                "[yellow]Audio-only export cannot mute audio. Using Stretch.[/yellow]"
            )
            from dataclasses import replace

            slowmo = replace(slowmo, audio_policy="stretch")

    if output_type == "audio":
        mode = "accurate_reencode"
        extension = ".mp3"
    else:
        # Export mode
        console.print("\nExport mode:")

        if slowmo is not None:
            console.print(
                "  [yellow]⚠️  Slow-motion requires re-encoding (accurate mode)[/yellow]"
            )
            console.print(
                "  [2] Accurate (re-encode, VP9 .webm) - [bold]Required for slow-motion[/bold]"
            )
            mode = "accurate_reencode"
        else:
            console.print("  [1] Fast (stream copy, keep original codec, .mp4)")
            console.print("  [2] Accurate (re-encode, VP9 .webm, slower)")

            mode_choice = Prompt.ask(
                "Choose mode",
                choices=["1", "2"],
                default="2",
            )

            mode = "fast_copy" if mode_choice == "1" else "accurate_reencode"

        # Determine file extension based on mode
        extension = ".mp4" if mode == "fast_copy" else ".webm"

    # Output filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    default_filename = f"clip_{timestamp}{extension}"

    filename = Prompt.ask(
        f"Output filename (will be {extension})",
        default=default_filename,
    )

    # Ensure correct extension
    filename = Path(filename)
    if filename.suffix.lower() not in [extension]:
        console.print(
            f"[yellow]Note: Changing extension to {extension} for {mode} mode[/yellow]"
        )
        filename = filename.with_suffix(extension)

    # Output directory
    default_dir = "./clips"
    output_dir_str = Prompt.ask(
        "Output directory",
        default=default_dir,
    )
    output_dir = Path(output_dir_str)

    # Create directory if it doesn't exist
    if not output_dir.exists():
        if Confirm.ask(f"Directory '{output_dir}' doesn't exist. Create it?"):
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            console.print("[yellow]Using current directory instead[/yellow]")
            output_dir = Path()

    output_path = output_dir / filename

    return ExportOptions(
        output_type=output_type,
        mode=mode,
        output_path=output_path,
        slowmo=slowmo,
        include_audio=True,
    )


def prompt_slowmo_options(spec: ClipSpec) -> SlowMoOptions | None:
    """Prompt user for slow-motion options.

    Args:
        spec: ClipSpec for duration calculation

    Returns:
        SlowMoOptions or None
    """
    console.print("\n[bold]Slow Motion Configuration[/bold]\n")
    console.print(f"Clip duration: {spec.duration:.2f}s")
    console.print("\nChoose slow-motion method:")
    console.print("  [1] Factor (e.g., 2x, 5x slower)")
    console.print("  [2] Target duration (specify output length)")

    choice = Prompt.ask("Choose method", choices=["1", "2"], default="1")

    if choice == "1":
        factor_str = Prompt.ask(
            "Slow-motion factor (e.g., 2.0 for 2x slower)",
            default="2.0",
        )
        try:
            factor = float(factor_str)
            if factor <= 0:
                console.print("[red]Invalid factor, using 2.0[/red]")
                factor = 2.0
        except ValueError:
            console.print("[red]Invalid input, using 2.0[/red]")
            factor = 2.0

        audio_policy = prompt_audio_policy(factor)

        return SlowMoOptions(factor=factor, audio_policy=audio_policy)

    else:  # Target duration
        target_str = Prompt.ask(
            f"Target duration in seconds (original: {spec.duration:.2f}s)",
            default=f"{spec.duration * 2:.2f}",
        )
        try:
            target_duration = float(target_str)
            if target_duration <= 0:
                console.print("[red]Invalid duration, using 2x original[/red]")
                target_duration = spec.duration * 2
        except ValueError:
            console.print("[red]Invalid input, using 2x original[/red]")
            target_duration = spec.duration * 2

        factor = target_duration / spec.duration
        audio_policy = prompt_audio_policy(factor)

        return SlowMoOptions(target_duration=target_duration, audio_policy=audio_policy)


def prompt_audio_policy(factor: float) -> str:
    """Prompt user for audio handling policy.

    Args:
        factor: Slow-motion factor

    Returns:
        Audio policy: "stretch", "mute", or "drop"
    """
    console.print("\n[bold]Audio Handling[/bold]")

    if factor > 10.0:
        console.print(
            f"[yellow]Warning: {factor}x slow-motion may not support audio stretching[/yellow]"
        )
        console.print("Recommend muting audio for extreme slow-motion")

    console.print("\n  [1] Stretch audio (preserve audio)")
    console.print("  [2] Mute audio (no sound)")
    console.print("  [3] Drop if unsupported (auto-decide)")

    choice = Prompt.ask("Choose audio policy", choices=["1", "2", "3"], default="1")

    policy_map = {
        "1": "stretch",
        "2": "mute",
        "3": "drop",
    }

    return policy_map[choice]


def confirm_export(spec: ClipSpec, options: ExportOptions) -> bool:
    """Confirm export settings with user.

    Args:
        spec: ClipSpec to export
        options: Export options

    Returns:
        True if user confirms
    """
    console.print("\n[bold]Export Summary[/bold]")
    console.print(f"  Duration: {spec.duration:.2f}s")
    console.print(f"  Type: {options.output_type}")
    console.print(f"  Mode: {options.mode}")
    console.print(f"  Output: {options.output_path}")

    if options.slowmo:
        factor = options.slowmo.compute_factor(spec.duration)
        console.print(f"  Slow-motion: {factor:.2f}x")
        console.print(f"  Audio: {options.slowmo.audio_policy}")

    return Confirm.ask("\nProceed with export?", default=True)
