"""mpv JSON IPC client.

Handles communication with mpv player via JSON IPC protocol.
"""

import json
import time
from typing import Any

from .ipc import IPCTransport


class MPVClient:
    """Client for controlling mpv via JSON IPC."""

    def __init__(self, transport: IPCTransport):
        """Initialize mpv client.

        Args:
            transport: IPC transport (socket or named pipe)
        """
        self.transport = transport
        self.request_id = 0

    def connect(self, ipc_path: str, timeout: int = 5) -> bool:
        """Connect to mpv IPC server.

        Args:
            ipc_path: Path to IPC endpoint (socket or pipe)
            timeout: Connection timeout in seconds

        Returns:
            True if connected successfully
        """
        start_time = time.time()
        last_error = None

        while time.time() - start_time < timeout:
            try:
                self.transport.connect(ipc_path)
                return True
            except (FileNotFoundError, ConnectionRefusedError, OSError) as e:
                last_error = e
                time.sleep(0.1)

        raise RuntimeError(
            f"Failed to connect to mpv IPC at {ipc_path} after {timeout}s: {last_error}"
        )

    def send_command(self, command: list, timeout: float = 2.0) -> dict | None:
        """Send a command to mpv and get response.

        Args:
            command: Command as list, e.g. ["get_property", "time-pos"]
            timeout: Timeout in seconds to wait for response

        Returns:
            Response dict or None if error
        """
        self.request_id += 1
        request = {"command": command, "request_id": self.request_id}

        # Send command
        request_json = json.dumps(request) + "\n"
        try:
            self.transport.send(request_json.encode("utf-8"))
        except (BrokenPipeError, OSError, RuntimeError):
            return None

        # Receive response with retry
        start_time = time.time()
        accumulated_data = b""

        while time.time() - start_time < timeout:
            try:
                response_data = self.transport.receive(4096)
                if response_data:
                    accumulated_data += response_data

                    # Try to parse accumulated data
                    response_str = accumulated_data.decode("utf-8")
                    for line in response_str.split("\n"):
                        if not line.strip():
                            continue
                        try:
                            response = json.loads(line)
                            # Match request_id
                            if response.get("request_id") == self.request_id:
                                return response
                        except json.JSONDecodeError:
                            continue

                # Small sleep to avoid busy waiting
                time.sleep(0.01)
            except (OSError, ConnectionError, UnicodeDecodeError):
                # If receive or decode fails, continue trying until timeout
                time.sleep(0.01)

        return None

    def get_property(self, name: str, timeout: float = 2.0) -> Any:
        """Get a property value from mpv.

        Args:
            name: Property name (e.g., "time-pos", "pause")
            timeout: Timeout in seconds to wait for response

        Returns:
            Property value, or None if error
        """
        response = self.send_command(["get_property", name], timeout=timeout)
        if response and response.get("error") == "success":
            return response.get("data")
        return None

    def set_property(self, name: str, value: Any) -> bool:
        """Set a property value in mpv.

        Args:
            name: Property name
            value: Property value

        Returns:
            True if successful
        """
        response = self.send_command(["set_property", name, value])
        return response is not None and response.get("error") == "success"

    def get_time_pos(self, timeout: float = 2.0) -> float | None:
        """Get current playback position in seconds."""
        return self.get_property("time-pos", timeout=timeout)

    def get_seekable_range(self, timeout: float = 0.5) -> tuple[float, float] | None:
        """Get the seekable range from demuxer cache.

        This is useful for livestreams where duration is unavailable but
        we can still seek within the cached content.

        Returns:
            Tuple of (start, end) in seconds, or None if unavailable
        """
        cache_state = self.get_property("demuxer-cache-state", timeout=timeout)
        if not cache_state or not isinstance(cache_state, dict):
            return None
        ranges = cache_state.get("seekable-ranges")
        if not ranges or not isinstance(ranges, list) or len(ranges) == 0:
            return None
        # Use the first (usually only) range
        first_range = ranges[0]
        if not isinstance(first_range, dict):
            return None
        start = first_range.get("start")
        end = first_range.get("end")
        if start is None or end is None:
            return None
        return (float(start), float(end))

    def pause(self) -> bool:
        """Pause playback."""
        return self.set_property("pause", True)

    def play(self) -> bool:
        """Resume playback."""
        return self.set_property("pause", False)

    def frame_step(self) -> bool:
        """Step forward one frame."""
        response = self.send_command(["frame-step"])
        return response is not None and response.get("error") == "success"

    def frame_back_step(self) -> bool:
        """Step backward one frame."""
        response = self.send_command(["frame-back-step"])
        return response is not None and response.get("error") == "success"

    def seek(self, time: float, mode: str = "absolute") -> bool:
        """Seek to a specific time.

        Args:
            time: Time in seconds
            mode: Seek mode ("absolute", "relative", "relative-percent")

        Returns:
            True if successful
        """
        response = self.send_command(["seek", time, mode])
        return response is not None and response.get("error") == "success"

    def quit(self) -> bool:
        """Quit mpv."""
        response = self.send_command(["quit"])
        return response is not None

    def ab_loop_align_cache(self) -> bool:
        """Align A-B loop points to keyframes in the cache.

        This should be called before ab_loop_dump_cache to ensure the
        loop points align with actual keyframe boundaries, preventing
        frame loss and timing issues.

        Returns:
            True if successful
        """
        response = self.send_command(["ab-loop-align-cache"], timeout=5.0)
        return response is not None and response.get("error") == "success"

    def ab_loop_dump_cache(self, output_path: str) -> bool:
        """Dump demuxer cache using current A-B loop points.

        This is the preferred method for exporting clips from livestreams.
        It uses the same A-B loop points that define the preview loop,
        ensuring the exported content matches exactly what was previewed.

        The A-B loop points should already be set via set_property before
        calling this method. Call ab_loop_align_cache first to align
        the points to keyframes.

        Args:
            output_path: Path to write the dumped cache

        Returns:
            True if successful
        """
        response = self.send_command(["ab-loop-dump-cache", output_path], timeout=60.0)
        return response is not None and response.get("error") == "success"

    def close(self) -> None:
        """Close the IPC connection."""
        self.transport.close()
