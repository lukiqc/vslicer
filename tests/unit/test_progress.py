"""Unit tests for ffmpeg progress parsing."""

from vslicer_core.export.progress import (
    calculate_percent,
    parse_out_time_ms,
    parse_progress_line,
)


def test_parse_progress_line_valid():
    assert parse_progress_line("frame=10") == {"frame": "10"}


def test_parse_progress_line_invalid():
    assert parse_progress_line("noequals") is None
    assert parse_progress_line("") is None


def test_parse_out_time_ms():
    assert parse_out_time_ms("123") == 123
    assert parse_out_time_ms("abc") is None


def test_calculate_percent_bounds():
    assert calculate_percent(0, 100) == 0.0
    assert calculate_percent(50, 100) == 50.0
    assert calculate_percent(200, 100) == 100.0
    assert calculate_percent(10, 0) == 0.0
