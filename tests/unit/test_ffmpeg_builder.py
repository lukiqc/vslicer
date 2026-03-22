"""Unit tests for ffmpeg command builder and video dimension probing."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vslicer_core.domain.models import ClipSpec, CropOptions, ExportOptions, SlowMoOptions
from vslicer_core.export.ffmpeg import build_ffmpeg_command, get_video_dimensions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spec(**kwargs):
    kwargs.setdefault("url", "https://example.com/video.webm")
    kwargs.setdefault("in_time", 1.0)
    kwargs.setdefault("out_time", 3.0)
    return ClipSpec(**kwargs)


def _opts(tmp_path, **kwargs):
    kwargs.setdefault("mode", "accurate_reencode")
    kwargs.setdefault("output_path", tmp_path / "clip.webm")
    return ExportOptions(**kwargs)


# ---------------------------------------------------------------------------
# build_ffmpeg_command — original tests
# ---------------------------------------------------------------------------

def test_build_ffmpeg_fast_copy_no_filters(tmp_path: Path):
    spec = ClipSpec(url="https://example.com/video.webm", in_time=1.0, out_time=2.0)
    options = ExportOptions(mode="fast_copy", output_path=tmp_path / "clip.webm")

    cmd = build_ffmpeg_command(spec, options)

    assert cmd[0] == "ffmpeg"
    assert "-c" in cmd
    assert "copy" in cmd


def test_build_ffmpeg_slowmo_forces_reencode(tmp_path: Path):
    spec = ClipSpec(url="https://example.com/video.webm", in_time=1.0, out_time=2.0)
    options = ExportOptions(
        mode="fast_copy",
        output_path=tmp_path / "clip.webm",
        slowmo=SlowMoOptions(factor=2.0),
    )

    cmd = build_ffmpeg_command(spec, options)

    assert "-c:v" in cmd
    assert "libvpx-vp9" in cmd
    assert "-vf" in cmd
    assert any("setpts" in item for item in cmd)
    assert "-af" in cmd
    assert any("atempo" in item for item in cmd)


def test_build_ffmpeg_mute_audio(tmp_path: Path):
    spec = ClipSpec(url="https://example.com/video.webm", in_time=1.0, out_time=2.0)
    options = ExportOptions(
        mode="accurate_reencode",
        output_path=tmp_path / "clip.webm",
        slowmo=SlowMoOptions(factor=2.0, audio_policy="mute"),
        include_audio=True,
    )

    cmd = build_ffmpeg_command(spec, options)

    assert "-an" in cmd
    assert "-c:a" not in cmd


# ---------------------------------------------------------------------------
# build_ffmpeg_command — crop
# ---------------------------------------------------------------------------

def test_build_ffmpeg_crop_forces_reencode(tmp_path, monkeypatch):
    monkeypatch.setattr("vslicer_core.export.ffmpeg.get_video_dimensions", lambda url: (1920, 1080))
    options = _opts(tmp_path, mode="fast_copy", crop=CropOptions(aspect_ratio="9:16", position=0.5))

    cmd = build_ffmpeg_command(_spec(), options)

    assert "libvpx-vp9" in cmd
    assert "-c" not in cmd  # no stream-copy


def test_build_ffmpeg_crop_filter_in_vf(tmp_path, monkeypatch):
    monkeypatch.setattr("vslicer_core.export.ffmpeg.get_video_dimensions", lambda url: (1920, 1080))
    options = _opts(tmp_path, crop=CropOptions(aspect_ratio="9:16", position=0.5))

    cmd = build_ffmpeg_command(_spec(), options)

    assert "-vf" in cmd
    assert "crop=" in cmd[cmd.index("-vf") + 1]


# ---------------------------------------------------------------------------
# build_ffmpeg_command — playback modes
# ---------------------------------------------------------------------------

def test_build_ffmpeg_reverse_playback(tmp_path):
    options = _opts(tmp_path, playback_mode="reverse")

    cmd = build_ffmpeg_command(_spec(), options)

    assert "-vf" in cmd
    assert "reverse" in cmd[cmd.index("-vf") + 1]
    assert "-af" in cmd
    assert "areverse" in cmd[cmd.index("-af") + 1]


def test_build_ffmpeg_pingpong_uses_filter_complex(tmp_path):
    options = _opts(tmp_path, playback_mode="pingpong")

    cmd = build_ffmpeg_command(_spec(), options)

    assert "-filter_complex" in cmd
    fc_value = cmd[cmd.index("-filter_complex") + 1]
    assert "reverse" in fc_value
    assert "concat" in fc_value


# ---------------------------------------------------------------------------
# build_ffmpeg_command — audio handling
# ---------------------------------------------------------------------------

def test_build_ffmpeg_separate_audio_url(tmp_path):
    audio_url = "https://example.com/audio.webm"
    options = _opts(tmp_path)

    cmd = build_ffmpeg_command(_spec(), options, audio_url=audio_url)

    i_indices = [i for i, x in enumerate(cmd) if x == "-i"]
    assert len(i_indices) == 2
    assert audio_url in cmd


def test_build_ffmpeg_audio_only(tmp_path):
    spec = ClipSpec(url="https://example.com/track.mp3", in_time=0.0, out_time=5.0)
    options = _opts(tmp_path, output_type="audio", output_path=tmp_path / "clip.mp3")

    cmd = build_ffmpeg_command(spec, options)

    assert "-vn" in cmd
    assert "libmp3lame" in cmd
    assert "-vf" not in cmd


def test_build_ffmpeg_no_audio(tmp_path):
    options = _opts(tmp_path, include_audio=False)

    cmd = build_ffmpeg_command(_spec(), options)

    assert "-an" in cmd
    assert "-c:a" not in cmd


def test_build_ffmpeg_slowmo_stretch_includes_audio_codec(tmp_path):
    options = _opts(tmp_path, slowmo=SlowMoOptions(factor=2.0, audio_policy="stretch"))

    cmd = build_ffmpeg_command(_spec(), options)

    assert "-af" in cmd
    assert any("atempo" in item for item in cmd)
    assert "-c:a" in cmd
    assert "libvorbis" in cmd


# ---------------------------------------------------------------------------
# build_ffmpeg_command — video filter passthrough
# ---------------------------------------------------------------------------

def test_build_ffmpeg_custom_video_filter(tmp_path):
    options = _opts(tmp_path, video_filter="hflip")

    cmd = build_ffmpeg_command(_spec(), options)

    assert "-vf" in cmd
    assert "hflip" in cmd[cmd.index("-vf") + 1]


# ---------------------------------------------------------------------------
# get_video_dimensions
# ---------------------------------------------------------------------------

def _mock_run(monkeypatch, returncode=0, stdout="1920,1080", stderr=""):
    mock_result = MagicMock()
    mock_result.returncode = returncode
    mock_result.stdout = stdout
    mock_result.stderr = stderr
    monkeypatch.setattr("vslicer_core.export.ffmpeg.subprocess.run", lambda *a, **kw: mock_result)


def test_get_video_dimensions_success(monkeypatch):
    _mock_run(monkeypatch)

    w, h = get_video_dimensions("https://example.com/video.mp4")

    assert w == 1920
    assert h == 1080


def test_get_video_dimensions_http_error(monkeypatch):
    _mock_run(monkeypatch, returncode=1, stderr="Server returned 403 Forbidden")

    with pytest.raises(RuntimeError, match="Failed to access video URL"):
        get_video_dimensions("https://example.com/private.mp4")


def test_get_video_dimensions_ffprobe_error(monkeypatch):
    _mock_run(monkeypatch, returncode=1, stderr="Invalid data found when processing input")

    with pytest.raises(RuntimeError, match="ffprobe failed"):
        get_video_dimensions("https://example.com/bad.mp4")


def test_get_video_dimensions_not_found(monkeypatch):
    def raise_not_found(*a, **kw):
        raise FileNotFoundError

    monkeypatch.setattr("vslicer_core.export.ffmpeg.subprocess.run", raise_not_found)

    with pytest.raises(RuntimeError, match="ffprobe not found"):
        get_video_dimensions("https://example.com/video.mp4")


def test_get_video_dimensions_timeout(monkeypatch):
    def raise_timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd=[], timeout=30)

    monkeypatch.setattr("vslicer_core.export.ffmpeg.subprocess.run", raise_timeout)

    with pytest.raises(RuntimeError, match="timed out"):
        get_video_dimensions("https://example.com/video.mp4")


def test_get_video_dimensions_empty_output(monkeypatch):
    _mock_run(monkeypatch, stdout="")

    with pytest.raises(RuntimeError, match="empty output"):
        get_video_dimensions("https://example.com/video.mp4")


def test_get_video_dimensions_malformed_output(monkeypatch):
    _mock_run(monkeypatch, stdout="1920")  # missing height

    with pytest.raises(RuntimeError, match="Unexpected ffprobe output"):
        get_video_dimensions("https://example.com/video.mp4")

