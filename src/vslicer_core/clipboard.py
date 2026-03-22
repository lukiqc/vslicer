"""Clipboard operations for VSlicer.

Reads URLs from system clipboard.
"""

try:
    import pyperclip
except ImportError:  # Optional dependency for clipboard access
    pyperclip = None

from .domain.validate import validate_url


def read_url_from_clipboard(strict_webm: bool = False) -> str | None:
    """Read URL from system clipboard.

    Args:
        strict_webm: If True, only accept .webm URLs

    Returns:
        Valid URL from clipboard, or None if no valid URL found
    """
    if pyperclip is None:
        return None

    try:
        clipboard_content = pyperclip.paste()

        if not clipboard_content:
            return None

        # Check if it looks like a URL
        is_valid, _ = validate_url(clipboard_content, strict_webm=strict_webm)

        if is_valid:
            return clipboard_content.strip()

        return None

    except (OSError, TypeError, AttributeError) as e:
        # Clipboard access failed (no display, invalid content, etc.)
        # pyperclip may raise various exceptions depending on platform
        del e  # Explicitly unused
        return None
