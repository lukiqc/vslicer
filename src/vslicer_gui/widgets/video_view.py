"""Video view widget that embeds mpv playback."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from vslicer_core.config import get_cache_size_mb, get_cookies_browser
from vslicer_core.mpv.client import MPVClient
from vslicer_core.mpv.ipc import create_transport, generate_ipc_path
from vslicer_core.mpv.process import MPVProcess


class VideoContainer(QFrame):
    """Container widget for embedded mpv video."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Dark background so it's visible before video loads
        self.setStyleSheet("background-color: #1a1a1a;")
        # Ensure the widget can receive a native window handle
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, False)
        self.setFrameStyle(QFrame.Box | QFrame.Plain)


class CropOverlay(QWidget):
    """Transparent overlay window that shows crop region over video.

    This is a top-level frameless window because Qt widgets cannot
    render on top of native mpv windows embedded via --wid.
    """

    # Edge detection threshold in pixels
    EDGE_THRESHOLD = 8

    # Signal emitted when position changes via drag (value 0-100)
    positionChanged = Signal(int)
    # Signal emitted when custom crop width changes (width ratio 0.0-1.0)
    customCropChanged = Signal(float)

    def __init__(
        self, parent: QWidget | None = None, main_window: QWidget | None = None
    ) -> None:
        # Create as child window of main app (so it doesn't float over other apps)
        super().__init__(main_window)
        self._parent_widget = parent  # The video container to track position of
        self._main_window = main_window

        # Frameless, transparent window
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool  # Doesn't show in taskbar
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)  # Receive mouse move events without clicking

        self._enabled = False
        self._aspect_ratio = "9:16"
        self._position = 0.5  # 0.0 = left, 1.0 = right
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_position = 0.0

        # Custom crop mode state
        self._custom_mode = False
        self._custom_width_ratio: float | None = None  # Width as ratio of video width

        # Video aspect ratio for calculating actual video bounds
        self._video_aspect_ratio: float | None = None  # width / height

        # Resize mode state
        self._resize_mode: str | None = None  # None, "left", "right"
        self._resize_start_x = 0
        self._resize_start_width_ratio = 0.0
        self._resize_start_position = 0.0

        # Start hidden
        self.hide()

    def set_main_window(self, main_window: QWidget) -> None:
        """Set the main window as parent so overlay stays with the app."""
        self._main_window = main_window
        self.setParent(main_window)
        # Re-apply window flags after reparenting
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def set_crop_enabled(self, enabled: bool) -> None:
        """Enable or disable the crop overlay."""
        self._enabled = enabled
        if enabled:
            self.update_position()
            self.show()
        else:
            self.hide()
        self.update()

    def update_position(self) -> None:
        """Update overlay position to match parent widget's screen position."""
        if self._parent_widget is None:
            return
        # Get the parent widget's position in global (screen) coordinates
        global_pos = self._parent_widget.mapToGlobal(
            self._parent_widget.rect().topLeft()
        )
        self.setGeometry(
            global_pos.x(),
            global_pos.y(),
            self._parent_widget.width(),
            self._parent_widget.height(),
        )

    def set_aspect_ratio(self, ratio: str) -> None:
        """Set the target aspect ratio (e.g., '9:16', '4:5', '1:1')."""
        self._aspect_ratio = ratio
        self.update()

    def set_position(self, position: float) -> None:
        """Set horizontal position (0.0 = left, 0.5 = center, 1.0 = right)."""
        self._position = max(0.0, min(1.0, position))
        self.update()

    def set_video_aspect_ratio(self, aspect_ratio: float | None) -> None:
        """Set the source video's aspect ratio (width/height).

        This is used to calculate where the video is actually rendered
        within the container (accounting for letterboxing).
        """
        self._video_aspect_ratio = aspect_ratio
        self.update()

    def _get_video_rect(self) -> QRect:
        """Calculate the rectangle where the video is actually rendered.

        mpv letterboxes the video to fit the container while maintaining
        aspect ratio. This calculates that actual video area.

        Returns:
            QRect of the video area within the overlay widget.
        """
        container_width = self.width()
        container_height = self.height()

        if (
            self._video_aspect_ratio is None
            or container_width <= 0
            or container_height <= 0
        ):
            # No video aspect ratio set, use full container
            return QRect(0, 0, container_width, container_height)

        container_aspect = container_width / container_height
        video_aspect = self._video_aspect_ratio

        if video_aspect > container_aspect:
            # Video is wider than container - letterbox top/bottom
            video_width = container_width
            video_height = int(container_width / video_aspect)
            video_x = 0
            video_y = (container_height - video_height) // 2
        else:
            # Video is taller than container - letterbox left/right
            video_height = container_height
            video_width = int(container_height * video_aspect)
            video_x = (container_width - video_width) // 2
            video_y = 0

        return QRect(video_x, video_y, video_width, video_height)

    def set_custom_crop(self, width_ratio: float, position: float) -> None:
        """Set custom crop mode with specified width ratio and position.

        Args:
            width_ratio: Crop width as ratio of container width (0.0-1.0)
            position: Horizontal position (0.0-1.0)
        """
        self._custom_mode = True
        self._custom_width_ratio = max(0.1, min(1.0, width_ratio))  # Min 10% width
        self._position = max(0.0, min(1.0, position))
        self.update()

    def clear_custom_crop(self) -> None:
        """Clear custom crop mode, revert to aspect ratio mode."""
        self._custom_mode = False
        self._custom_width_ratio = None
        self.update()

    def is_custom_mode(self) -> bool:
        """Check if in custom crop mode."""
        return self._custom_mode

    def get_custom_width_ratio(self) -> float | None:
        """Get the custom width ratio if in custom mode."""
        return self._custom_width_ratio if self._custom_mode else None

    def _get_edge_at_pos(self, pos) -> str | None:
        """Determine if position is near a crop rectangle edge.

        Args:
            pos: Mouse position in widget coordinates

        Returns:
            'left', 'right', or None
        """
        crop_rect = self.get_crop_rect()
        if not crop_rect:
            return None

        x = pos.x()
        y = pos.y()

        # Check if within vertical bounds of crop rect
        if not (crop_rect.top() <= y <= crop_rect.bottom()):
            return None

        # Check left edge
        if abs(x - crop_rect.left()) <= self.EDGE_THRESHOLD:
            return "left"

        # Check right edge
        if abs(x - crop_rect.right()) <= self.EDGE_THRESHOLD:
            return "right"

        return None

    def get_crop_rect(self) -> QRect | None:
        """Get the crop rectangle in widget coordinates.

        The crop is constrained to the actual video area (accounting for
        letterboxing), not the full container.
        """
        if not self._enabled:
            return None

        # Get the actual video bounds within the container
        video_rect = self._get_video_rect()
        video_width = video_rect.width()
        video_height = video_rect.height()
        video_x = video_rect.x()
        video_y = video_rect.y()

        # Crop height matches video height
        crop_height = video_height

        if self._custom_mode and self._custom_width_ratio is not None:
            # Custom mode: width ratio is relative to video width
            crop_width = int(video_width * self._custom_width_ratio)
        else:
            # Preset mode: calculate from target aspect ratio
            ratio_map = {"9:16": 9 / 16, "4:5": 4 / 5, "1:1": 1 / 1}
            target_ratio = ratio_map.get(self._aspect_ratio, 9 / 16)
            crop_width = int(crop_height * target_ratio)

        # Ensure crop width doesn't exceed video width
        if crop_width > video_width:
            crop_width = video_width

        # Calculate x position within video bounds
        max_x = video_width - crop_width
        x = video_x + int(max_x * self._position)

        return QRect(x, video_y, crop_width, crop_height)

    def paintEvent(self, event) -> None:
        """Draw the crop overlay with darkened areas outside crop region."""
        if not self._enabled:
            return

        crop_rect = self.get_crop_rect()
        if not crop_rect:
            return

        video_rect = self._get_video_rect()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fill crop area with nearly-invisible color to capture mouse events
        # (fully transparent areas don't receive mouse events)
        painter.fillRect(crop_rect, QColor(0, 0, 0, 1))

        # Dark overlay color for areas outside crop
        overlay_color = QColor(0, 0, 0, 230)

        # Darken letterbox areas (outside video bounds)
        # Top letterbox
        if video_rect.top() > 0:
            painter.fillRect(QRect(0, 0, self.width(), video_rect.top()), overlay_color)
        # Bottom letterbox
        if video_rect.bottom() < self.height():
            painter.fillRect(
                QRect(
                    0,
                    video_rect.bottom(),
                    self.width(),
                    self.height() - video_rect.bottom(),
                ),
                overlay_color,
            )
        # Left letterbox
        if video_rect.left() > 0:
            painter.fillRect(
                QRect(0, video_rect.top(), video_rect.left(), video_rect.height()),
                overlay_color,
            )
        # Right letterbox
        if video_rect.right() < self.width():
            painter.fillRect(
                QRect(
                    video_rect.right(),
                    video_rect.top(),
                    self.width() - video_rect.right(),
                    video_rect.height(),
                ),
                overlay_color,
            )

        # Darken areas within video but outside crop (left and right of crop)
        # Left side of crop (within video)
        if crop_rect.left() > video_rect.left():
            left_rect = QRect(
                video_rect.left(),
                video_rect.top(),
                crop_rect.left() - video_rect.left(),
                video_rect.height(),
            )
            painter.fillRect(left_rect, overlay_color)
        # Right side of crop (within video)
        if crop_rect.right() < video_rect.right():
            right_rect = QRect(
                crop_rect.right(),
                video_rect.top(),
                video_rect.right() - crop_rect.right(),
                video_rect.height(),
            )
            painter.fillRect(right_rect, overlay_color)

        # Draw border around crop region
        pen = QPen(QColor(0, 200, 100))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRect(crop_rect.adjusted(1, 1, -1, -1))

        painter.end()

    def mousePressEvent(self, event) -> None:
        """Start dragging or resizing based on click position."""
        if not self._enabled:
            return

        crop_rect = self.get_crop_rect()
        if not crop_rect:
            return

        # Check if clicking on an edge for resize
        edge = self._get_edge_at_pos(event.pos())
        if edge:
            self._resize_mode = edge
            self._resize_start_x = event.pos().x()
            # Store current state for resize calculation
            video_rect = self._get_video_rect()
            if self._custom_mode and self._custom_width_ratio is not None:
                self._resize_start_width_ratio = self._custom_width_ratio
            else:
                # Convert current aspect ratio to width ratio (relative to video width)
                self._resize_start_width_ratio = (
                    crop_rect.width() / video_rect.width()
                    if video_rect.width() > 0
                    else 1.0
                )
            self._resize_start_position = self._position
            self.setCursor(QCursor(Qt.SizeHorCursor))
            return

        # Check if clicking inside rectangle for drag
        if crop_rect.contains(event.pos()):
            self._dragging = True
            self._drag_start_x = event.pos().x()
            self._drag_start_position = self._position
            self.setCursor(QCursor(Qt.ClosedHandCursor))

    def mouseMoveEvent(self, event) -> None:
        """Update position while dragging or resize while resizing."""
        # Handle resize mode
        if self._resize_mode:
            self._handle_resize(event.pos())
            return

        # Handle drag mode
        if self._dragging:
            self._handle_drag(event.pos())
            return

        # Not dragging or resizing - update cursor based on position
        crop_rect = self.get_crop_rect()
        if not crop_rect:
            self.setCursor(QCursor(Qt.ArrowCursor))
            return

        # Check if near an edge
        edge = self._get_edge_at_pos(event.pos())
        if edge:
            self.setCursor(QCursor(Qt.SizeHorCursor))
        elif crop_rect.contains(event.pos()):
            self.setCursor(QCursor(Qt.OpenHandCursor))
        else:
            self.setCursor(QCursor(Qt.ArrowCursor))

    def _handle_drag(self, pos) -> None:
        """Handle dragging to move the crop rectangle."""
        crop_rect = self.get_crop_rect()
        if not crop_rect:
            return

        video_rect = self._get_video_rect()

        # How far has the mouse moved?
        delta_x = pos.x() - self._drag_start_x

        # Calculate the maximum x range within video bounds
        crop_width = crop_rect.width()
        max_x = video_rect.width() - crop_width

        if max_x <= 0:
            return

        # Convert pixel delta to position delta (0.0 to 1.0)
        position_delta = delta_x / max_x

        # New position
        new_position = self._drag_start_position + position_delta
        new_position = max(0.0, min(1.0, new_position))

        if new_position != self._position:
            self._position = new_position
            self.update()
            # Emit signal with value 0-100 for slider
            self.positionChanged.emit(int(new_position * 100))

    def _handle_resize(self, pos) -> None:
        """Handle resizing the crop rectangle by dragging an edge."""
        video_rect = self._get_video_rect()
        video_width = video_rect.width()
        if video_width <= 0:
            return

        # How far has the mouse moved from the start?
        delta_x = pos.x() - self._resize_start_x

        # Current crop width in pixels (before resize) - ratio is relative to video width
        start_crop_width = self._resize_start_width_ratio * video_width

        if self._resize_mode == "left":
            # Dragging left edge: moving left makes crop wider, moving right makes it narrower
            # Also need to adjust position to keep right edge fixed
            new_crop_width = start_crop_width - delta_x
        else:  # "right"
            # Dragging right edge: moving right makes crop wider
            new_crop_width = start_crop_width + delta_x

        # Enforce minimum and maximum width within video bounds
        min_width = video_width * 0.1  # Minimum 10% of video
        max_width = video_width
        new_crop_width = max(min_width, min(max_width, new_crop_width))

        # Convert to width ratio (relative to video width)
        new_width_ratio = new_crop_width / video_width

        # Calculate new position to maintain the appropriate edge
        if self._resize_mode == "left":
            # Keep right edge fixed: adjust position so right edge stays in place
            # right_edge = position * max_x + crop_width
            # We want: new_position * new_max_x + new_crop_width = old_right_edge
            old_max_x = video_width - start_crop_width
            old_right_edge = self._resize_start_position * old_max_x + start_crop_width
            new_max_x = video_width - new_crop_width
            if new_max_x > 0:
                new_position = (old_right_edge - new_crop_width) / new_max_x
            else:
                new_position = 0.0
        else:  # "right"
            # Keep left edge fixed: adjust position so left edge stays in place
            # left_edge = position * max_x
            # We want: new_position * new_max_x = old_left_edge
            old_max_x = video_width - start_crop_width
            old_left_edge = self._resize_start_position * old_max_x
            new_max_x = video_width - new_crop_width
            if new_max_x > 0:
                new_position = old_left_edge / new_max_x
            else:
                new_position = 0.0

        new_position = max(0.0, min(1.0, new_position))

        # Update state and emit signal
        self._custom_mode = True
        self._custom_width_ratio = new_width_ratio
        self._position = new_position
        self.update()

        # Emit signals for UI updates
        self.customCropChanged.emit(new_width_ratio)
        self.positionChanged.emit(int(new_position * 100))

    def mouseReleaseEvent(self, event) -> None:
        """End dragging or resizing."""
        was_active = self._dragging or self._resize_mode

        self._dragging = False
        self._resize_mode = None

        if was_active:
            # Update cursor based on current position
            crop_rect = self.get_crop_rect()
            if crop_rect:
                edge = self._get_edge_at_pos(event.pos())
                if edge:
                    self.setCursor(QCursor(Qt.SizeHorCursor))
                elif crop_rect.contains(event.pos()):
                    self.setCursor(QCursor(Qt.OpenHandCursor))
                else:
                    self.setCursor(QCursor(Qt.ArrowCursor))
            else:
                self.setCursor(QCursor(Qt.ArrowCursor))


