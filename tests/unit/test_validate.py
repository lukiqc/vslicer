"""Unit tests for validation helpers."""

from pathlib import Path

from vslicer_core.domain.models import ClipSpec, ExportOptions
from vslicer_core.domain.validate import (
    validate_clip_spec,
    validate_export_options,
    validate_local_media_path,
    validate_url,
)


def test_validate_url_http_https():
    ok, err = validate_url("https://example.com/video.webm")
    assert ok
    assert err == ""

    ok, err = validate_url("http://example.com/video.webm")
    assert ok
    assert err == ""


def test_validate_url_invalid_scheme():
    ok, err = validate_url("ftp://example.com/video.webm")
    assert not ok
    assert "http" in err


def test_validate_url_missing_netloc():
    ok, err = validate_url("https:///video.webm")
    assert not ok
    assert "network location" in err


def test_validate_url_strict_webm():
    ok, err = validate_url("https://example.com/video.mp4", strict_webm=True)
    assert not ok
    assert ".webm" in err


def test_validate_url_rejects_non_video_extension():
    ok, err = validate_url("https://example.com/video.exe")
    assert not ok
    assert "video resource" in err


def test_validate_url_allows_streaming_extension():
    ok, err = validate_url("https://example.com/playlist.m3u8")
    assert ok
    assert err == ""


def test_validate_url_allows_extensionless():
    ok, err = validate_url("https://example.com/stream")
    assert ok
    assert err == ""


def test_validate_url_allows_trailing_dot_host():
    ok, err = validate_url(
        "https://example.com./video.mp4",
        allowed_hosts=("example.com",),
    )
    assert ok
    assert err == ""


def test_validate_url_blocks_trailing_dot_host():
    ok, err = validate_url(
        "https://example.com./video.mp4",
        blocked_hosts=("example.com",),
    )
    assert not ok
    assert "blocked" in err


def test_validate_clip_spec_min_duration():
    spec = ClipSpec(url="https://example.com/video.webm", in_time=1.0, out_time=1.01)
    ok, err = validate_clip_spec(spec, min_duration=0.05)
    assert not ok
    assert "minimum" in err


def test_validate_clip_spec_ok():
    spec = ClipSpec(url="https://example.com/video.webm", in_time=1.0, out_time=2.0)
    ok, err = validate_clip_spec(spec)
    assert ok
    assert err == ""


def test_validate_export_options_output_exists(tmp_path: Path):
    output_path = tmp_path / "clip.webm"
    output_path.write_text("existing")
    options = ExportOptions(mode="accurate_reencode", output_path=output_path)

    ok, err = validate_export_options(options)
    assert not ok
    assert "already exists" in err


def test_validate_export_options_missing_dir(tmp_path: Path):
    output_path = tmp_path / "missing" / "clip.webm"
    options = ExportOptions(mode="accurate_reencode", output_path=output_path)

    ok, err = validate_export_options(options)
    assert not ok
    assert "does not exist" in err


def test_validate_local_media_path_rejects_extension(tmp_path: Path):
    path = tmp_path / "not_video.txt"
    path.write_text("data")
    ok, err = validate_local_media_path(path, probe=False)
    assert not ok
    assert "supported media" in err


def test_validate_local_media_path_accepts_extension(tmp_path: Path):
    path = tmp_path / "video.mp4"
    path.write_text("data")
    ok, err = validate_local_media_path(path, probe=False)
    assert ok
    assert err == ""


def test_validate_local_media_path_accepts_mp3(tmp_path: Path):
    path = tmp_path / "audio.mp3"
    path.write_text("data")
    ok, err = validate_local_media_path(path, probe=False)
    assert ok
    assert err == ""
