"""Export dialog for VSlicer GUI."""

from __future__ import annotations

import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from vslicer_core.domain.models import ExportOptions, SlowMoOptions


class ExportDialog(QDialog):
    """Modal export options dialog."""

    def __init__(self, parent=None, audio_only_input: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.setModal(True)
        self._options: ExportOptions | None = None
        self._audio_only_input = audio_only_input

        self._build_ui()
        self._wire_signals()
        self._update_ui_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Output path
        self.output_path_edit = QLineEdit()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_path_edit.setText(str(Path("./clips") / f"clip_{timestamp}.webm"))
        browse_button = QPushButton("Browse")
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_path_edit)
        output_row.addWidget(browse_button)
        self._browse_button = browse_button
        form.addRow("Output", output_row)

        # Output type
        self.output_type_combo = QComboBox()
        self.output_type_combo.addItem("Video", "video")
        self.output_type_combo.addItem("Audio-only (MP3)", "audio")
        form.addRow("Type", self.output_type_combo)

        # Mode
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Accurate (re-encode)", "accurate_reencode")
        self.mode_combo.addItem("Fast (stream copy)", "fast_copy")
        form.addRow("Mode", self.mode_combo)

        # Playback direction
        self.direction_combo = QComboBox()
        self.direction_combo.addItem("Forward", "forward")
        self.direction_combo.addItem("Reverse", "reverse")
        self.direction_combo.addItem("Ping-Pong", "pingpong")
        form.addRow("Direction", self.direction_combo)

        # Output resolution
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItem("Source", "source")
        self.resolution_combo.addItem("720p", "720p")
        self.resolution_combo.addItem("1080p", "1080p")
        self.resolution_combo.addItem("Custom", "custom")
        form.addRow("Resolution", self.resolution_combo)

        self.custom_width = QSpinBox()
        self.custom_width.setRange(16, 7680)
        self.custom_width.setValue(1280)
        self.custom_height = QSpinBox()
        self.custom_height.setRange(16, 4320)
        self.custom_height.setValue(720)
        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel("W"))
        custom_row.addWidget(self.custom_width)
        custom_row.addWidget(QLabel("H"))
        custom_row.addWidget(self.custom_height)
        form.addRow("Custom size", custom_row)

        layout.addLayout(form)

        # Slow motion
        slowmo_group = QGroupBox("Slow motion")
        slowmo_layout = QVBoxLayout(slowmo_group)
        self.slowmo_enable = QCheckBox("Enable slow motion")
        slowmo_layout.addWidget(self.slowmo_enable)

        method_row = QHBoxLayout()
        self.factor_radio = QRadioButton("Factor")
        self.target_radio = QRadioButton("Target duration (s)")
        self.factor_radio.setChecked(True)
        self.method_group = QButtonGroup(self)
        self.method_group.addButton(self.factor_radio)
        self.method_group.addButton(self.target_radio)
        method_row.addWidget(self.factor_radio)
        method_row.addWidget(self.target_radio)
        slowmo_layout.addLayout(method_row)

        self.factor_input = QDoubleSpinBox()
        self.factor_input.setRange(0.1, 100.0)
        self.factor_input.setSingleStep(0.1)
        self.factor_input.setValue(2.0)
        self.target_input = QDoubleSpinBox()
        self.target_input.setRange(0.1, 36000.0)
        self.target_input.setSingleStep(0.5)
        self.target_input.setValue(5.0)

        factor_row = QHBoxLayout()
        factor_row.addWidget(QLabel("Factor"))
        factor_row.addWidget(self.factor_input)
        slowmo_layout.addLayout(factor_row)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Target (s)"))
        target_row.addWidget(self.target_input)
        slowmo_layout.addLayout(target_row)

        # Audio policy
        audio_row = QHBoxLayout()
        self.include_audio = QCheckBox("Include audio")
        self.include_audio.setChecked(True)
        self.audio_policy = QComboBox()
        self.audio_policy.addItem("Stretch", "stretch")
        self.audio_policy.addItem("Mute", "mute")
        self.audio_policy.addItem("Drop if unsupported", "drop")
        audio_row.addWidget(self.include_audio)
        audio_row.addWidget(self.audio_policy)
        slowmo_layout.addLayout(audio_row)

        layout.addWidget(slowmo_group)

        # Buttons
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.ok_button = QPushButton("Export")
        self.ok_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.ok_button)
        layout.addLayout(button_row)

    def _wire_signals(self) -> None:
        self._browse_button.clicked.connect(self._browse_output)
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button.clicked.connect(self._on_accept)
        self.slowmo_enable.toggled.connect(self._update_ui_state)
        self.factor_radio.toggled.connect(self._update_ui_state)
        self.resolution_combo.currentIndexChanged.connect(self._update_ui_state)
        self.mode_combo.currentIndexChanged.connect(self._update_extension)
        self.mode_combo.currentIndexChanged.connect(self._update_ui_state)
        self.output_type_combo.currentIndexChanged.connect(self._update_extension)
        self.output_type_combo.currentIndexChanged.connect(self._update_ui_state)

    def _browse_output(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save clip", self.output_path_edit.text()
        )
        if filename:
            self.output_path_edit.setText(filename)

    def _update_extension(self) -> None:
        output_type = self.output_type_combo.currentData()
        mode = self.mode_combo.currentData()
        path = Path(self.output_path_edit.text())
        if not path.suffix:
            return

        if output_type == "audio":
            self.output_path_edit.setText(str(path.with_suffix(".mp3")))
            return

        if mode == "fast_copy":
            self.output_path_edit.setText(str(path.with_suffix(".mp4")))
        else:
            self.output_path_edit.setText(str(path.with_suffix(".webm")))

    def _update_ui_state(self) -> None:
        if self._audio_only_input:
            idx = self.output_type_combo.findData("audio")
            self.output_type_combo.setCurrentIndex(idx)
            self.output_type_combo.setEnabled(False)

        slowmo_enabled = self.slowmo_enable.isChecked()
        audio_only = self.output_type_combo.currentData() == "audio"
        self.factor_input.setEnabled(slowmo_enabled and self.factor_radio.isChecked())
        self.target_input.setEnabled(slowmo_enabled and self.target_radio.isChecked())
        self.audio_policy.setEnabled(slowmo_enabled and not audio_only)

        custom_enabled = self.resolution_combo.currentData() == "custom"
        self.custom_width.setEnabled(custom_enabled and not audio_only)
        self.custom_height.setEnabled(custom_enabled and not audio_only)

        is_fast_copy = self.mode_combo.currentData() == "fast_copy"
        self.direction_combo.setEnabled(not is_fast_copy and not audio_only)

        if audio_only:
            self.mode_combo.setCurrentIndex(0)
            self.mode_combo.setEnabled(False)
            self.resolution_combo.setEnabled(False)
            self.include_audio.setChecked(True)
            self.include_audio.setEnabled(False)
            self.direction_combo.setEnabled(False)
            if slowmo_enabled:
                self.audio_policy.setCurrentIndex(0)
        elif slowmo_enabled:
            self.mode_combo.setCurrentIndex(0)
            self.mode_combo.setEnabled(False)
            self.resolution_combo.setEnabled(True)
            self.include_audio.setEnabled(True)
        else:
            self.mode_combo.setEnabled(True)
            self.resolution_combo.setEnabled(True)
            self.include_audio.setEnabled(True)

    def _build_video_filter(self) -> str | None:
        choice = self.resolution_combo.currentData()
        if choice == "source":
            return None
        if choice == "720p":
            return "scale=-2:720"
        if choice == "1080p":
            return "scale=-2:1080"
        if choice == "custom":
            width = self.custom_width.value()
            height = self.custom_height.value()
            return f"scale={width}:{height}"
        return None

    def _on_accept(self) -> None:
        output_path = Path(self.output_path_edit.text().strip())
        output_type = self.output_type_combo.currentData()
        mode = self.mode_combo.currentData()

        output_dir = output_path.parent
        if not output_dir.exists():
            if (
                QMessageBox.question(
                    self,
                    "Create directory",
                    f"Output directory does not exist:\n{output_dir}\nCreate it?",
                )
                == QMessageBox.StandardButton.Yes
            ):
                output_dir.mkdir(parents=True, exist_ok=True)
            else:
                return

        slowmo = None
        if self.slowmo_enable.isChecked():
            audio_policy = self.audio_policy.currentData()
            if output_type == "audio" and audio_policy == "mute":
                audio_policy = "stretch"
            if self.factor_radio.isChecked():
                slowmo = SlowMoOptions(
                    factor=self.factor_input.value(), audio_policy=audio_policy
                )
            else:
                slowmo = SlowMoOptions(
                    target_duration=self.target_input.value(), audio_policy=audio_policy
                )

        video_filter = self._build_video_filter()
        include_audio = self.include_audio.isChecked()
        if output_type == "audio":
            include_audio = True

        self._options = ExportOptions(
            output_type=output_type,
            mode=mode,
            output_path=output_path,
            slowmo=slowmo,
            include_audio=include_audio,
            video_filter=video_filter,
            playback_mode=self.direction_combo.currentData()
            if mode == "accurate_reencode"
            else "forward",
        )
        self.accept()

    def get_options(self) -> ExportOptions | None:
        return self._options
