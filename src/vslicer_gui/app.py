"""VSlicer GUI application entrypoint (Qt)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    """Launch the VSlicer GUI.

    Returns:
        Exit code (0 on success).
    """
    # pythonw.exe sets sys.stdout/stderr to None (no console attached).
    # Redirect to devnull so logging setup doesn't crash on AttributeError.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115, PTH123
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115, PTH123

    # Initialize logging early (before Qt imports)
    from vslicer_core.config import (
        cleanup_old_logs,
        cleanup_temp_artifacts,
        get_config,
        get_log_dir,
        get_logger,
        setup_logging,
    )

    # Setup logging with file output
    log_file = get_log_dir() / "vslicer-gui.log"
    setup_logging(log_file=str(log_file))
    logger = get_logger(__name__)

    # Clean up old log files (older than 30 days)
    removed = cleanup_old_logs()
    if removed > 0:
        logger.debug(f"Cleaned up {removed} old log files")
    temp_removed = cleanup_temp_artifacts()
    if temp_removed > 0:
        logger.debug(f"Cleaned up {temp_removed} temp artifacts")

    if get_config().force_x11:
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    try:
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        logger.error("PySide6 import failed", exc_info=True)
        print("PySide6 import failed. Details:")
        print(str(exc))
        print("If this is a missing system library, install it with apt.")
        print("Example: sudo apt-get install -y libgl1 libxkbcommon0 libxcb-cursor0")
        return 1

    from .main_window import MainWindow

    logger.info("Starting GUI application")
    app = QApplication(sys.argv)

    # Set application icon
    icon_path = Path(__file__).parent / "assets" / "icons" / "vslicer_256.ico"
    if icon_path.exists():
        app_icon = QIcon(str(icon_path))
        app.setWindowIcon(app_icon)
        logger.debug("Application icon set", extra={"path": str(icon_path)})

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
