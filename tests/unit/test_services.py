"""Unit tests for core service helpers."""

import pytest

from vslicer_core.domain.models import ClipSpec, ExportOptions
from vslicer_core.services.export import build_export_command, resolve_input_urls
from vslicer_core.services.playback import build_clip_spec


def test_build_clip_spec_valid():
    spec = build_clip_spec("https://example.com/video.webm", 1.0, 2.5)
    assert isinstance(spec, ClipSpec)
    assert spec.duration == pytest.approx(1.5)


def test_build_clip_spec_invalid_times():
    with pytest.raises(ValueError):
        build_clip_spec("https://example.com/video.webm", 2.0, 1.0)


def test_build_export_command_valid(tmp_path):
    spec = ClipSpec(url="https://example.com/video.webm", in_time=1.0, out_time=2.0)
    output_path = tmp_path / "clip.webm"
    options = ExportOptions(mode="accurate_reencode", output_path=output_path)

    cmd = build_export_command(spec, options)

    assert cmd[0] == "ffmpeg"
    assert str(output_path) == cmd[-1]


def test_build_export_command_invalid_output(tmp_path):
    spec = ClipSpec(url="https://example.com/video.webm", in_time=1.0, out_time=2.0)
    bad_dir = tmp_path / "missing"
    output_path = bad_dir / "clip.webm"
    options = ExportOptions(mode="accurate_reencode", output_path=output_path)

    with pytest.raises(ValueError):
        build_export_command(spec, options)


def test_resolve_input_urls_non_youtube():
    url = "https://example.com/video.webm"
    video_url, audio_url = resolve_input_urls(
        url, include_audio=False, audio_only=False
    )
    assert video_url == url
    assert audio_url is None
