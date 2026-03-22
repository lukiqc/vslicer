"""mpv process lifecycle management.

Handles launching, monitoring, and terminating mpv player processes.
"""

import subprocess
import time
from pathlib import Path


class MPVProcess:
    """Manager for mpv player process."""

    def __init__(self):
        """Initialize mpv process manager."""
        self.process: subprocess.Popen | None = None
        self.ipc_path: str | None = None

    def start(
        self,
        url: str,
        ipc_path: str,
        additional_args: list[str] | None = None,
        embedded: bool = False,
        wid: int | None = None,
    ) -> bool:
        """Start mpv process with IPC server.

        Args:
            url: Video URL to play
            ipc_path: Path for IPC server (socket or named pipe)
            additional_args: Additional mpv arguments
            embedded: If True, run in embed mode without forcing a top-level window
            wid: Window ID to embed video into (uses --wid flag)

        Returns:
            True if started successfully

        Raises:
            FileNotFoundError: If mpv is not installed
            RuntimeError: If failed to start
        """
        self.ipc_path = ipc_path

        # Build mpv command
        cmd = ["mpv"]

        if wid is not None:
            # Embed into specified window
            cmd.append(f"--wid={wid}")
        elif not embedded:
            cmd.append("--force-window=yes")  # Always show window

        cmd.extend(
            [
                f"--input-ipc-server={ipc_path}",  # IPC server
                "--keep-open=yes",  # Keep open after playback ends
                "--no-terminal",  # Don't attach to terminal
                "--idle=yes",  # Stay open even without file
                "--demuxer-max-bytes=1GiB",  # Large cache for stream clipping
                "--demuxer-max-back-bytes=1GiB",  # Allow rewinding in streams
            ]
        )

        # Add any additional arguments
        if additional_args:
            cmd.extend(additional_args)

        # Add video URL last
        cmd.append(url)

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Give mpv time to start and create IPC server
            time.sleep(0.5)

            # Check if process started successfully
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"mpv process exited immediately with code {self.process.returncode}"
                )

            return True

        except FileNotFoundError as e:
            raise FileNotFoundError(
                "mpv not found. Please install mpv:\n"
                "  Linux/WSL: sudo apt install mpv\n"
                "  Windows: Download from mpv.io or use chocolatey\n"
                "  macOS: brew install mpv"
            ) from e

    def is_running(self) -> bool:
        """Check if mpv process is still running.

        Returns:
            True if process is running
        """
        if self.process is None:
            return False
        return self.process.poll() is None

    def stop(self, timeout: int = 5) -> bool:
        """Stop mpv process gracefully.

        Args:
            timeout: Timeout in seconds for graceful shutdown

        Returns:
            True if stopped successfully
        """
        if self.process is None:
            return True

        # Try graceful termination first
        self.process.terminate()

        try:
            self.process.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            # Force kill if graceful termination failed
            self.process.kill()
            self.process.wait()
            return True
        finally:
            self.process = None
            # Clean up IPC socket file if it exists (Unix sockets only)
            if self.ipc_path and self.ipc_path.startswith("/"):
                ipc_file = Path(self.ipc_path)
                if ipc_file.exists():
                    try:
                        ipc_file.unlink()
                    except OSError:
                        pass

    def __del__(self):
        """Cleanup on deletion."""
        if self.is_running():
            self.stop()
