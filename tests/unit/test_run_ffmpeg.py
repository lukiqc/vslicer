"""Unit tests for run_ffmpeg execution, progress tracking, and cancellation."""

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from vslicer_core.export.ffmpeg import run_ffmpeg


def _mock_process(stdout_lines=None, stderr_lines=None, return_code=0):
    proc = MagicMock()
    proc.stdout = iter(stdout_lines or [])
    proc.stderr = iter(stderr_lines or [])
    proc.wait.return_value = return_code
    return proc


def test_run_ffmpeg_success(tmp_path: Path):
    output = tmp_path / "clip.webm"
    cmd = ["ffmpeg", "-y", str(output)]

    with patch("vslicer_core.export.ffmpeg.subprocess.Popen", return_value=_mock_process()):
        result = run_ffmpeg(cmd)

    assert result.ok
    assert result.output_path == output


def test_run_ffmpeg_progress_callback(tmp_path: Path):
    output = tmp_path / "clip.webm"
    cmd = ["ffmpeg", "-y", str(output)]
    # parse_progress_line returns a dict for any "key=value" line
    proc = _mock_process(stdout_lines=["out_time_ms=5000000\n", "progress=continue\n"])
    calls = []

    with patch("vslicer_core.export.ffmpeg.subprocess.Popen", return_value=proc):
        result = run_ffmpeg(cmd, on_progress=calls.append)

    assert result.ok
    assert len(calls) >= 1
    assert any("out_time_ms" in d for d in calls)


def test_run_ffmpeg_nonzero_exit(tmp_path: Path):
    output = tmp_path / "clip.webm"
    cmd = ["ffmpeg", "-y", str(output)]
    proc = _mock_process(stderr_lines=["Error: codec not found\n"], return_code=1)

    with patch("vslicer_core.export.ffmpeg.subprocess.Popen", return_value=proc):
        result = run_ffmpeg(cmd)

    assert not result.ok
    assert "1" in result.error
    assert result.ffmpeg_log is not None
    assert "codec not found" in result.ffmpeg_log


def test_run_ffmpeg_cancelled(tmp_path: Path):
    output = tmp_path / "clip.webm"
    cmd = ["ffmpeg", "-y", str(output)]
    cancel = threading.Event()
    cancel.set()  # already cancelled before start

    with patch("vslicer_core.export.ffmpeg.subprocess.Popen", return_value=_mock_process()):
        result = run_ffmpeg(cmd, cancel_event=cancel)

    assert not result.ok
    assert result.error == "Export canceled"


def test_run_ffmpeg_ffmpeg_not_found():
    with patch("vslicer_core.export.ffmpeg.subprocess.Popen", side_effect=FileNotFoundError):
        result = run_ffmpeg(["ffmpeg", "-y", "out.webm"])

    assert not result.ok
    assert "not found" in result.error
