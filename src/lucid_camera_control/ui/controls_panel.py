"""Capability-driven common camera controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from lucid_camera_control.application.state import ApplicationSnapshot, CameraState
from lucid_camera_control.camera.controls import CameraControlRequest
from lucid_camera_control.camera.nodes import NodeCapability
from lucid_camera_control.ui.numeric_slider import NumericSliderControl


class ControlsPanel(QGroupBox):
    apply_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__("Camera Controls")
        self.exposure_auto = QCheckBox("Auto")
        self.exposure_time_control = NumericSliderControl(
            "exposureTime", "Exposure time"
        )
        self.exposure_time = self.exposure_time_control.spin_box
        self.exposure_time_slider = self.exposure_time_control.slider
        self.exposure_time_range = self.exposure_time_control.range_label
        self.gain_auto = QCheckBox("Auto")
        self.gain_control = NumericSliderControl("gain", "Gain")
        self.gain = self.gain_control.spin_box
        self.gain_slider = self.gain_control.slider
        self.gain_range = self.gain_control.range_label
        self.frame_rate_enabled = QCheckBox("Enabled")
        self.frame_rate_control = NumericSliderControl("frameRate", "Frame rate")
        self.frame_rate = self.frame_rate_control.spin_box
        self.frame_rate_slider = self.frame_rate_control.slider
        self.frame_rate_range = self.frame_rate_control.range_label
        self.gamma_enabled = QCheckBox("Enabled")
        self.gamma_control = NumericSliderControl("gamma", "Gamma")
        self.gamma = self.gamma_control.spin_box
        self.gamma_slider = self.gamma_control.slider
        self.gamma_range = self.gamma_control.range_label
        self.black_level_control = NumericSliderControl("blackLevel", "Black level")
        self.black_level = self.black_level_control.spin_box
        self.black_level_slider = self.black_level_control.slider
        self.black_level_range = self.black_level_control.range_label
        self.white_balance_auto = QCheckBox("Auto")
        self.binning = QComboBox()
        self.binning.addItem("1 x 1", 1)
        self.binning.addItem("2 x 2", 2)
        self.apply_button = QPushButton("Apply Controls")
        self.apply_button.setObjectName("applyControlsButton")
        self.note = QLabel("Unsupported controls are hidden for the connected camera.")
        self.note.setWordWrap(True)

        self.form = QFormLayout()
        self.form.addRow("Exposure mode", self.exposure_auto)
        self.form.addRow("Exposure time", self.exposure_time_control)
        self.form.addRow("Gain mode", self.gain_auto)
        self.form.addRow("Gain", self.gain_control)
        self.form.addRow("FPS limit", self.frame_rate_enabled)
        self.form.addRow("Frame rate", self.frame_rate_control)
        self.form.addRow("Gamma mode", self.gamma_enabled)
        self.form.addRow("Gamma", self.gamma_control)
        self.form.addRow("Black level", self.black_level_control)
        self.form.addRow("White balance", self.white_balance_auto)
        self.form.addRow("Binning", self.binning)
        layout = QVBoxLayout(self)
        layout.addLayout(self.form)
        layout.addWidget(self.note)
        layout.addWidget(self.apply_button)

        self._snapshot = ApplicationSnapshot()
        self._busy = False
        self.exposure_auto.toggled.connect(self._refresh_enabled)
        self.gain_auto.toggled.connect(self._refresh_enabled)
        self.frame_rate_enabled.toggled.connect(self._refresh_enabled)
        self.gamma_enabled.toggled.connect(self._refresh_enabled)
        self.apply_button.clicked.connect(self._emit_apply)
        self.apply_snapshot(self._snapshot, False)

    def apply_snapshot(self, snapshot: ApplicationSnapshot, busy: bool) -> None:
        self._snapshot = snapshot
        self._busy = busy
        caps = snapshot.control_capabilities
        if caps is not None:
            self._set_auto(self.exposure_auto, caps.exposure_auto)
            self.exposure_time_control.configure(caps.exposure_time, 1.0)
            self._set_auto(self.gain_auto, caps.gain_auto)
            self.gain_control.configure(caps.gain, 0.1)
            self._set_bool(self.frame_rate_enabled, caps.frame_rate_enable)
            self.frame_rate_control.configure(caps.frame_rate, 0.1)
            self._set_bool(self.gamma_enabled, caps.gamma_enable)
            self.gamma_control.configure(caps.gamma, 0.01)
            self.black_level_control.configure(caps.black_level, 0.1)
            self._set_auto(self.white_balance_auto, caps.white_balance_auto)
            binning = int(caps.binning_horizontal.value or 1)
            self.binning.setCurrentIndex(1 if binning == 2 else 0)
            has_binning = (
                caps.binning_horizontal.available and caps.binning_vertical.available
            )
            self._set_row_visible(self.binning, has_binning)
            self._set_row_visible(self.gamma_enabled, caps.gamma_enable.available)
            self._set_row_visible(self.gamma_control, caps.gamma.available)
            self._set_row_visible(
                self.black_level_control, caps.black_level.available
            )
            self._set_row_visible(
                self.white_balance_auto, caps.white_balance_auto.available
            )
        self._refresh_enabled()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._refresh_enabled()

    def _emit_apply(self) -> None:
        caps = self._snapshot.control_capabilities
        if caps is None:
            return
        self.apply_requested.emit(
            CameraControlRequest(
                self.exposure_auto.isChecked(),
                self.exposure_time.value(),
                self.gain_auto.isChecked(),
                self.gain.value(),
                self.frame_rate_enabled.isChecked(),
                self.frame_rate.value(),
                self.gamma_enabled.isChecked() if caps.gamma_enable.available else None,
                self.gamma.value() if caps.gamma.available else None,
                self.black_level.value() if caps.black_level.available else None,
                self.white_balance_auto.isChecked()
                if caps.white_balance_auto.available
                else None,
                int(self.binning.currentData())
                if caps.binning_horizontal.available
                and caps.binning_vertical.available
                else None,
            )
        )

    def _refresh_enabled(self) -> None:
        caps = self._snapshot.control_capabilities
        usable = (
            self._snapshot.state in (CameraState.CONNECTED, CameraState.STREAMING)
            and not self._busy
            and caps is not None
        )
        self.exposure_auto.setEnabled(usable and caps.exposure_auto.writable if caps else False)
        self.exposure_time_control.setEnabled(
            usable and not self.exposure_auto.isChecked()
        )
        self.gain_auto.setEnabled(usable and caps.gain_auto.writable if caps else False)
        self.gain_control.setEnabled(usable and not self.gain_auto.isChecked())
        self.frame_rate_enabled.setEnabled(
            usable and caps.frame_rate_enable.writable if caps else False
        )
        self.frame_rate_control.setEnabled(
            usable and self.frame_rate_enabled.isChecked()
        )
        self.gamma_enabled.setEnabled(usable and caps.gamma_enable.writable if caps else False)
        self.gamma_control.setEnabled(usable and self.gamma_enabled.isChecked())
        self.black_level_control.setEnabled(
            usable and caps.black_level.writable if caps else False
        )
        self.white_balance_auto.setEnabled(
            usable and caps.white_balance_auto.writable if caps else False
        )
        roi_on = bool(
            self._snapshot.roi_result and self._snapshot.roi_result.applied.enabled
        )
        has_binning = bool(
            caps
            and caps.binning_horizontal.writable
            and caps.binning_vertical.writable
        )
        self.binning.setEnabled(usable and has_binning and not roi_on)
        self.apply_button.setEnabled(usable)

    @staticmethod
    def _set_auto(widget: QCheckBox, cap: NodeCapability) -> None:
        widget.setChecked(cap.value != "Off")

    @staticmethod
    def _set_bool(widget: QCheckBox, cap: NodeCapability) -> None:
        widget.setChecked(bool(cap.value))

    def _set_row_visible(self, widget, visible: bool) -> None:
        widget.setVisible(visible)
        label = self.form.labelForField(widget)
        if label is not None:
            label.setVisible(visible)
