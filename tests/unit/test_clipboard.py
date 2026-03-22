"""Unit tests for clipboard URL reading."""

from vslicer_core import clipboard


def test_read_url_from_clipboard_valid(monkeypatch):
    monkeypatch.setattr(clipboard.pyperclip, "paste", lambda: "https://example.com/video.webm")
    assert clipboard.read_url_from_clipboard() == "https://example.com/video.webm"


def test_read_url_from_clipboard_invalid(monkeypatch):
    monkeypatch.setattr(clipboard.pyperclip, "paste", lambda: "not-a-url")
    assert clipboard.read_url_from_clipboard() is None


def test_read_url_from_clipboard_exception(monkeypatch):
    def raise_error():
        raise OSError("clipboard access denied")

    monkeypatch.setattr(clipboard.pyperclip, "paste", raise_error)
    assert clipboard.read_url_from_clipboard() is None
