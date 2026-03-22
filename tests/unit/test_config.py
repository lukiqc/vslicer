"""Unit tests for configuration helpers."""

from __future__ import annotations

import os

from vslicer_core.config import get_config


def _load_config(**env: str) -> object:
    previous = {}
    for key, value in env.items():
        if value is None:
            raise ValueError("None is not a valid env value for this helper")
        previous[key] = os.environ.get(key)
        os.environ[key] = value

    get_config.cache_clear()
    config = get_config()

    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    get_config.cache_clear()
    return config


def test_get_config_normalizes_log_format() -> None:
    config = _load_config(VSLICER_LOG_FORMAT="weird")
    assert config.log_format == "text"


def test_get_config_normalizes_log_level() -> None:
    config = _load_config(VSLICER_LOG_LEVEL="not-a-level")
    assert config.log_level == "INFO"


def test_get_config_handles_negative_min_duration() -> None:
    config = _load_config(VSLICER_MIN_DURATION="-1")
    assert config.min_clip_duration == 0.05


def test_get_config_parses_host_lists() -> None:
    config = _load_config(
        VSLICER_ALLOWED_HOSTS="Example.com, .video.com,",
        VSLICER_BLOCKED_HOSTS="bad.example, .evil.org",
    )
    assert config.allowed_hosts == ("example.com", ".video.com")
    assert config.blocked_hosts == ("bad.example", ".evil.org")


def test_get_config_normalizes_timeouts() -> None:
    config = _load_config(
        VSLICER_FFMPEG_TIMEOUT="-5",
        VSLICER_YTDLP_TIMEOUT="0",
        VSLICER_FFPROBE_TIMEOUT="0",
    )
    assert config.ffmpeg_timeout_seconds == 0
    assert config.ytdlp_timeout_seconds == 0
    assert config.ffprobe_timeout_seconds == 30
