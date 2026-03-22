"""Seek slider with click-to-seek and selection highlight."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider


class SeekSlider(QSlider):
    """QSlider that supports click-to-seek and selection range highlight."""

    marksChanged = Signal(int, int)

    def __init__(self, orientation: Qt.Orientation, parent=None) -> None:
        super().__init__(orientation, parent)
        self._in_ms: int | None = None
        self._out_ms: int | None = None
        self._dragging_mark: str | None = None

    def set_marks(self, in_ms: int | None, out_ms: int | None) -> None:
        self._in_ms = in_ms
        self._out_ms = out_ms
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming convention
        if event.button() == Qt.LeftButton:
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            groove = self.style().subControlRect(
                QStyle.CC_Slider,
                option,
                QStyle.SC_SliderGroove,
                self,
            )
            handle = self.style().subControlRect(
                QStyle.CC_Slider,
                option,
                QStyle.SC_SliderHandle,
                self,
            )
            if self.orientation() == Qt.Horizontal:
                x = event.position().x()
                in_pos = (
                    self._value_to_pos(self._in_ms, groove)
                    if self._in_ms is not None
                    else None
                )
                out_pos = (
                    self._value_to_pos(self._out_ms, groove)
                    if self._out_ms is not None
                    else None
                )
                if in_pos is not None and abs(x - in_pos) <= 6:
                    self._dragging_mark = "in"
                    return
                if out_pos is not None and abs(x - out_pos) <= 6:
                    self._dragging_mark = "out"
                    return
                slider_min = groove.x()
                slider_max = groove.right() - handle.width() + 1
                value = QStyle.sliderValueFromPosition(
                    self.minimum(),
                    self.maximum(),
                    int(x - handle.width() / 2),
                    slider_max - slider_min,
                )
                self.setValue(value)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming convention
        if self._dragging_mark and self.orientation() == Qt.Horizontal:
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            groove = self.style().subControlRect(
                QStyle.CC_Slider,
                option,
                QStyle.SC_SliderGroove,
                self,
            )
            handle = self.style().subControlRect(
                QStyle.CC_Slider,
                option,
                QStyle.SC_SliderHandle,
                self,
            )
            x = event.position().x()
            slider_min = groove.x()
            slider_max = groove.right() - handle.width() + 1
            value = QStyle.sliderValueFromPosition(
                self.minimum(),
                self.maximum(),
                int(x - handle.width() / 2),
                slider_max - slider_min,
            )

            if self._dragging_mark == "in":
                out_limit = self._out_ms if self._out_ms is not None else self.maximum()
                self._in_ms = max(self.minimum(), min(value, out_limit))
            else:
                in_limit = self._in_ms if self._in_ms is not None else self.minimum()
                self._out_ms = min(self.maximum(), max(value, in_limit))

            if self._in_ms is not None and self._out_ms is not None:
                self.marksChanged.emit(self._in_ms, self._out_ms)
            self.update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming convention
        if self._dragging_mark:
            self._dragging_mark = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming convention
        super().paintEvent(event)
        if self._in_ms is None or self._out_ms is None:
            return
        if self.maximum() <= self.minimum():
            return

        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(
            QStyle.CC_Slider,
            option,
            QStyle.SC_SliderGroove,
            self,
        )
        if groove.width() <= 0:
            return

        in_pos = self._value_to_pos(self._in_ms, groove)
        out_pos = self._value_to_pos(self._out_ms, groove)
        left = min(in_pos, out_pos)
        right = max(in_pos, out_pos)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(46, 125, 50, 80)
        painter.fillRect(
            left,
            groove.center().y() - 3,
            right - left,
            6,
            color,
        )

        self._draw_marker(painter, groove, in_pos, Qt.green)
        self._draw_marker(painter, groove, out_pos, Qt.red)

    def _value_to_pos(self, value: int | None, groove) -> int:
        if value is None:
            return groove.x()
        span = self.maximum() - self.minimum()
        if span <= 0:
            return groove.x()
        ratio = (value - self.minimum()) / span
        return int(groove.x() + ratio * groove.width())

    def _draw_marker(
        self, painter: QPainter, groove, pos: int, color: Qt.GlobalColor
    ) -> None:
        painter.setPen(color)
        painter.setBrush(color)
        painter.drawRect(pos - 2, groove.center().y() - 6, 4, 12)