class VideoView(QWidget):
    """Widget that manages mpv playback embedded in the window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mpv_process = MPVProcess()
        self._transport = create_transport()
        self._ipc_path: str | None = None
        self._client: MPVClient | None = None
        self._url: str | None = None
        self._log_path: Path | None = None
        self._is_livestream: bool = False

        # Create layout and video container
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._video_container = VideoContainer(self)
        layout.addWidget(self._video_container)

        # Create crop overlay as top-level transparent window
        # Pass video container as reference for positioning
        # main_window will be set later via set_main_window()
        self._crop_overlay = CropOverlay(self._video_container, None)

    @property
    def client(self) -> MPVClient | None:
        return self._client

    @property
    def url(self) -> str | None:
        return self._url

    @property
    def log_path(self) -> Path | None:
        return self._log_path

    @property
    def crop_overlay(self) -> CropOverlay:
        return self._crop_overlay

    @property
    def is_livestream(self) -> bool:
        """Check if the current source is a livestream (no fixed duration)."""
        return self._is_livestream

    def resizeEvent(self, event) -> None:
        """Handle resize to keep crop overlay sized correctly."""
        super().resizeEvent(event)
        # Update overlay position to match video container
        if self._crop_overlay._enabled:
            self._crop_overlay.update_position()

    def moveEvent(self, event) -> None:
        """Handle move to keep crop overlay positioned correctly."""
        super().moveEvent(event)
        if self._crop_overlay._enabled:
            self._crop_overlay.update_position()

    def showEvent(self, event) -> None:
        """Handle show to position crop overlay."""
        super().showEvent(event)
        if self._crop_overlay._enabled:
            self._crop_overlay.update_position()
            self._crop_overlay.show()

    def _get_window_id(self) -> int | None:
        """Get the native window ID for embedding mpv."""
        # Ensure the widget is shown and has a native window
        self._video_container.show()
        self._video_container.winId()  # Force native window creation
        wid = int(self._video_container.winId())
        return wid if wid != 0 else None

    def open_url(self, url: str, use_cookies: bool = False) -> None:
        """Start mpv and load the URL embedded in the widget."""
        self.close()

        self._ipc_path = generate_ipc_path()
        self._client = MPVClient(self._transport)
        self._url = url
        self._is_livestream = False  # Will be detected after video loads
        # Create secure temp file with unpredictable name
        try:
            fd, log_path = tempfile.mkstemp(prefix="vslicer-mpv-", suffix=".log")
            os.close(fd)
            self._log_path = Path(log_path)
        except OSError:
            self._log_path = None

        additional_args = []
        cache_bytes = get_cache_size_mb() * 1024 * 1024
        additional_args.append(f"--demuxer-max-bytes={cache_bytes}")
        if self._log_path:
            additional_args.append(f"--log-file={self._log_path}")
        if use_cookies:
            browser = get_cookies_browser()
            additional_args.append(f"--ytdl-raw-options=cookies-from-browser={browser}")

        # Get window ID for embedding
        wid = self._get_window_id()

        self._mpv_process.start(
            url,
            self._ipc_path,
            additional_args=additional_args,
            embedded=True,
            wid=wid,
        )
        self._client.connect(self._ipc_path)

        # Clear video aspect ratio (will be set once video loads)
        self._crop_overlay.set_video_aspect_ratio(None)

    def update_video_aspect_ratio(self) -> None:
        """Query video dimensions from mpv and update crop overlay.

        Should be called periodically after opening a video to detect
        when dimensions become available.
        """
        if not self._client:
            return

        try:
            width = self._client.get_property("width", timeout=0.1)
            height = self._client.get_property("height", timeout=0.1)
            if width and height and width > 0 and height > 0:
                aspect_ratio = width / height
                self._crop_overlay.set_video_aspect_ratio(aspect_ratio)
        except (OSError, ConnectionError, TimeoutError, ValueError):
            pass  # Video not loaded yet, IPC error, or invalid response

    def detect_livestream(self) -> bool:
        """Detect if the current source is a livestream.

        Livestreams have no fixed duration (None or infinite).
        Should be called after video loads.

        Returns:
            True if the source appears to be a livestream.
        """
        if not self._client:
            return False

        try:
            duration = self._client.get_property("duration", timeout=0.5)
            # Livestreams have no duration or infinite duration
            if duration is None or (
                isinstance(duration, (int, float)) and duration <= 0
            ):
                self._is_livestream = True
            else:
                self._is_livestream = False
        except (OSError, ConnectionError, TimeoutError, ValueError):
            self._is_livestream = False

        return self._is_livestream

    def ab_loop_dump_cache(self, output_path: str) -> bool:
        """Dump the demuxer cache using current A-B loop points.

        This saves the buffered content from mpv using the same A-B loop
        points that define the preview loop, ensuring the exported content
        matches exactly what was previewed.

        Args:
            output_path: Path to write the cached content

        Returns:
            True if successful
        """
        if not self._client:
            return False

        return self._client.ab_loop_dump_cache(output_path)

    def close(self) -> None:
        """Stop mpv and release IPC transport."""
        # Hide crop overlay and clear video aspect ratio
        self._crop_overlay.hide()
        self._crop_overlay.set_video_aspect_ratio(None)
        self._is_livestream = False

        if self._client:
            try:
                self._client.quit()
            except (OSError, ConnectionError, TimeoutError):
                pass  # mpv already closed or IPC failure
            self._client.close()
            self._client = None

        if self._mpv_process.is_running():
            self._mpv_process.stop()

        self._url = None
        self._log_path = None
