"""Configuration management for VSlicer.

Supports configuration via environment variables following 12-factor app principles.
"""

import atexit
import json
import logging
import os
import platform
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from pathlib import Path

# =============================================================================
# Environment Variable Configuration
# =============================================================================


def _get_bool_env(name: str, default: bool) -> bool:
    """Get boolean from environment variable."""
    value = os.environ.get(name, "").lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    return default


def _get_int_env(name: str, default: int) -> int:
    """Get integer from environment variable."""
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _get_float_env(name: str, default: float) -> float:
    """Get float from environment variable."""
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# =============================================================================
# Consolidated Configuration
# =============================================================================


@dataclass(frozen=True)
class AppConfig:
    """Typed, validated configuration sourced from environment variables."""

    output_dir: Path
    min_clip_duration: float
    strict_webm: bool
    enable_crop_feature: bool
    log_level: str
    log_format: str
    log_file: str | None
    log_max_size_mb: int
    log_backup_count: int
    log_retention_days: int
    force_x11: bool
    allowed_hosts: tuple[str, ...]
    blocked_hosts: tuple[str, ...]
    local_only: bool
    ytdlp_timeout_seconds: int
    ffmpeg_timeout_seconds: int
    ffprobe_timeout_seconds: int
    validate_remote_media: bool
    enable_cookie_fallback: bool
    cookies_from_browser: str


def _normalize_log_format(value: str) -> str:
    value = value.lower()
    return value if value in ("text", "json") else "text"


def _normalize_log_level(value: str) -> str:
    value = value.upper()
    return value if value in logging._nameToLevel else "INFO"


def _normalize_positive_int(value: int, default: int, minimum: int = 1) -> int:
    if value < minimum:
        return default
    return value


