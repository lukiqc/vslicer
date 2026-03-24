"""Main window for the VSlicer GUI."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from vslicer_core.clipboard import read_url_from_clipboard
from vslicer_core.config import (
    ENABLE_CROP_FEATURE,
    add_recent_media,
    clear_recent_media,
    get_cache_size_mb,
    get_config,
    get_cookies_browser,
    get_incognito_enabled,
    get_logger,
    get_media_access_policy,
    get_recent_media,
    set_cache_size_mb,
    set_cookies_browser,
    set_incognito_enabled,
    set_media_access_policy,
    set_media_access_policy_override,
)
from vslicer_core.domain.models import CropOptions
from vslicer_core.domain.validate import validate_local_media_path, validate_url
from vslicer_core.export.ffmpeg import get_video_duration
from vslicer_core.services.playback import build_clip_spec

from .dialogs.export_dialog import ExportDialog
from .export_worker import ExportWorker
from .widgets.seek_slider import SeekSlider
from .widgets.video_view import VideoView

logger = get_logger(__name__)

APP_VERSION = "0.1.0-beta"
_GITHUB_RELEASES_API = "https://api.github.com/repos/lukiqc/vslicer/releases"
_GITHUB_RELEASES_PAGE = "https://github.com/lukiqc/vslicer/releases"


class MainWindow(QMainWindow):
    """Main application window with mpv playback."""

    _update_check_done = Signal(str, str)  # (title, message)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"VSlicer v{APP_VERSION}")

        # Set window icon
        icon_path = Path(__file__).parent / "assets" / "icons" / "vslicer_256.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._in_mark: float | None = None
        self._out_mark: float | None = None
        self._export_thread: QThread | None = None
        self._export_worker: ExportWorker | None = None
        self._duration: float | None = None
        self._fps: float | None = None
        self._slider_dragging = False
        self._livestream_detected = False
        self._cache_dump_path: Path | None = None
        self._cache_start: float = (
            0.0  # Start of livestream cache (when we started watching)
        )
        self._cache_end: float = 0.0  # End of livestream cache (live edge)
        self._following_live: bool = True  # Whether to auto-follow live edge
        self._stream_start_pos: float | None = None  # Position when stream was opened
        self._seek_target: float | None = None  # Track our own position when rewound

        # Crop feature state
        self._crop_enabled = False
        self._crop_ratio = "9:16"
        self._crop_position = 0.5
        self._custom_width_ratio: float | None = None

        self._cookie_retry_attempted = False
        self._cache_dump_path: Path | None = None
        self._cache_dump_offset: float = 0.0
        self._media_access_prompted = False
        self._video_fullscreen = False
        self._incognito_enabled = False
        self._incognito_action: object | None = None
        self._update_check_action: object | None = None
        self._recent_menu: QMenu | None = None
        self._log_offset = 0
        temp_dir = Path(__file__).resolve().parent.parent / "temp"
        temp_dir.mkdir(exist_ok=True)
        self._gui_log_path = temp_dir / "vslicer-gui.log"
        # Clear previous log on startup
        self._gui_log_path.write_text("", encoding="utf-8")

        self._build_ui()
        self._wire_signals()
        self._wire_shortcuts()

        # Set main window reference for crop overlay so it stays with this app
        if ENABLE_CROP_FEATURE:
            self.video_view.crop_overlay.set_main_window(self)

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(250)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()

        self._log_timer = QTimer(self)
        self._log_timer.setInterval(500)
        self._log_timer.timeout.connect(self._refresh_log)
        self._log_timer.start()

        self._set_incognito_enabled(get_incognito_enabled())

    def _build_menu_bar(self) -> None:
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)

        # File menu
        file_menu = QMenu("&File", self)
        menu_bar.addMenu(file_menu)

        open_url_action = file_menu.addAction("Open &URL...")
        open_url_action.setShortcut(QKeySequence("Ctrl+U"))
        open_url_action.triggered.connect(self._menu_open_url)

        open_media_action = file_menu.addAction("&Open Media...")
        open_media_action.setShortcut(QKeySequence("Ctrl+O"))
        open_media_action.triggered.connect(self._browse_file)

        self._recent_menu = QMenu("Open &Recent", self)
        file_menu.addMenu(self._recent_menu)
        self._update_recent_menu()

        file_menu.addSeparator()

        close_action = file_menu.addAction("&Close Current Media")
        close_action.setShortcut(QKeySequence("Ctrl+W"))
        close_action.triggered.connect(self._close_media)

        file_menu.addSeparator()

        self._incognito_action = file_menu.addAction("Activate Incognito")
        self._incognito_action.triggered.connect(self._toggle_incognito)

        preferences_action = file_menu.addAction("&Preferences...")
        preferences_action.setShortcut(QKeySequence("Ctrl+,"))
        preferences_action.triggered.connect(self._show_preferences)

        file_menu.addSeparator()

        quit_action = file_menu.addAction("&Quit")
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)

        # Navigate menu
        navigate_menu = QMenu("&Navigate", self)
        menu_bar.addMenu(navigate_menu)

        play_pause_action = navigate_menu.addAction("&Play/Pause")
        play_pause_action.setShortcut(QKeySequence("Space"))
        play_pause_action.triggered.connect(self._toggle_play)

        frame_back_action = navigate_menu.addAction("Frame &-")
        frame_back_action.setShortcut(QKeySequence(","))
        frame_back_action.triggered.connect(self._frame_back)

        frame_forward_action = navigate_menu.addAction("Frame &+")
        frame_forward_action.setShortcut(QKeySequence("."))
        frame_forward_action.triggered.connect(self._frame_forward)

        navigate_menu.addSeparator()

        set_in_action = navigate_menu.addAction("Set &IN")
        set_in_action.setShortcut(QKeySequence("I"))
        set_in_action.triggered.connect(self._mark_in)

        goto_in_action = navigate_menu.addAction("&Go to IN")
        goto_in_action.setShortcut(QKeySequence("G"))
        goto_in_action.triggered.connect(self._goto_in)

        navigate_menu.addSeparator()

        set_out_action = navigate_menu.addAction("Set &OUT")
        set_out_action.setShortcut(QKeySequence("O"))
        set_out_action.triggered.connect(self._mark_out)

        goto_out_action = navigate_menu.addAction("Go to O&UT")
        goto_out_action.setShortcut(QKeySequence("Shift+G"))
        goto_out_action.triggered.connect(self._goto_out)

        navigate_menu.addSeparator()

        volume_up_action = navigate_menu.addAction("Volume &Up")
        volume_up_action.setShortcut(QKeySequence("Ctrl+Up"))
        volume_up_action.triggered.connect(self._volume_up)

        volume_down_action = navigate_menu.addAction("Volume &Down")
        volume_down_action.setShortcut(QKeySequence("Ctrl+Down"))
        volume_down_action.triggered.connect(self._volume_down)

        mute_action = navigate_menu.addAction("&Mute")
        mute_action.setShortcut(QKeySequence("M"))
        mute_action.triggered.connect(self._toggle_mute)

        navigate_menu.addSeparator()

        fullscreen_action = navigate_menu.addAction("&Fullscreen")
        fullscreen_action.setShortcut(QKeySequence("F"))
        fullscreen_action.triggered.connect(self._toggle_fullscreen)

        # Help menu
        help_menu = QMenu("&Help", self)
        menu_bar.addMenu(help_menu)

        about_action = help_menu.addAction("&About VSlicer")
        about_action.triggered.connect(self._show_about)

        self._update_check_action = help_menu.addAction("Check for &Updates")
        self._update_check_action.triggered.connect(self._check_for_updates)

    def _show_about(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("About VSlicer")
        dialog.setModal(True)
        dialog.setFixedWidth(400)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        title_label = QLabel(f"<b>VSlicer v{APP_VERSION}</b>")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(title_label)

        desc_label = QLabel(
            "Frame-accurate video clipping tool.\n"
            "Clip and export directly from stream URLs\u2014no download required."
        )
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        link_label = QLabel(
            '<a href="https://github.com/lukiqc/vslicer">github.com/lukiqc/vslicer</a>'
        )
        link_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link_label.setOpenExternalLinks(True)
        layout.addWidget(link_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        dialog.exec()

    def _check_for_updates(self) -> None:
        if self._update_check_action is not None:
            self._update_check_action.setEnabled(False)
        threading.Thread(target=self._do_update_check, daemon=True).start()

    def _do_update_check(self) -> None:
        try:
            req = urllib.request.Request(  # noqa: S310
                _GITHUB_RELEASES_API,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "vslicer",
                },
            )
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
                releases = json.loads(resp.read())
            if not releases:
                self._update_check_done.emit(
                    "No releases found",
                    f"No releases have been published yet.\n\nVisit {_GITHUB_RELEASES_PAGE} to check manually.",
                )
                return
            tag = releases[0].get("tag_name", "").lstrip("v")
            if tag == APP_VERSION:
                self._update_check_done.emit(
                    "Up to date",
                    f"You are running the latest version (v{APP_VERSION}).",
                )
            else:
                self._update_check_done.emit(
                    "Update available",
                    f"A new version is available: v{tag}\n\n"
                    f"Visit {_GITHUB_RELEASES_PAGE} to download it.",
                )
        except urllib.error.HTTPError as exc:
            self._update_check_done.emit(
                "Check failed",
                f"GitHub returned an error (HTTP {exc.code}). Try again later.",
            )
        except Exception:
            self._update_check_done.emit(
                "Check failed",
                "Could not reach GitHub. Check your internet connection and try again.",
            )

    def _on_update_check_done(self, title: str, message: str) -> None:
        if self._update_check_action is not None:
            self._update_check_action.setEnabled(True)
        QMessageBox.information(self, title, message)

    def _volume_up(self) -> None:
        if self.video_view.client:
            vol = self.video_view.client.get_property("volume", timeout=0.1)
            if vol is not None:
                self.video_view.client.set_property("volume", min(vol + 5, 150))

    def _volume_down(self) -> None:
        if self.video_view.client:
            vol = self.video_view.client.get_property("volume", timeout=0.1)
            if vol is not None:
                self.video_view.client.set_property("volume", max(vol - 5, 0))

    def _toggle_mute(self) -> None:
        if self.video_view.client:
            muted = self.video_view.client.get_property("mute", timeout=0.1)
            if muted is not None:
                self.video_view.client.set_property("mute", not muted)

    def _toggle_fullscreen(self) -> None:
        if self._video_fullscreen:
            self._exit_fullscreen()
        else:
            # Enter fullscreen: detach and show as top-level
            self.video_layout.removeWidget(self.video_view)
            self.video_view.setParent(None)
            self.video_view.setWindowFlags(Qt.Window)
            self.video_view.showFullScreen()
            self._video_fullscreen = True
            # Add shortcuts to exit fullscreen from the video window
            self._fs_shortcut_f = QShortcut(QKeySequence("F"), self.video_view)
            self._fs_shortcut_f.activated.connect(self._exit_fullscreen)
            self._fs_shortcut_esc = QShortcut(QKeySequence("Escape"), self.video_view)
            self._fs_shortcut_esc.activated.connect(self._exit_fullscreen)

    def _exit_fullscreen(self) -> None:
        if not self._video_fullscreen:
            return
        self._video_fullscreen = False
        self.video_view.setWindowFlags(Qt.Widget)
        self.video_layout.addWidget(self.video_view)
        self.video_view.show()

    def _build_ui(self) -> None:
        self._build_menu_bar()

        root = QWidget(self)
        layout = QVBoxLayout(root)
        self._main_layout = layout

        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste video URL...")
        clipboard_url = read_url_from_clipboard()
        if clipboard_url:
            self.url_input.setText(clipboard_url)

        self.open_button = QPushButton("Open URL")
        self.browse_button = QPushButton("Browse File")
        url_row.addWidget(self.url_input)
        url_row.addWidget(self.open_button)
        url_row.addWidget(self.browse_button)

        self.video_container = QWidget(self)
        self.video_layout = QVBoxLayout(self.video_container)
        self.video_layout.setContentsMargins(0, 0, 0, 0)

        self.video_view = VideoView()
        self.video_view.setMinimumSize(640, 360)
        self.video_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_layout.addWidget(self.video_view)

        self.seek_slider = SeekSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setSingleStep(100)
        self.seek_slider.setPageStep(1000)

        controls_row = QHBoxLayout()
        self.play_button = QPushButton("Play/Pause")
        self.step_back_button = QPushButton("Frame -")
        self.step_forward_button = QPushButton("Frame +")
        self.mark_in_button = QPushButton("Set IN")
        self.mark_out_button = QPushButton("Set OUT")
        self.goto_in_button = QPushButton("Go to IN")
        self.goto_out_button = QPushButton("Go to OUT")
        self.loop_checkbox = QCheckBox("Preview")
        self.export_button = QPushButton("Export")
        self.cancel_export_button = QPushButton("Cancel Export")
        self.cancel_export_button.setEnabled(False)

        for button in (
            self.play_button,
            self.step_back_button,
            self.step_forward_button,
            self.mark_in_button,
            self.mark_out_button,
            self.goto_in_button,
            self.goto_out_button,
        ):
            controls_row.addWidget(button)
        controls_row.addWidget(self.loop_checkbox)
        controls_row.addWidget(self.export_button)
        controls_row.addWidget(self.cancel_export_button)

        # Crop controls row (only if feature is enabled)
        self._crop_row = None
        if ENABLE_CROP_FEATURE:
            crop_row = QHBoxLayout()
            self.crop_checkbox = QCheckBox("Crop for vertical")
            self.crop_ratio_combo = QComboBox()
            self.crop_ratio_combo.addItem("9:16", "9:16")
            self.crop_ratio_combo.addItem("4:5", "4:5")
            self.crop_ratio_combo.addItem("1:1", "1:1")
            self.crop_ratio_combo.addItem("Custom", "custom")
            self.crop_ratio_combo.setEnabled(False)
            crop_row.addWidget(self.crop_checkbox)
            crop_row.addWidget(self.crop_ratio_combo)
            crop_row.addStretch(1)
            self._crop_row = crop_row

        status_row = QHBoxLayout()
        self.time_label = QLabel("Time: 00:00.000")
        self.in_label = QLabel("IN")
        self.in_input = QLineEdit()
        self.in_input.setPlaceholderText("--")
        self.in_input.setFixedWidth(120)
        self.out_label = QLabel("OUT")
        self.out_input = QLineEdit()
        self.out_input.setPlaceholderText("--")
        self.out_input.setFixedWidth(120)
        self.export_label = QLabel("Export: --")
        status_row.addWidget(self.time_label)
        status_row.addWidget(self.in_label)
        status_row.addWidget(self.in_input)
        status_row.addWidget(self.out_label)
        status_row.addWidget(self.out_input)
        self.reset_marks_btn = QPushButton("Reset")
        self.reset_marks_btn.setFixedWidth(60)
        self.reset_marks_btn.clicked.connect(self._reset_marks)
        status_row.addWidget(self.reset_marks_btn)
        status_row.addWidget(self.export_label)
        status_row.addStretch(1)

        layout.addLayout(url_row)
        layout.addWidget(self.video_container, stretch=1)
        layout.addWidget(self.seek_slider)
        layout.addLayout(controls_row)
        if self._crop_row is not None:
            layout.addLayout(self._crop_row)
        layout.addLayout(status_row)

        self.setCentralWidget(root)

        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

    def _wire_signals(self) -> None:
        self._update_check_done.connect(self._on_update_check_done)
        self.open_button.clicked.connect(self._open_url)
        self.browse_button.clicked.connect(self._browse_file)
        self.play_button.clicked.connect(self._toggle_play)
        self.step_back_button.clicked.connect(self._frame_back)
        self.step_forward_button.clicked.connect(self._frame_forward)
        self.mark_in_button.clicked.connect(self._mark_in)
        self.mark_out_button.clicked.connect(self._mark_out)
        self.goto_in_button.clicked.connect(self._goto_in)
        self.goto_out_button.clicked.connect(self._goto_out)
        self.in_input.editingFinished.connect(self._on_in_input_changed)
        self.out_input.editingFinished.connect(self._on_out_input_changed)
        self.loop_checkbox.toggled.connect(self._toggle_loop)
        self.export_button.clicked.connect(self._export_clip)
        self.cancel_export_button.clicked.connect(self._cancel_export)
        self.seek_slider.sliderPressed.connect(self._on_seek_start)
        self.seek_slider.sliderReleased.connect(self._on_seek_end)
        self.seek_slider.valueChanged.connect(self._on_seek_change)
        self.seek_slider.marksChanged.connect(self._on_marks_changed)

        # Crop controls signals
        if ENABLE_CROP_FEATURE:
            self.crop_checkbox.toggled.connect(self._on_crop_toggled)
            self.crop_ratio_combo.currentIndexChanged.connect(
                self._on_crop_ratio_changed
            )
            # Connect overlay drag to update position state
            self.video_view.crop_overlay.positionChanged.connect(
                self._on_crop_overlay_dragged
            )
            # Connect custom crop resize signal
            self.video_view.crop_overlay.customCropChanged.connect(
                self._on_custom_crop_changed
            )

        self.setFocusPolicy(Qt.StrongFocus)

    def _wire_shortcuts(self) -> None:
        # Most shortcuts are defined on menu actions in _build_menu_bar().
        # Only add shortcuts here for actions not in the menu.
        QShortcut(QKeySequence("E"), self, activated=self._export_clip)

    def _open_url(self, use_cookies: bool = False) -> None:
        if not use_cookies:
            self._cookie_retry_attempted = False
            self._media_access_prompted = False
        else:
            self._cookie_retry_attempted = True

        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Invalid input", "Enter a URL or choose a file.")
            return

        parsed = urlparse(url)
        is_http = parsed.scheme in ("http", "https")
        is_file_scheme = parsed.scheme == "file"

        if is_http:
            ok, error = validate_url(url)
            if not ok:
                QMessageBox.warning(self, "Invalid URL", error)
                return
            if parsed.hostname and parsed.hostname.endswith(
                ("youtube.com", "youtu.be")
            ):
                if shutil.which("yt-dlp") is None:
                    choice = QMessageBox.question(
                        self,
                        "yt-dlp missing",
                        "YouTube URLs require yt-dlp. Continue anyway?",
                    )
                    if choice != QMessageBox.StandardButton.Yes:
                        return
        else:
            if is_file_scheme:
                local_path = Path(parsed.path)
            else:
                local_path = Path(url)

            if not local_path.exists():
                QMessageBox.warning(self, "File not found", str(local_path))
                return
            ok, error = validate_local_media_path(local_path)
            if not ok:
                QMessageBox.warning(self, "Invalid media file", error)
                return
            url = str(local_path)

        self._in_mark = None
        self._out_mark = None
        self._log_offset = 0
        self._livestream_detected = False
        self._cache_start = 0.0
        self._cache_end = 0.0
        self._following_live = True
        self._stream_start_pos = None
        self._seek_target = None
        self._cleanup_cache_dump()
        logger.info("Opening video", extra={"url": url[:200]})  # Truncate long URLs
        try:
            if use_cookies:
                self._log_message(
                    "Retrying with browser cookies for media access...", status=True
                )
            self.video_view.open_url(url, use_cookies=use_cookies)
            logger.info("Video opened successfully")
            if not self._incognito_enabled:
                add_recent_media(url)
                self._update_recent_menu()
        except (FileNotFoundError, RuntimeError) as exc:
            logger.error(
                "Failed to open video", exc_info=True, extra={"url": url[:200]}
            )
            QMessageBox.warning(self, "MPV Error", str(exc))
        except Exception as exc:
            logger.exception("Unexpected error opening video", extra={"url": url[:200]})
            QMessageBox.warning(self, "Unexpected Error", str(exc))

    def _menu_open_url(self) -> None:
        """Show dialog to enter a URL and open it."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Open URL")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout(dialog)

        label = QLabel("Enter video URL:")
        layout.addWidget(label)

        url_input = QLineEdit()
        url_input.setPlaceholderText("https://...")
        layout.addWidget(url_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Open URL")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            url = url_input.text().strip()
            if url:
                self.url_input.setText(url)
                self._open_url()

    def _update_recent_menu(self) -> None:
        """Rebuild the Open Recent submenu."""
        if self._recent_menu is None:
            return
        self._recent_menu.clear()
        recent = get_recent_media()

        if recent:
            for path in recent:
                display = path if len(path) <= 60 else "..." + path[-57:]
                action = self._recent_menu.addAction(display)
                action.triggered.connect(lambda checked, p=path: self._open_recent(p))

            self._recent_menu.addSeparator()
            clear_action = self._recent_menu.addAction("Clear Recents")
            clear_action.triggered.connect(self._clear_recents)
        else:
            no_recent = self._recent_menu.addAction("(No recent items)")
            no_recent.setEnabled(False)

    def _open_recent(self, path: str) -> None:
        """Open a recently used media path/URL."""
        self.url_input.setText(path)
        self._open_url()

    def _clear_recents(self) -> None:
        """Clear the recent media list."""
        clear_recent_media()
        self._update_recent_menu()

    def _close_media(self) -> None:
        """Close current media and reset app to initial state."""
        self.video_view.close()
        self._in_mark = None
        self._out_mark = None
        self._duration = None
        self._fps = None
        self._log_offset = 0
        self._cleanup_cache_dump()
        self.url_input.clear()
        self._status_bar.showMessage("Ready")
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setValue(0)
        self.in_input.clear()
        self.out_input.clear()
        self.time_label.setText("Time: --")
        self.seek_slider.set_marks(None, None)
        if self.loop_checkbox.isChecked():
            self.loop_checkbox.setChecked(False)

    def _show_preferences(self) -> None:
        """Show preferences dialog."""
        from vslicer_core.browser_profiles import get_browser_profiles

        dialog = QDialog(self)
        dialog.setWindowTitle("Preferences")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout(dialog)

        # Section: Browser for Cookies
        group = QGroupBox("Browser Cookies")
        group_layout = QVBoxLayout(group)

        profile_combo = QComboBox()
        detected = get_browser_profiles()
        for display_name, value in detected:
            profile_combo.addItem(display_name, value)
        profile_combo.addItem("Custom...", "custom")

        custom_widget = QWidget()
        custom_layout = QHBoxLayout(custom_widget)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_input = QLineEdit()
        custom_input.setPlaceholderText("firefox:/path/to/profile")
        browse_btn = QPushButton("Browse...")
        custom_layout.addWidget(custom_input, stretch=1)
        custom_layout.addWidget(browse_btn)
        custom_widget.hide()

        help_text = QLabel(
            "Enter browser and profile path for cookie access.\n"
            "Format: BROWSER:/path/to/profile\n\n"
            "Profile locations:\n"
            "  Firefox (Linux): ~/.mozilla/firefox/<profile>/\n"
            "  Chrome (Linux): ~/.config/google-chrome/<Profile>/\n"
            "  Firefox (macOS): ~/Library/Application Support/Firefox/Profiles/\n"
            "  Chrome (macOS): ~/Library/Application Support/Google/Chrome/"
        )
        help_text.setStyleSheet("color: gray; font-size: 10px;")
        help_text.setWordWrap(True)
        help_text.hide()

        def on_combo_changed(_index: int) -> None:
            is_custom = profile_combo.currentData() == "custom"
            custom_widget.setVisible(is_custom)
            help_text.setVisible(is_custom)

        profile_combo.currentIndexChanged.connect(on_combo_changed)

        def on_browse() -> None:
            path = QFileDialog.getExistingDirectory(
                dialog, "Select Browser Profile Directory"
            )
            if path:
                path_lower = path.lower()
                if "firefox" in path_lower or ".mozilla" in path_lower:
                    browser = "firefox"
                elif "chrom" in path_lower:
                    browser = "chrome"
                elif "edge" in path_lower:
                    browser = "edge"
                elif "brave" in path_lower:
                    browser = "brave"
                else:
                    browser = "firefox"
                custom_input.setText(f"{browser}:{path}")

        browse_btn.clicked.connect(on_browse)

        current = get_cookies_browser()
        found = False
        for i in range(profile_combo.count() - 1):
            if profile_combo.itemData(i) == current:
                profile_combo.setCurrentIndex(i)
                found = True
                break
        if not found and current:
            profile_combo.setCurrentIndex(profile_combo.count() - 1)
            custom_input.setText(current)
            custom_widget.show()
            help_text.show()

        group_layout.addWidget(profile_combo)
        group_layout.addWidget(custom_widget)
        group_layout.addWidget(help_text)
        layout.addWidget(group)

        # Section: Cache
        cache_group = QGroupBox("Demuxer Cache")
        cache_layout = QHBoxLayout(cache_group)
        cache_label = QLabel("Cache size (MB):")
        cache_input = QLineEdit()
        cache_input.setPlaceholderText("1024")
        cache_input.setText(str(get_cache_size_mb()))
        cache_label_hint = QLabel(
            "Controls how much stream data mpv buffers for export."
        )
        cache_label_hint.setStyleSheet("color: gray; font-size: 10px;")
        cache_layout.addWidget(cache_label)
        cache_layout.addWidget(cache_input)
        cache_group_layout = QVBoxLayout()
        cache_group_layout.addLayout(cache_layout)
        cache_group_layout.addWidget(cache_label_hint)
        cache_group.setLayout(cache_group_layout)
        layout.addWidget(cache_group)

        layout.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            if profile_combo.currentData() == "custom":
                value = custom_input.text().strip() or "firefox"
            else:
                value = profile_combo.currentData()
            set_cookies_browser(value)
            try:
                cache_mb = int(cache_input.text().strip())
                set_cache_size_mb(cache_mb)
            except ValueError:
                pass

    def _toggle_incognito(self) -> None:
        self._set_incognito_enabled(not self._incognito_enabled)

    def _set_incognito_enabled(self, enabled: bool) -> None:
        if self._incognito_enabled == enabled:
            return
        self._incognito_enabled = enabled
        if enabled:
            set_media_access_policy_override("deny")
            self.setWindowTitle(f"VSlicer v{APP_VERSION} - Incognito Mode")
            if self._incognito_action is not None:
                self._incognito_action.setText("Disable Incognito")
        else:
            set_media_access_policy_override(None)
            self.setWindowTitle(f"VSlicer v{APP_VERSION}")
            if self._incognito_action is not None:
                self._incognito_action.setText("Activate Incognito")
        set_incognito_enabled(enabled)

    def _browse_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Open video file")
        if filename:
            self.url_input.setText(filename)
            self._open_url()

    def _toggle_play(self) -> None:
        client = self.video_view.client
        if not client:
            return
        paused = client.get_property("pause", timeout=0.1)
        if paused:
            client.play()
        else:
            client.pause()

    def _frame_back(self) -> None:
        if self.video_view.client:
            self.video_view.client.frame_back_step()

    def _frame_forward(self) -> None:
        if self.video_view.client:
            self.video_view.client.frame_step()

    def _mark_in(self) -> None:
        if not self.video_view.client:
            return
        pos = self.video_view.client.get_time_pos(timeout=0.5)
        if pos is None:
            return
        self._in_mark = pos
        self._normalize_marks()
        if self.loop_checkbox.isChecked() and self._out_mark is not None:
            self._apply_loop()
        self.seek_slider.set_marks(
            int(self._in_mark * 1000) if self._in_mark is not None else None,
            int(self._out_mark * 1000) if self._out_mark is not None else None,
        )
        self._refresh_status()

    def _mark_out(self) -> None:
        if not self.video_view.client:
            return
        pos = self.video_view.client.get_time_pos(timeout=0.5)
        if pos is None:
            return
        self._out_mark = pos
        self._normalize_marks()
        if self.loop_checkbox.isChecked() and self._in_mark is not None:
            self._apply_loop()
        self.seek_slider.set_marks(
            int(self._in_mark * 1000) if self._in_mark is not None else None,
            int(self._out_mark * 1000) if self._out_mark is not None else None,
        )
        self._refresh_status()

    def _reset_marks(self) -> None:
        self._in_mark = None
        self._out_mark = None
        self.in_input.clear()
        self.out_input.clear()
        self.seek_slider.set_marks(None, None)
        if self.loop_checkbox.isChecked():
            self.loop_checkbox.setChecked(False)

    def _export_clip(self) -> None:
        if not self.video_view.client:
            return
        if self._in_mark is None or self._out_mark is None:
            QMessageBox.information(self, "Export", "Set IN and OUT points first.")
            return

        source_url = self.video_view.url or ""
        is_remote = source_url.startswith(("http://", "https://"))
        export_url = source_url
        self._cache_dump_path = None

        if is_remote and self.video_view.client:
            temp_dir = Path(__file__).resolve().parent.parent.parent / "temp"
            temp_dir.mkdir(exist_ok=True)
            dump_path = temp_dir / f"vslicer-cache-dump-{int(time.time())}.mkv"

            self.video_view.client.set_property("ab-loop-a", self._in_mark)
            self.video_view.client.set_property("ab-loop-b", self._out_mark)
            self.video_view.client.ab_loop_align_cache()
            aligned_start = self.video_view.client.get_property(
                "ab-loop-a", timeout=0.5
            )
            if aligned_start is not None:
                self._cache_dump_offset = self._in_mark - float(aligned_start)
            else:
                self._cache_dump_offset = 0.0

            self._log_message("Dumping cached segment for export...", status=True)
            ok = self.video_view.client.ab_loop_dump_cache(str(dump_path))

            if not self.loop_checkbox.isChecked():
                self.video_view.client.set_property("ab-loop-a", "no")
                self.video_view.client.set_property("ab-loop-b", "no")

            if ok and dump_path.exists() and dump_path.stat().st_size > 0:
                export_url = str(dump_path)
                self._cache_dump_path = dump_path
                self._log_message("Cache dump ready.", status=True)
            else:
                self._log_message(
                    "Cache dump failed; exporting from URL directly.", status=True
                )

        try:
            if self._cache_dump_path:
                offset = self._cache_dump_offset
                clip_duration = self._out_mark - self._in_mark
                spec = build_clip_spec(
                    url=export_url,
                    in_mark=offset,
                    out_mark=offset + clip_duration,
                )
            else:
                spec = build_clip_spec(
                    url=export_url,
                    in_mark=self._in_mark,
                    out_mark=self._out_mark,
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid clip", str(exc))
            return

        current_url = self.url_input.text().strip()
        audio_only_input = Path(current_url).suffix.lower() == ".mp3"

        # For livestreams, dump the cache first since ffmpeg can't seek to
        # historical timestamps in a live stream
        if self.video_view.is_livestream:
            self._log_message("Livestream detected - dumping cache for export...", status=True)
            cache_path = self._dump_livestream_cache()
            if cache_path is None:
                QMessageBox.warning(
                    self,
                    "Export Error",
                    "Failed to dump livestream cache. The buffered content may not "
                    "be available. Try marking a shorter clip or ensure the content "
                    "is still in mpv's buffer.",
                )
                return
            # Probe the actual duration of the dumped file
            actual_duration = get_video_duration(str(cache_path))
            if actual_duration is None:
                actual_duration = self._out_mark - self._in_mark
                logger.warning(
                    "Could not probe cache duration, using calculated duration",
                    extra={"calculated": actual_duration},
                )
            else:
                logger.info(
                    "Cache duration probed",
                    extra={
                        "actual": actual_duration,
                        "requested": self._out_mark - self._in_mark,
                    },
                )
            # Export the entire dumped file (from 0 to actual duration)
            try:
                spec = build_clip_spec(
                    url=str(cache_path),
                    in_mark=0.0,
                    out_mark=actual_duration,
                )
            except ValueError as exc:
                QMessageBox.warning(self, "Invalid clip", str(exc))
                self._cleanup_cache_dump()
                return

        dialog = ExportDialog(self, audio_only_input=audio_only_input)
        if dialog.exec() != QDialog.Accepted:
            return

        options = dialog.get_options()
        if options is None:
            return

        # Add crop options if enabled
        crop_options = self._get_crop_options()
        if crop_options is not None:
            from dataclasses import replace

            options = replace(options, crop=crop_options)

        # Fast copy from cache dump: just copy the raw MKV directly
        if self._cache_dump_path and options.mode == "fast_copy":
            try:
                shutil.copy2(str(self._cache_dump_path), str(options.output_path))
            except OSError as e:
                QMessageBox.warning(
                    self, "Export Error", f"Failed to copy cache dump: {e}"
                )
            else:
                self._log_message(
                    f"Export complete: {options.output_path}", status=True
                )
            self._cleanup_cache_dump()
            return

        if self._export_thread and self._export_thread.isRunning():
            QMessageBox.information(self, "Export", "Export is already running.")
            return

        logger.info(
            "Starting export",
            extra={
                "output_path": str(options.output_path),
                "duration": spec.duration,
                "mode": options.mode,
                "has_crop": crop_options is not None,
            },
        )

        self._export_thread = QThread(self)
        worker = ExportWorker(spec, options)
        self._export_worker = worker
        worker.moveToThread(self._export_thread)
        self._export_thread.started.connect(worker.run)
        worker.progress.connect(self._log_message)
        worker.progress_percent.connect(self._update_export_progress)
        worker.finished.connect(self._on_export_result)
        worker.finished.connect(self._export_thread.quit)
        worker.finished.connect(worker.deleteLater)
        self._export_thread.finished.connect(self._on_export_thread_finished)
        self._export_thread.finished.connect(self._export_thread.deleteLater)

        self._log_message("Starting export...", status=True)
        self.export_button.setEnabled(False)
        self.cancel_export_button.setEnabled(True)
        self._export_thread.start()

    def _refresh_status(self) -> None:
        time_pos = None
        duration = None
        if self.video_view.client:
            # For livestreams, try playback-time first (more accurate for cached content)
            if self.video_view.is_livestream:
                time_pos = self.video_view.client.get_property(
                    "playback-time", timeout=0.1
                )
            if time_pos is None:
                time_pos = self.video_view.client.get_time_pos(timeout=0.1)
            duration = self.video_view.client.get_property("duration", timeout=0.1)
            fps = self.video_view.client.get_property("container-fps", timeout=0.1)
            if not fps:
                fps = self.video_view.client.get_property("fps", timeout=0.1)
            if fps:
                self._fps = float(fps)
            # Update video aspect ratio for crop overlay
            self.video_view.update_video_aspect_ratio()

        # Detect livestream once
        if not self._livestream_detected and self.video_view.client:
            self._livestream_detected = True
            self.video_view.detect_livestream()
            if self.video_view.is_livestream:
                logger.info("Livestream detected - using cache for seeking and export")

        # For livestreams, calculate cache window from when we started watching
        if self.video_view.is_livestream and time_pos is not None:
            # Get the live edge from seekable range
            seekable = self.video_view.client.get_seekable_range(timeout=0.1)
            live_edge = seekable[1] if seekable else time_pos

            # Record starting position on first refresh
            if self._stream_start_pos is None:
                self._stream_start_pos = live_edge
                logger.info(f"Livestream started at position {live_edge:.1f}s")

            # Only update cache window when following live
            # When rewound, freeze the window so slider doesn't snap back
            if self._following_live:
                max_cache_duration = 45 * 60  # 45 minutes
                self._cache_start = max(
                    self._stream_start_pos, live_edge - max_cache_duration
                )
                self._cache_end = live_edge

                cache_duration = self._cache_end - self._cache_start
                # Update slider range
                new_range = int(cache_duration * 1000)
                if new_range > 0 and self.seek_slider.maximum() != new_range:
                    self.seek_slider.setRange(0, new_range)
                # Set initial marks if not set
                if self._in_mark is None and self._out_mark is None:
                    self._in_mark = self._cache_start
                    self._out_mark = self._cache_end
        elif duration:
            # Normal file with duration
            if self._duration != duration:
                self._duration = duration
                self._cache_start = 0.0
                self._cache_end = duration
                self.seek_slider.setRange(0, int(duration * 1000))
                if self._in_mark is None and self._out_mark is None:
                    self._in_mark = 0.0
                    self._out_mark = duration

        if time_pos is not None and not self._slider_dragging:
            if self.video_view.is_livestream:
                cache_duration = self._cache_end - self._cache_start
                if self._following_live:
                    # Following live: keep slider at far right
                    self.seek_slider.setValue(self.seek_slider.maximum())
                    self._seek_target = None
                elif self._seek_target is not None:
                    # Use our tracked position (mpv's time_pos is unreliable)
                    # Advance by ~250ms each refresh (timer interval)
                    is_paused = self.video_view.client.get_property(
                        "pause", timeout=0.1
                    )
                    if not is_paused:
                        self._seek_target += 0.25

                    # Check if we've reached the frozen cache end - resume following live
                    if self._seek_target >= self._cache_end:
                        self._following_live = True
                        self._seek_target = None
                        self.seek_slider.setValue(self.seek_slider.maximum())
                        logger.info("Playback reached cache end, resuming follow-live")
                    else:
                        slider_value = self._seek_target - self._cache_start
                        self.seek_slider.setValue(int(slider_value * 1000))
                else:
                    # Fallback to time_pos
                    slider_value = time_pos - self._cache_start
                    slider_value = max(0, min(slider_value, cache_duration))
                    self.seek_slider.setValue(int(slider_value * 1000))
            else:
                # Normal file playback
                slider_value = time_pos - self._cache_start
                slider_value = max(
                    0, min(slider_value, self._cache_end - self._cache_start)
                )
                self.seek_slider.setValue(int(slider_value * 1000))

        if time_pos is not None:
            # For livestreams, show "LIVE" when at the live edge (within 2 seconds)
            if self.video_view.is_livestream and self._cache_end > 0:
                distance_from_live = self._cache_end - time_pos
                if distance_from_live < 2.0:
                    self.time_label.setText("Time: LIVE")
                else:
                    # Show how far behind live we are
                    behind = int(distance_from_live)
                    mins = behind // 60
                    secs = behind % 60
                    self.time_label.setText(f"Time: -{mins:02d}:{secs:02d}")
            else:
                minutes = int(time_pos // 60)
                seconds = time_pos % 60
                self.time_label.setText(f"Time: {minutes:02d}:{seconds:06.3f}")
        else:
            self.time_label.setText("Time: --")

        if self._in_mark is not None:
            if not self.in_input.hasFocus():
                self.in_input.setText(f"{self._in_mark:.3f}")
            self.in_label.setStyleSheet("color: #2e7d32;")
        else:
            self.in_label.setStyleSheet("")
            if not self.in_input.hasFocus():
                self.in_input.setText("--")

        if self._out_mark is not None:
            if not self.out_input.hasFocus():
                self.out_input.setText(f"{self._out_mark:.3f}")
            self.out_label.setStyleSheet("color: #c62828;")
        else:
            self.out_label.setStyleSheet("")
            if not self.out_input.hasFocus():
                self.out_input.setText("--")

    def _cancel_export(self) -> None:
        if not self._export_worker or not self._export_thread:
            return
        if not self._export_thread.isRunning():
            return
        self._log_message("Canceling export...", status=True)
        self._export_worker.cancel()

        in_ms = int(self._in_mark * 1000) if self._in_mark is not None else None
        out_ms = int(self._out_mark * 1000) if self._out_mark is not None else None
        self.seek_slider.set_marks(in_ms, out_ms)

    def _refresh_log(self) -> None:
        log_path = self.video_view.log_path
        if not log_path or not log_path.exists():
            return

        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self._log_offset)
                new_data = handle.read()
                self._log_offset = handle.tell()
        except OSError:
            return

        if new_data:
            filtered = self._filter_log_lines(new_data)
            if filtered:
                self._log_message(filtered)
            self._handle_media_access_warning(new_data)

    @staticmethod
    def _filter_log_lines(data: str) -> str:
        keep_tokens = ("[e]", "[w]", "ERROR:", "WARNING:", "Failed", "failed")
        kept = []
        for line in data.splitlines():
            if any(token in line for token in keep_tokens):
                kept.append(line)
        if kept:
            return "\n".join(kept) + "\n"
        return ""

    def _goto_in(self) -> None:
        if not self.video_view.client or self._in_mark is None:
            return
        self.video_view.client.pause()
        self.video_view.client.seek(self._in_mark, "absolute")

    def _goto_out(self) -> None:
        if not self.video_view.client or self._out_mark is None:
            return
        self.video_view.client.pause()
        self.video_view.client.seek(self._out_mark, "absolute")

    def _on_seek_start(self) -> None:
        self._slider_dragging = True

    def _on_seek_end(self) -> None:
        self._slider_dragging = False
        if not self.video_view.client:
            return
        # For livestreams, we may not have duration but still allow seeking
        if self._duration is None and not self.video_view.is_livestream:
            return
        target_time = self.seek_slider.value() / 1000.0 + self._cache_start
        # Clamp to valid cache range for livestreams
        if self.video_view.is_livestream and self._cache_end > 0:
            target_time = max(self._cache_start, min(target_time, self._cache_end))
            # Toggle follow-live mode: only follow live if seeking to far right
            at_live_edge = self.seek_slider.value() >= self.seek_slider.maximum() - 2000
            self._following_live = at_live_edge
            # Track our own position when not following live
            self._seek_target = None if at_live_edge else target_time
            logger.info(
                f"Seek end: target={target_time:.1f}, "
                f"at_live_edge={at_live_edge}, seek_target={self._seek_target}"
            )
        self.video_view.client.seek(target_time, "absolute")

    def _on_seek_change(self, value: int) -> None:
        if self._slider_dragging:
            seconds = value / 1000.0
            target_time = seconds + self._cache_start

            # For livestreams, clamp and show relative time
            if self.video_view.is_livestream and self._cache_end > 0:
                target_time = max(self._cache_start, min(target_time, self._cache_end))
                distance_from_live = self._cache_end - target_time
                if distance_from_live < 2.0:
                    self.time_label.setText("Time: LIVE")
                else:
                    behind = int(distance_from_live)
                    mins = behind // 60
                    secs = behind % 60
                    self.time_label.setText(f"Time: -{mins:02d}:{secs:02d}")
            else:
                minutes = int(target_time // 60)
                secs = target_time % 60
                self.time_label.setText(f"Time: {minutes:02d}:{secs:06.3f}")

            if self.video_view.client:
                self.video_view.client.seek(target_time, "absolute")

    def _on_marks_changed(self, in_ms: int, out_ms: int) -> None:
        # Add cache offset for actual timestamps
        self._in_mark = in_ms / 1000.0 + self._cache_start
        self._out_mark = out_ms / 1000.0 + self._cache_start
        self._normalize_marks()
        if self.loop_checkbox.isChecked():
            self._apply_loop()
        self._refresh_status()

    def _parse_time_frames(self, text: str) -> float | None:
        raw = text.strip()
        if not raw or raw == "--":
            return None
        if "/" in raw:
            left, right = raw.split("/", 1)
            left = left.strip()
            right = right.strip()
            if left:
                try:
                    return float(left)
                except ValueError:
                    return None
            if right and self._fps:
                try:
                    return float(right) / self._fps
                except ValueError:
                    return None
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    def _on_in_input_changed(self) -> None:
        if self._duration is None:
            return
        value = self._parse_time_frames(self.in_input.text())
        if value is None:
            return
        self._in_mark = max(0.0, min(value, self._duration))
        self._normalize_marks()
        if self.video_view.client:
            self.video_view.client.pause()
            self.video_view.client.seek(self._in_mark, "absolute")
        self.seek_slider.set_marks(
            int(self._in_mark * 1000),
            int(self._out_mark * 1000) if self._out_mark is not None else None,
        )
        self._refresh_status()

    def _on_out_input_changed(self) -> None:
        if self._duration is None:
            return
        value = self._parse_time_frames(self.out_input.text())
        if value is None:
            return
        self._out_mark = max(0.0, min(value, self._duration))
        self._normalize_marks()
        if self.video_view.client:
            self.video_view.client.pause()
            self.video_view.client.seek(self._out_mark, "absolute")
        self.seek_slider.set_marks(
            int(self._in_mark * 1000) if self._in_mark is not None else None,
            int(self._out_mark * 1000),
        )
        self._refresh_status()

    def _normalize_marks(self) -> None:
        if self._in_mark is None or self._out_mark is None:
            return
        if self._out_mark < self._in_mark:
            self._in_mark, self._out_mark = self._out_mark, self._in_mark

    def _toggle_loop(self, enabled: bool) -> None:
        if not self.video_view.client:
            self.loop_checkbox.setChecked(False)
            return
        if enabled and (self._in_mark is None or self._out_mark is None):
            QMessageBox.information(self, "Loop", "Set IN and OUT points first.")
            self.loop_checkbox.setChecked(False)
            return
        if enabled:
            self._apply_loop()
        else:
            self.video_view.client.set_property("ab-loop-a", "no")
            self.video_view.client.set_property("ab-loop-b", "no")

    def _apply_loop(self) -> None:
        if (
            not self.video_view.client
            or self._in_mark is None
            or self._out_mark is None
        ):
            return
        self.video_view.client.set_property("ab-loop-a", self._in_mark)
        self.video_view.client.set_property("ab-loop-b", self._out_mark)
        self.video_view.client.seek(self._in_mark, "absolute")
        self.video_view.client.play()

    def _log_message(self, text: str, status: bool = False) -> None:
        """Write message to GUI log file. If status=True, also show in status bar."""
        try:
            with self._gui_log_path.open("a", encoding="utf-8") as f:
                f.write(text.rstrip("\n") + "\n")
        except OSError:
            pass
        if status:
            self._status_bar.showMessage(text.strip())

    def _handle_media_access_warning(self, new_data: str) -> None:
        if not get_config().enable_cookie_fallback:
            return
        if self._cookie_retry_attempted or self._media_access_prompted:
            return
        if not self._has_media_access_error(new_data):
            return

        policy = get_media_access_policy()
        if policy == "deny":
            return

        if policy == "allow":
            self._retry_with_cookies()
            return

        self._media_access_prompted = True
        checkbox = QCheckBox("Don't show this again")
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle("Content unavailable")
        dialog.setText(
            "Content unavailable. Enable permission to use browser for media access?"
        )
        allow_button = dialog.addButton("Allow", QMessageBox.AcceptRole)
        dialog.addButton("Cancel", QMessageBox.RejectRole)
        dialog.setCheckBox(checkbox)
        dialog.exec()

        if dialog.clickedButton() == allow_button:
            if checkbox.isChecked():
                set_media_access_policy("allow")
            else:
                set_media_access_policy_override("allow")
            self._retry_with_cookies()
        else:
            if checkbox.isChecked():
                set_media_access_policy("deny")

    def _retry_with_cookies(self) -> None:
        if self._cookie_retry_attempted:
            return
        self._cookie_retry_attempted = True
        url = self.url_input.text().strip()
        if not url:
            return
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return
        self._open_url(use_cookies=True)

    @staticmethod
    def _has_media_access_error(new_data: str) -> bool:
        triggers = (
            "Failed to recognize file format.",
            "This content may be inappropriate: It's unavailable for certain audiences.",
        )
        return any(trigger in new_data for trigger in triggers)

    def _update_export_progress(self, percent: float) -> None:
        self.export_label.setText(f"Export: {percent:5.1f}%")

    def _cleanup_cache_dump(self) -> None:
        if self._cache_dump_path and self._cache_dump_path.exists():
            try:
                self._cache_dump_path.unlink()
            except OSError:
                pass
            self._cache_dump_path = None

    def _on_export_result(self, result) -> None:
        """Handle export result (update UI)."""
        self._cleanup_cache_dump()
        if result.ok:
            logger.info(
                "Export completed successfully",
                extra={"output_path": str(result.output_path)},
            )
            self._log_message(f"Export complete: {result.output_path}", status=True)
            self.export_label.setText("Export: 100.0%")
        else:
            logger.error(
                "Export failed",
                extra={
                    "error": result.error,
                    "has_ffmpeg_log": bool(result.ffmpeg_log),
                },
            )
            detail = result.error or "Unknown error"
            if result.ffmpeg_log:
                self._log_message(result.ffmpeg_log.strip())
                detail += "\n\n" + result.ffmpeg_log.strip()[-500:]
            self._log_message(f"Export failed: {result.error}", status=True)
            QMessageBox.warning(self, "Export Failed", detail)
            self.export_label.setText("Export: --")
        self.export_button.setEnabled(True)
        self.cancel_export_button.setEnabled(False)
        # Note: Don't clear _export_thread here - thread may still be running

    def _on_export_thread_finished(self) -> None:
        """Clean up thread reference after thread actually stops."""
        self._export_thread = None
        self._export_worker = None
        # Clean up cache dump file after export completes
        self._cleanup_cache_dump()

    # Crop feature handlers
    def _on_crop_toggled(self, enabled: bool) -> None:
        self._crop_enabled = enabled
        if ENABLE_CROP_FEATURE:
            self.crop_ratio_combo.setEnabled(enabled)
            # Update crop overlay
            self.video_view.crop_overlay.set_crop_enabled(enabled)
            if enabled:
                self.video_view.crop_overlay.set_aspect_ratio(self._crop_ratio)
                self.video_view.crop_overlay.set_position(self._crop_position)

    def _on_crop_ratio_changed(self) -> None:
        if ENABLE_CROP_FEATURE:
            self._crop_ratio = self.crop_ratio_combo.currentData()
            if self._crop_ratio != "custom":
                # Clear custom mode when selecting a preset
                self._custom_width_ratio = None
                self.video_view.crop_overlay.clear_custom_crop()
            # Update crop overlay
            self.video_view.crop_overlay.set_aspect_ratio(self._crop_ratio)

    def _on_crop_overlay_dragged(self, value: int) -> None:
        """Handle position change from dragging the crop overlay."""
        self._crop_position = value / 100.0
        if ENABLE_CROP_FEATURE:
            # Overlay already reflects the position.
            pass

    def _on_custom_crop_changed(self, width_ratio: float) -> None:
        """Handle custom crop width change from resizing the overlay."""
        self._custom_width_ratio = width_ratio
        self._crop_ratio = "custom"
        if ENABLE_CROP_FEATURE:
            # Update dropdown to show "Custom" without triggering signal
            self.crop_ratio_combo.blockSignals(True)
            custom_index = self.crop_ratio_combo.findData("custom")
            if custom_index >= 0:
                self.crop_ratio_combo.setCurrentIndex(custom_index)
            self.crop_ratio_combo.blockSignals(False)

    def _cleanup_cache_dump(self) -> None:
        """Clean up any temporary cache dump file."""
        if self._cache_dump_path and self._cache_dump_path.exists():
            try:
                self._cache_dump_path.unlink()
                logger.info(
                    "Cleaned up cache dump file",
                    extra={"path": str(self._cache_dump_path)},
                )
            except OSError as exc:
                logger.warning(
                    "Failed to clean up cache dump file",
                    extra={"path": str(self._cache_dump_path), "error": str(exc)},
                )
        self._cache_dump_path = None

    def _dump_livestream_cache(self) -> Path | None:
        """Dump the livestream cache to a temporary file for export.

        Uses the current A-B loop points (which define the preview loop)
        to ensure the exported content matches exactly what was previewed.

        Returns:
            Path to the dumped cache file, or None if dump failed
        """
        # Clean up any previous cache dump
        self._cleanup_cache_dump()

        # Ensure A-B loop points are set
        if self._in_mark is None or self._out_mark is None:
            logger.error("Cannot dump cache without IN/OUT marks set")
            return None

        # Set A-B loop points in mpv (they may already be set from preview)
        client = self.video_view.client
        if not client:
            logger.error("No mpv client available for cache dump")
            return None

        client.set_property("ab-loop-a", self._in_mark)
        client.set_property("ab-loop-b", self._out_mark)

        # Align loop points to keyframes in the cache
        # This is critical for accurate timing - without alignment,
        # the dump may start/end at arbitrary positions
        if client.ab_loop_align_cache():
            logger.info("A-B loop points aligned to keyframes")
        else:
            logger.warning("Failed to align A-B loop points to keyframes")

        # Create temp file for the cache dump
        try:
            fd, cache_path = tempfile.mkstemp(prefix="vslicer-cache-", suffix=".mkv")
            os.close(fd)
            self._cache_dump_path = Path(cache_path)
        except OSError as exc:
            logger.error("Failed to create cache dump file", extra={"error": str(exc)})
            return None

        logger.info(
            "Dumping livestream cache using A-B loop points",
            extra={
                "ab_loop_a": self._in_mark,
                "ab_loop_b": self._out_mark,
                "path": str(self._cache_dump_path),
            },
        )

        # Dump the cache using A-B loop points
        if not self.video_view.ab_loop_dump_cache(str(self._cache_dump_path)):
            logger.error("Failed to dump livestream cache")
            self._cleanup_cache_dump()
            return None

        # Verify the file was created and has content
        if (
            not self._cache_dump_path.exists()
            or self._cache_dump_path.stat().st_size == 0
        ):
            logger.error("Cache dump file is empty or missing")
            self._cleanup_cache_dump()
            return None

        logger.info(
            "Livestream cache dumped successfully",
            extra={
                "path": str(self._cache_dump_path),
                "size": self._cache_dump_path.stat().st_size,
            },
        )
        return self._cache_dump_path

    def _get_crop_options(self) -> CropOptions | None:
        """Get current crop options if crop is enabled."""
        if not ENABLE_CROP_FEATURE or not self._crop_enabled:
            return None
        return CropOptions(
            aspect_ratio=self._crop_ratio,
            position=self._crop_position,
            custom_width_ratio=self._custom_width_ratio
            if self._crop_ratio == "custom"
            else None,
        )

    def moveEvent(self, event) -> None:  # noqa: N802 - Qt naming convention
        """Update crop overlay position when window moves."""
        super().moveEvent(event)
        if ENABLE_CROP_FEATURE and self._crop_enabled:
            self.video_view.crop_overlay.update_position()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming convention
        """Update crop overlay position when window resizes."""
        super().resizeEvent(event)
        if ENABLE_CROP_FEATURE and self._crop_enabled:
            self.video_view.crop_overlay.update_position()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming convention
        self._cleanup_cache_dump()
        self.video_view.close()
        self._cleanup_cache_dump()
        if self._gui_log_path and self._gui_log_path.exists():
            try:
                self._gui_log_path.unlink()
            except OSError:
                pass
        super().closeEvent(event)
