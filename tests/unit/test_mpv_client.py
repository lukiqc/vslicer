"""Unit tests for MPVClient using a fake transport."""

import json

from vslicer_core.mpv.client import MPVClient
from vslicer_core.mpv.ipc import IPCTransport


class FakeTransport(IPCTransport):
    """Simple fake IPC transport that echoes success responses."""

    def __init__(self):
        self._connected = False
        self._last_request = None
        self._responded = False

    def connect(self, path: str) -> None:
        self._connected = True

    def send(self, data: bytes) -> None:
        self._last_request = json.loads(data.decode("utf-8"))
        self._responded = False

    def receive(self, buffer_size: int = 4096) -> bytes:
        if self._responded or not self._last_request:
            return b""

        request_id = self._last_request.get("request_id")
        command = self._last_request.get("command", [])
        response = {"request_id": request_id, "error": "success"}

        if command[:2] == ["get_property", "time-pos"]:
            response["data"] = 12.34

        self._responded = True
        return (json.dumps(response) + "\n").encode("utf-8")

    def close(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected


def test_get_time_pos():
    client = MPVClient(FakeTransport())
    client.connect("/tmp/fake")

    assert client.get_time_pos() == 12.34


def test_play_pause_and_frame_step():
    client = MPVClient(FakeTransport())
    client.connect("/tmp/fake")

    assert client.pause()
    assert client.play()
    assert client.frame_step()
    assert client.frame_back_step()


def test_seek():
    client = MPVClient(FakeTransport())
    client.connect("/tmp/fake")

    assert client.seek(5.0)
    assert client.seek(2.0, mode="relative")


def test_quit():
    client = MPVClient(FakeTransport())
    client.connect("/tmp/fake")

    assert client.quit()


# ---------------------------------------------------------------------------
# send_command edge cases
# ---------------------------------------------------------------------------

class _SilentTransport(IPCTransport):
    """Never returns any data — simulates a non-responsive mpv."""

    def connect(self, path: str) -> None:
        pass

    def send(self, data: bytes) -> None:
        pass

    def receive(self, buffer_size: int = 4096) -> bytes:
        return b""

    def close(self) -> None:
        pass

    def is_connected(self) -> bool:
        return True


class _WrongIdTransport(IPCTransport):
    """Returns a response whose request_id never matches the caller's."""

    def connect(self, path: str) -> None:
        self._responded = False

    def send(self, data: bytes) -> None:
        self._responded = False

    def receive(self, buffer_size: int = 4096) -> bytes:
        if self._responded:
            return b""
        self._responded = True
        return (json.dumps({"request_id": 9999, "error": "success", "data": 5.0}) + "\n").encode()

    def close(self) -> None:
        pass

    def is_connected(self) -> bool:
        return True


class _BrokenTransport(IPCTransport):
    """Raises BrokenPipeError on every send."""

    def connect(self, path: str) -> None:
        pass

    def send(self, data: bytes) -> None:
        raise BrokenPipeError

    def receive(self, buffer_size: int = 4096) -> bytes:
        return b""

    def close(self) -> None:
        pass

    def is_connected(self) -> bool:
        return True


class _ErrorResponseTransport(IPCTransport):
    """Returns an mpv error response (error != 'success')."""

    def connect(self, path: str) -> None:
        self._request: dict | None = None
        self._responded = False

    def send(self, data: bytes) -> None:
        self._request = json.loads(data.decode())
        self._responded = False

    def receive(self, buffer_size: int = 4096) -> bytes:
        if self._responded or not self._request:
            return b""
        self._responded = True
        response = json.dumps({
            "request_id": self._request["request_id"],
            "error": "property unavailable",
        }) + "\n"
        return response.encode()

    def close(self) -> None:
        pass

    def is_connected(self) -> bool:
        return True


def test_send_command_timeout():
    """When the transport never responds, send_command returns None after timeout."""
    client = MPVClient(_SilentTransport())
    client.connect("/tmp/fake")

    result = client.send_command(["get_property", "time-pos"], timeout=0.05)

    assert result is None


def test_send_command_ignores_wrong_request_id():
    """A response with a non-matching request_id is discarded; returns None on timeout."""
    client = MPVClient(_WrongIdTransport())
    client.connect("/tmp/fake")

    result = client.send_command(["get_property", "time-pos"], timeout=0.05)

    assert result is None


def test_send_command_broken_pipe_returns_none():
    """BrokenPipeError during send causes send_command to return None immediately."""
    client = MPVClient(_BrokenTransport())
    client.connect("/tmp/fake")

    result = client.send_command(["get_property", "time-pos"])

    assert result is None


def test_get_property_returns_none_on_error_response():
    """If mpv responds with a non-success error field, get_property returns None."""
    client = MPVClient(_ErrorResponseTransport())
    client.connect("/tmp/fake")

    assert client.get_property("nonexistent-property") is None
