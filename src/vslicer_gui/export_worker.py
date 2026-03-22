"""Background export worker for the GUI."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from vslicer_core.config import get_logger
from vslicer_core.domain.models import ClipSpec, ExportOptions, ExportResult
from vslicer_core.services.export import run_export

logger = get_logger(__name__)


class ExportWorker(QObject):
    """Run export in a background thread."""

    progress = Signal(str)
    progress_percent = Signal(float)
    finished = Signal(ExportResult)

    def __init__(self, spec: ClipSpec, options: ExportOptions) -> None:
        super().__init__()
        self._spec = spec
        self._options = options
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        total_duration = self._spec.duration
        if self._options.slowmo:
            total_duration *= self._options.slowmo.compute_factor(self._spec.duration)
        if self._options.playback_mode == "pingpong":
            total_duration *= 2.0

        total_ms = int(total_duration * 1_000_000)

        def on_progress(data: dict) -> None:
            if "out_time_ms" in data:
                try:
                    out_time_ms = int(data["out_time_ms"])
                except ValueError:
                    return
                if total_ms > 0:
                    percent = min(100.0, (out_time_ms / total_ms) * 100.0)
                    self.progress_percent.emit(percent)

        try:
            result = run_export(
                self._spec,
                self._options,
                on_progress=on_progress,
                cancel_event=self._cancel_event,
            )
        except Exception as exc:
            logger.exception(
                "Export crashed",
                extra={
                    "output_path": str(self._options.output_path),
                    "duration": self._spec.duration,
                },
            )
            result = ExportResult(ok=False, error=str(exc))
        self.finished.emit(result)
