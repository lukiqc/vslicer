"""Platform abstraction for mpv IPC communication.

Handles Unix sockets (Linux/WSL) and named pipes (Windows) for mpv JSON IPC.
"""

import os
import platform
import secrets
import socket
import tempfile
from abc import ABC, abstractmethod


class IPCTransport(ABC):
    """Abstract base class for IPC transport."""

    @abstractmethod
    def connect(self, path: str) -> None:
        """Connect to the IPC endpoint."""
        pass

    @abstractmethod
    def send(self, data: bytes) -> None:
        """Send data to the IPC endpoint."""
        pass

    @abstractmethod
    def receive(self, buffer_size: int = 4096) -> bytes:
        """Receive data from the IPC endpoint."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the IPC connection."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected."""
        pass


class UnixSocketTransport(IPCTransport):
    """Unix domain socket transport for Linux/WSL."""

    def __init__(self):
        self.sock: socket.socket | None = None
        self._connected = False

    def connect(self, path: str) -> None:
        """Connect to Unix socket."""
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path)
        # Set socket to non-blocking mode
        self.sock.setblocking(False)
        self._connected = True

    def send(self, data: bytes) -> None:
        """Send data over socket."""
        if not self.sock:
            raise RuntimeError("Not connected")
        self.sock.sendall(data)

    def receive(self, buffer_size: int = 4096) -> bytes:
        """Receive data from socket.

        Returns empty bytes if no data available (non-blocking mode).
        """
        if not self.sock:
            raise RuntimeError("Not connected")
        try:
            return self.sock.recv(buffer_size)
        except BlockingIOError:
            # No data available in non-blocking mode
            return b""

    def close(self) -> None:
        """Close socket."""
        if self.sock:
            self.sock.close()
            self.sock = None
            self._connected = False

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected and self.sock is not None


class NamedPipeTransport(IPCTransport):
    """Named pipe transport for Windows."""

    def __init__(self):
        self.pipe: int | None = None  # File descriptor
        self._connected = False
        self._path: str | None = None

    def connect(self, path: str) -> None:
        r"""Connect to named pipe.

        On Windows, named pipes are accessed like files.
        Path format: \\.\pipe\name
        """
        self._path = path
        # Open named pipe in binary read-write mode
        self.pipe = os.open(path, os.O_RDWR | os.O_BINARY)
        self._connected = True

    def send(self, data: bytes) -> None:
        """Send data to pipe."""
        if self.pipe is None:
            raise RuntimeError("Not connected")
        os.write(self.pipe, data)

    def receive(self, buffer_size: int = 4096) -> bytes:
        """Receive data from pipe."""
        if self.pipe is None:
            raise RuntimeError("Not connected")
        return os.read(self.pipe, buffer_size)

    def close(self) -> None:
        """Close pipe."""
        if self.pipe is not None:
            os.close(self.pipe)
            self.pipe = None
            self._connected = False

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected and self.pipe is not None


def create_transport(platform_name: str | None = None) -> IPCTransport:
    """Factory function to create appropriate IPC transport.

    Args:
        platform_name: Platform name ('Linux', 'Windows', 'Darwin'), or None to auto-detect

    Returns:
        Appropriate IPCTransport for the platform
    """
    if platform_name is None:
        platform_name = platform.system()

    if platform_name in ("Linux", "Darwin"):  # Linux, WSL, macOS
        return UnixSocketTransport()
    elif platform_name == "Windows":
        return NamedPipeTransport()
    else:
        # Default to Unix socket for unknown platforms
        return UnixSocketTransport()


def generate_ipc_path(platform_name: str | None = None) -> str:
    """Generate appropriate IPC path for the platform.

    Args:
        platform_name: Platform name or None to auto-detect

    Returns:
        IPC path string
    """
    if platform_name is None:
        platform_name = platform.system()

    # Use cryptographically secure random token for unpredictable paths
    token = secrets.token_hex(8)

    if platform_name in ("Linux", "Darwin"):
        # Use XDG_RUNTIME_DIR if available (more secure, user-private)
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", tempfile.gettempdir())
        return f"{runtime_dir}/vslicer-mpv-{token}.sock"
    elif platform_name == "Windows":
        # Named pipe path with random token
        return f"\\\\.\\pipe\\vslicer-mpv-{token}"
    else:
        # Default to Unix socket with random token
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", tempfile.gettempdir())
        return f"{runtime_dir}/vslicer-mpv-{token}.sock"
