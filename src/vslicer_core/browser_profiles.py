"""Detect browser profiles for cookie extraction."""

from __future__ import annotations

import configparser
import json
import os
import platform
from pathlib import Path


def get_browser_profiles() -> list[tuple[str, str]]:
    """Return list of (display_name, yt-dlp_value) for detected browser profiles.

    Returns:
        List of tuples containing (display_name, yt-dlp_value).
        display_name is shown in the UI, yt-dlp_value is passed to --cookies-from-browser.
    """
    profiles: list[tuple[str, str]] = []
    profiles.extend(_detect_firefox_profiles())
    profiles.extend(_detect_chrome_profiles())
    profiles.extend(_detect_chromium_profiles())
    profiles.extend(_detect_edge_profiles())
    profiles.extend(_detect_brave_profiles())
    return profiles


def _get_firefox_dir() -> Path | None:
    """Get Firefox profile directory for current OS."""
    system = platform.system()
    home = Path.home()
    if system == "Linux":
        return home / ".mozilla" / "firefox"
    elif system == "Darwin":
        return home / "Library" / "Application Support" / "Firefox"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "Mozilla" / "Firefox"
    return None


def _detect_firefox_profiles() -> list[tuple[str, str]]:
    """Detect Firefox profiles from profiles.ini."""
    profiles: list[tuple[str, str]] = []
    firefox_dir = _get_firefox_dir()
    if not firefox_dir or not firefox_dir.exists():
        return profiles

    ini_path = firefox_dir / "profiles.ini"
    if not ini_path.exists():
        return profiles

    config = configparser.ConfigParser()
    try:
        config.read(ini_path)
    except (configparser.Error, OSError):
        return profiles

    for section in config.sections():
        if section.startswith("Profile"):
            name = config.get(section, "Name", fallback="")
            path = config.get(section, "Path", fallback="")
            is_relative = config.getboolean(section, "IsRelative", fallback=True)

            if path:
                if is_relative:
                    full_path = firefox_dir / path
                else:
                    full_path = Path(path)

                if full_path.exists():
                    display = f"Firefox: {name}" if name else f"Firefox: {path}"
                    value = f"firefox:{full_path}"
                    profiles.append((display, value))

    return profiles


def _get_chrome_dir() -> Path | None:
    """Get Chrome user data directory for current OS."""
    system = platform.system()
    home = Path.home()
    if system == "Linux":
        return home / ".config" / "google-chrome"
    elif system == "Darwin":
        return home / "Library" / "Application Support" / "Google" / "Chrome"
    elif system == "Windows":
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata:
            return Path(local_appdata) / "Google" / "Chrome" / "User Data"
    return None


def _detect_chromium_style_profiles(
    browser_name: str, user_data_dir: Path | None
) -> list[tuple[str, str]]:
    """Detect profiles for Chromium-based browsers.

    Chromium browsers store profiles in subdirectories of the user data dir.
    The 'Local State' file contains profile info.
    """
    profiles: list[tuple[str, str]] = []
    if not user_data_dir or not user_data_dir.exists():
        return profiles

    # Check for Default profile
    default_profile = user_data_dir / "Default"
    if default_profile.exists():
        display = f"{browser_name}: Default"
        value = f"{browser_name.lower()}:{default_profile}"
        profiles.append((display, value))

    # Check Local State for additional profiles
    local_state = user_data_dir / "Local State"
    if local_state.exists():
        try:
            with local_state.open(encoding="utf-8") as f:
                state = json.load(f)
            profile_info = state.get("profile", {}).get("info_cache", {})
            for profile_dir, info in profile_info.items():
                if profile_dir == "Default":
                    continue  # Already added
                profile_path = user_data_dir / profile_dir
                if profile_path.exists():
                    name = info.get("name", profile_dir)
                    display = f"{browser_name}: {name}"
                    value = f"{browser_name.lower()}:{profile_path}"
                    profiles.append((display, value))
        except (json.JSONDecodeError, OSError, KeyError):
            pass

    return profiles


def _detect_chrome_profiles() -> list[tuple[str, str]]:
    """Detect Chrome profiles."""
    return _detect_chromium_style_profiles("Chrome", _get_chrome_dir())


def _get_chromium_dir() -> Path | None:
    """Get Chromium user data directory for current OS."""
    system = platform.system()
    home = Path.home()
    if system == "Linux":
        return home / ".config" / "chromium"
    elif system == "Darwin":
        return home / "Library" / "Application Support" / "Chromium"
    elif system == "Windows":
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata:
            return Path(local_appdata) / "Chromium" / "User Data"
    return None


def _detect_chromium_profiles() -> list[tuple[str, str]]:
    """Detect Chromium profiles."""
    return _detect_chromium_style_profiles("Chromium", _get_chromium_dir())


def _get_edge_dir() -> Path | None:
    """Get Edge user data directory for current OS."""
    system = platform.system()
    home = Path.home()
    if system == "Linux":
        return home / ".config" / "microsoft-edge"
    elif system == "Darwin":
        return home / "Library" / "Application Support" / "Microsoft Edge"
    elif system == "Windows":
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata:
            return Path(local_appdata) / "Microsoft" / "Edge" / "User Data"
    return None


def _detect_edge_profiles() -> list[tuple[str, str]]:
    """Detect Microsoft Edge profiles."""
    return _detect_chromium_style_profiles("Edge", _get_edge_dir())


def _get_brave_dir() -> Path | None:
    """Get Brave user data directory for current OS."""
    system = platform.system()
    home = Path.home()
    if system == "Linux":
        return home / ".config" / "BraveSoftware" / "Brave-Browser"
    elif system == "Darwin":
        return (
            home / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser"
        )
    elif system == "Windows":
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata:
            return Path(local_appdata) / "BraveSoftware" / "Brave-Browser" / "User Data"
    return None


def _detect_brave_profiles() -> list[tuple[str, str]]:
    """Detect Brave browser profiles."""
    return _detect_chromium_style_profiles("Brave", _get_brave_dir())
