"""Status display for VSlicer UI.

Uses rich library for formatted terminal output.
"""

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

console = Console()


def display_playback_status(
    time_pos: float,
    in_mark: float | None,
    out_mark: float | None,
    paused: bool = False,
) -> None:
    """Display current playback status.

    Args:
        time_pos: Current playback position in seconds
        in_mark: IN mark position in seconds, or None if not set
        out_mark: OUT mark position in seconds, or None if not set
        paused: Whether playback is paused
    """
    table = Table(show_header=False, box=None, padding=(0, 2))

    # Current time
    status_icon = "⏸️ " if paused else "▶️ "
    table.add_row("Time:", f"{status_icon}{format_time(time_pos)}")

    # IN mark
    if in_mark is not None:
        table.add_row("IN:", f"[green]{format_time(in_mark)}[/green]")
    else:
        table.add_row("IN:", "[dim]Not set (press 'i')[/dim]")

    # OUT mark
    if out_mark is not None:
        table.add_row("OUT:", f"[red]{format_time(out_mark)}[/red]")
    else:
        table.add_row("OUT:", "[dim]Not set (press 'o')[/dim]")

    # Duration if both marks set
    if in_mark is not None and out_mark is not None:
        duration = out_mark - in_mark
        table.add_row("Duration:", f"[yellow]{format_time(duration)}[/yellow]")

    console.print(table)


def display_export_progress(
    percent: float,
    time_remaining: int | None = None,
    message: str = "Exporting...",
) -> None:
    """Display export progress.

    Args:
        percent: Progress percentage (0-100)
        time_remaining: Estimated time remaining in seconds
        message: Status message
    """
    progress_bar = "█" * int(percent / 2) + "░" * (50 - int(percent / 2))

    status_line = f"{message} [{progress_bar}] {percent:.1f}%"

    if time_remaining is not None:
        status_line += f" (ETA: {time_remaining}s)"

    console.print(status_line, end="\r")


def create_export_progress() -> Progress:
    """Create a Rich progress bar for export.

    Returns:
        Progress object for tracking export
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


def format_time(seconds: float) -> str:
    """Format time in seconds as HH:MM:SS.mmm.

    Args:
        seconds: Time in seconds

    Returns:
        Formatted time string
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    else:
        return f"{minutes:02d}:{secs:06.3f}"


def print_error(message: str) -> None:
    """Print error message in red.

    Args:
        message: Error message
    """
    console.print(f"[bold red]Error:[/bold red] {message}")


def print_success(message: str) -> None:
    """Print success message in green.

    Args:
        message: Success message
    """
    console.print(f"[bold green]✓[/bold green] {message}")


def print_info(message: str) -> None:
    """Print info message.

    Args:
        message: Info message
    """
    console.print(f"[bold cyan]ℹ[/bold cyan] {message}")


def clear_screen() -> None:
    """Clear the console screen."""
    console.clear()


def display_help() -> None:
    """Display keyboard shortcuts help."""
    table = Table(
        title="Commands (Type in TERMINAL, then press Enter)", show_header=True
    )
    table.add_column("Type", style="cyan", width=10)
    table.add_column("Action", style="white")

    table.add_row("space", "Play/Pause")
    table.add_row(".", "Frame step forward")
    table.add_row(",", "Frame step backward")
    table.add_row("i", "Set IN point")
    table.add_row("o", "Set OUT point")
    table.add_row("e", "Export clip")
    table.add_row("h", "Show this help")
    table.add_row("q", "Quit")

    console.print(table)
    console.print(
        "\n[dim]Note: Type commands here in the terminal and press Enter.[/dim]"
    )
    console.print(
        "[dim]The mpv window is for viewing only. Space/./, also work in mpv.[/dim]"
    )