def _parse_host_list(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    items = []
    for raw in value.split(","):
        entry = raw.strip().lower()
        if entry:
            items.append(entry)
    return tuple(items)


def load_project_config() -> dict[str, object]:
    """Load project-local config.json if present."""
    path = Path.cwd() / "config.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Return cached configuration values."""
    project_config = load_project_config()
    output_dir = Path(os.environ.get("VSLICER_OUTPUT_DIR", "./clips"))
    min_clip_duration = _get_float_env("VSLICER_MIN_DURATION", 0.05)
    if min_clip_duration <= 0:
        min_clip_duration = 0.05
    strict_webm = _get_bool_env("VSLICER_STRICT_WEBM", False)
    enable_crop_feature = _get_bool_env("VSLICER_ENABLE_CROP", True)

    log_level = _normalize_log_level(os.environ.get("VSLICER_LOG_LEVEL", "INFO"))
    log_format = _normalize_log_format(os.environ.get("VSLICER_LOG_FORMAT", "text"))
    log_file = os.environ.get("VSLICER_LOG_FILE", "").strip() or None
    log_max_size_mb = _normalize_positive_int(
        _get_int_env("VSLICER_LOG_MAX_SIZE_MB", 10),
        default=10,
    )
    log_backup_count = _normalize_positive_int(
        _get_int_env("VSLICER_LOG_BACKUP_COUNT", 3),
        default=3,
        minimum=0,
    )
    log_retention_days = _normalize_positive_int(
        _get_int_env("VSLICER_LOG_RETENTION_DAYS", 30),
        default=30,
    )
    force_x11 = _get_bool_env("VSLICER_FORCE_X11", False)
    allowed_hosts = _parse_host_list(os.environ.get("VSLICER_ALLOWED_HOSTS", ""))
    blocked_hosts = _parse_host_list(os.environ.get("VSLICER_BLOCKED_HOSTS", ""))
    local_only = _get_bool_env("VSLICER_LOCAL_ONLY", False)
    ytdlp_timeout_seconds = _normalize_positive_int(
        _get_int_env("VSLICER_YTDLP_TIMEOUT", 60),
        default=60,
        minimum=0,
    )
    ffmpeg_timeout_seconds = _normalize_positive_int(
        _get_int_env("VSLICER_FFMPEG_TIMEOUT", 0),
        default=0,
        minimum=0,
    )
    ffprobe_timeout_seconds = _normalize_positive_int(
        _get_int_env("VSLICER_FFPROBE_TIMEOUT", 30),
        default=30,
        minimum=1,
    )
    validate_remote_media = _get_bool_env("VSLICER_VALIDATE_REMOTE_MEDIA", False)
    enable_cookie_fallback = _get_bool_env("VSLICER_ENABLE_COOKIE_FALLBACK", True)
    cookies_from_browser = os.environ.get("VSLICER_YTDLP_COOKIES_FROM_BROWSER")
    if cookies_from_browser is None:
        cookies_from_browser = project_config.get("cookies_from_browser")
    cookies_from_browser = (cookies_from_browser or "firefox").strip() or "firefox"

    return AppConfig(
        output_dir=output_dir,
        min_clip_duration=min_clip_duration,
        strict_webm=strict_webm,
        enable_crop_feature=enable_crop_feature,
        log_level=log_level,
        log_format=log_format,
        log_file=log_file,
        log_max_size_mb=log_max_size_mb,
        log_backup_count=log_backup_count,
        log_retention_days=log_retention_days,
        force_x11=force_x11,
        allowed_hosts=allowed_hosts,
        blocked_hosts=blocked_hosts,
        local_only=local_only,
        ytdlp_timeout_seconds=ytdlp_timeout_seconds,
        ffmpeg_timeout_seconds=ffmpeg_timeout_seconds,
        ffprobe_timeout_seconds=ffprobe_timeout_seconds,
        validate_remote_media=validate_remote_media,
        enable_cookie_fallback=enable_cookie_fallback,
        cookies_from_browser=cookies_from_browser,
    )


# Default configuration (backwards-compatible module constants)
_CONFIG = get_config()
DEFAULT_OUTPUT_DIR = _CONFIG.output_dir
MIN_CLIP_DURATION = _CONFIG.min_clip_duration
STRICT_WEBM = _CONFIG.strict_webm
ENABLE_CROP_FEATURE = _CONFIG.enable_crop_feature
LOG_LEVEL = _CONFIG.log_level
LOG_FORMAT = _CONFIG.log_format
LOG_FILE = _CONFIG.log_file or ""
LOG_MAX_SIZE_MB = _CONFIG.log_max_size_mb
LOG_BACKUP_COUNT = _CONFIG.log_backup_count

# Platform detection
PLATFORM = platform.system()

# =============================================================================
# Structured Logging
# =============================================================================


class StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter for machine parsing."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add source location for errors
        if record.levelno >= logging.ERROR:
            log_data["source"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info),
            }

        # Add extra fields
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in (
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "message",
                "asctime",
            ):
                continue
            log_data[key] = value

        return json.dumps(log_data, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable text formatter with optional colors."""

    def __init__(self, use_colors: bool = True):
        super().__init__(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.use_colors = use_colors and sys.stderr.isatty()
        self.colors = {
            "DEBUG": "\033[36m",  # Cyan
            "INFO": "\033[32m",  # Green
            "WARNING": "\033[33m",  # Yellow
            "ERROR": "\033[31m",  # Red
            "CRITICAL": "\033[35m",  # Magenta
        }
        self.reset = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        result = super().format(record)
        if self.use_colors and record.levelname in self.colors:
            color = self.colors[record.levelname]
            result = f"{color}{result}{self.reset}"
        return result


# Global state for logging
_logging_initialized = False
_log_file_handler: RotatingFileHandler | None = None
_media_access_policy_override: str | None = None


def _validate_log_file_path(file_path: str) -> Path | None:
    path = Path(file_path)
    try:
        resolved = path.resolve()
    except (OSError, ValueError):
        return None

    if path.exists() and path.is_dir():
        return None

    if ".." in path.parts and resolved != path.absolute():
        return None

    return path


def setup_logging(
    debug: bool = False,
    json_format: bool | None = None,
    log_file: str | None = None,
) -> None:
    """Setup logging configuration with rotation and crash handling.

    Args:
        debug: Enable debug logging (overrides VSLICER_LOG_LEVEL)
        json_format: Use JSON format (overrides VSLICER_LOG_FORMAT)
        log_file: Log file path (overrides VSLICER_LOG_FILE)
    """
    global _logging_initialized, _log_file_handler

    if _logging_initialized:
        return

    # Determine log level
    config = get_config()
    if debug:
        level = logging.DEBUG
    else:
        level_name = config.log_level
        level = getattr(logging, level_name, logging.INFO)

    # Determine format
    use_json = json_format if json_format is not None else (config.log_format == "json")

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    if use_json:
        console_handler.setFormatter(StructuredFormatter())
    else:
        console_handler.setFormatter(TextFormatter(use_colors=True))
    root_logger.addHandler(console_handler)

    # File handler with rotation
    file_path = log_file or (config.log_file or "")
    if file_path:
        log_path = _validate_log_file_path(file_path)
        if log_path is None:
            sys.stderr.write("Invalid log file path; file logging disabled.\n")
            log_path = None
        else:
            log_path.parent.mkdir(parents=True, exist_ok=True)

        if log_path is not None:
            _log_file_handler = RotatingFileHandler(
                log_path,
                maxBytes=config.log_max_size_mb * 1024 * 1024,
                backupCount=config.log_backup_count,
                encoding="utf-8",
            )
            _log_file_handler.setLevel(level)
            # Always use JSON for file logs (easier to parse)
            _log_file_handler.setFormatter(StructuredFormatter())
            root_logger.addHandler(_log_file_handler)

    # Install crash handlers
    _install_crash_handlers()

    _logging_initialized = True

    # Log startup
    logger = get_logger("vslicer")
    logger.info(
        "VSlicer starting",
        extra={
            "platform": PLATFORM,
            "python_version": sys.version,
            "log_level": logging.getLevelName(level),
        },
    )


def _install_crash_handlers() -> None:
    """Install handlers to log uncaught exceptions and crashes."""
    logger = get_logger("vslicer.crash")

    def exception_hook(exc_type, exc_value, exc_tb):
        """Log uncaught exceptions."""
        if issubclass(exc_type, KeyboardInterrupt):
            # Don't log keyboard interrupts as errors
            logger.info("Interrupted by user")
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        logger.critical(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_tb),
            extra={
                "exception_type": exc_type.__name__,
                "exception_message": str(exc_value),
            },
        )
        # Call default handler
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = exception_hook

    def exit_handler():
        """Log clean shutdown."""
        logger = get_logger("vslicer")
        logger.info("VSlicer shutting down")
        # Flush and close log file
        if _log_file_handler:
            _log_file_handler.flush()
            _log_file_handler.close()

    atexit.register(exit_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def get_config_summary() -> dict[str, object]:
    """Return a serializable summary of the current configuration."""
    config = get_config()
    return {
        "output_dir": str(config.output_dir),
        "min_clip_duration": config.min_clip_duration,
        "strict_webm": config.strict_webm,
        "enable_crop_feature": config.enable_crop_feature,
        "log_level": config.log_level,
        "log_format": config.log_format,
        "log_file": config.log_file,
        "log_max_size_mb": config.log_max_size_mb,
        "log_backup_count": config.log_backup_count,
        "log_retention_days": config.log_retention_days,
        "force_x11": config.force_x11,
        "allowed_hosts": list(config.allowed_hosts),
        "blocked_hosts": list(config.blocked_hosts),
        "local_only": config.local_only,
        "ytdlp_timeout_seconds": config.ytdlp_timeout_seconds,
        "ffmpeg_timeout_seconds": config.ffmpeg_timeout_seconds,
        "ffprobe_timeout_seconds": config.ffprobe_timeout_seconds,
        "validate_remote_media": config.validate_remote_media,
        "enable_cookie_fallback": config.enable_cookie_fallback,
        "cookies_from_browser": config.cookies_from_browser,
    }


def get_user_config_path() -> Path:
    """Return the per-user config JSON path."""
    if PLATFORM == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
    elif PLATFORM == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

    config_dir = base / "vslicer"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


def load_user_config() -> dict[str, object]:
    """Load user config JSON if present."""
    path = get_user_config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_user_config(data: dict[str, object]) -> None:
    """Persist user config JSON."""
    path = get_user_config_path()
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        return


def get_media_access_policy() -> str:
    """Return media access policy: ask, allow, or deny."""
    if _media_access_policy_override in ("allow", "deny"):
        return _media_access_policy_override
    data = load_user_config()
    value = data.get("media_access_policy")
    if value in ("allow", "deny", "ask"):
        return value
    return "ask"


def set_media_access_policy(value: str) -> None:
    """Persist media access policy: ask, allow, or deny."""
    if value not in ("allow", "deny", "ask"):
        return
    data = load_user_config()
    data["media_access_policy"] = value
    save_user_config(data)


def set_media_access_policy_override(value: str | None) -> None:
    """Set a session-only media access policy override."""
    global _media_access_policy_override
    if value not in ("allow", "deny", None):
        return
    _media_access_policy_override = value


def get_cookies_browser() -> str:
    """Get configured browser for cookies.

    Priority: env var > user config > default ("firefox").
    """
    env = os.environ.get("VSLICER_YTDLP_COOKIES_FROM_BROWSER")
    if env:
        return env.strip()
    data = load_user_config()
    value = data.get("cookies_from_browser", "")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "firefox"


def set_cookies_browser(browser: str) -> None:
    """Set browser for cookies."""
    data = load_user_config()
    data["cookies_from_browser"] = browser
    save_user_config(data)


def get_cache_size_mb() -> int:
    """Return demuxer cache size in MB (default 1024)."""
    data = load_user_config()
    try:
        value = int(data.get("cache_size_mb", 1024))
    except (TypeError, ValueError):
        value = 1024
    return max(value, 32)


def set_cache_size_mb(value: int) -> None:
    """Persist demuxer cache size in MB."""
    data = load_user_config()
    data["cache_size_mb"] = max(int(value), 32)
    save_user_config(data)


def get_incognito_enabled() -> bool:
    """Return whether incognito mode is enabled."""
    data = load_user_config()
    return bool(data.get("incognito_enabled", False))


def set_incognito_enabled(enabled: bool) -> None:
    """Persist incognito mode setting."""
    data = load_user_config()
    data["incognito_enabled"] = bool(enabled)
    save_user_config(data)


# =============================================================================
# Recent Media
# =============================================================================

_MAX_RECENT_MEDIA = 10


def get_recent_media() -> list[str]:
    """Return list of recently opened media paths/URLs."""
    data = load_user_config()
    recent = data.get("recent_media", [])
    if not isinstance(recent, list):
        return []
    return [item for item in recent if isinstance(item, str)][:_MAX_RECENT_MEDIA]


def add_recent_media(path: str) -> None:
    """Add a path/URL to recent media list."""
    if not path or not isinstance(path, str):
        return
    data = load_user_config()
    recent = data.get("recent_media", [])
    if not isinstance(recent, list):
        recent = []
    recent = [item for item in recent if item != path]
    recent.insert(0, path)
    data["recent_media"] = recent[:_MAX_RECENT_MEDIA]
    save_user_config(data)


def clear_recent_media() -> None:
    """Clear the recent media list."""
    data = load_user_config()
    data["recent_media"] = []
    save_user_config(data)


def get_log_dir() -> Path:
    """Get the default log directory.

    Returns platform-appropriate log directory:
    - Linux: ~/.local/share/vslicer/logs
    - macOS: ~/Library/Logs/vslicer
    - Windows: %LOCALAPPDATA%/vslicer/logs
    """
    if PLATFORM == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
    elif PLATFORM == "Darwin":
        base = Path.home() / "Library" / "Logs"
    else:  # Linux and others
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    log_dir = base / "vslicer" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def cleanup_old_logs(max_age_days: int | None = None) -> int:
    """Remove log files older than max_age_days.

    Args:
        max_age_days: Maximum age of log files in days

    Returns:
        Number of files removed
    """
    if max_age_days is None:
        max_age_days = get_config().log_retention_days

    log_dir = get_log_dir()
    if not log_dir.exists():
        return 0

    removed = 0
    cutoff = datetime.now().timestamp() - (max_age_days * 24 * 60 * 60)

    for log_file in log_dir.glob("*.log*"):
        try:
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
                removed += 1
        except OSError:
            pass

    return removed


def cleanup_temp_artifacts(max_age_hours: int = 24) -> int:
    """Remove VSlicer temp artifacts older than max_age_hours."""
    temp_dir = Path(tempfile.gettempdir())
    if not temp_dir.exists():
        return 0

    prefixes = (
        "vslicer-cache-",
        "vslicer-ytdlp-",
        "vslicer-mpv-",
        "vslicer-mpv-dump-",
    )
    cutoff = time.time() - (max_age_hours * 60 * 60)
    removed = 0

    for entry in temp_dir.iterdir():
        name = entry.name
        if not name.startswith(prefixes):
            continue
        try:
            if entry.stat().st_mtime >= cutoff:
                continue
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            removed += 1
        except OSError:
            continue

    return removed


def is_windows() -> bool:
    """Check if running on Windows.

    Returns:
        True if Windows
    """
    return PLATFORM == "Windows"


def is_linux() -> bool:
    """Check if running on Linux/WSL.

    Returns:
        True if Linux
    """
    return PLATFORM == "Linux"


def is_macos() -> bool:
    """Check if running on macOS.

    Returns:
        True if macOS
    """
    return PLATFORM == "Darwin"
