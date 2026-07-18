"""Capability-driven common camera controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from lucid_camera_control.application.state import ApplicationSnapshot, CameraState
from lucid_camera_control.camera.controls import CameraControlRequest
from lucid_camera_control.camera.nodes import NodeCapability


class ControlsPanel(QGroupBox):
    apply_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__("Camera Controls")
        self.exposure_auto = QCheckBox("Continuous auto exposure")
        self.exposure_time = self._numeric("exposureTimeSpinBox")
        self.gain_auto = QCheckBox("Continuous auto gain")
        self.gain = self._numeric("gainSpinBox")
        self.frame_rate_enabled = QCheckBox("Limit acquisition frame rate")
        self.frame_rate = self._numeric("frameRateSpinBox")
        self.gamma_enabled = QCheckBox("Enable gamma")
        self.gamma = self._numeric("gammaSpinBox")
        self.black_level = self._numeric("blackLevelSpinBox")
        self.white_balance_auto = QCheckBox("Continuous auto white balance")
        self.binning = QComboBox()
        self.binning.addItem("1 x 1", 1)
        self.binning.addItem("2 x 2", 2)
        self.apply_button = QPushButton("Apply Controls")
        self.apply_button.setObjectName("applyControlsButton")
        self.note = QLabel("Unsupported controls are hidden for the connected camera.")
        self.note.setWordWrap(True)

        self.form = QFormLayout()
        self.form.addRow("Exposure mode", self.exposure_auto)
        self.form.addRow("Exposure time", self.exposure_time)
        self.form.addRow("Gain mode", self.gain_auto)
        self.form.addRow("Gain", self.gain)
        self.form.addRow("Frame-rate control", self.frame_rate_enabled)
        self.form.addRow("Frame rate", self.frame_rate)
        self.form.addRow("Gamma mode", self.gamma_enabled)
        self.form.addRow("Gamma", self.gamma)
        self.form.addRow("Black level", self.black_level)
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
            self._configure_numeric(self.exposure_time, caps.exposure_time)
            self._set_auto(self.gain_auto, caps.gain_auto)
            self._configure_numeric(self.gain, caps.gain)
            self._set_bool(self.frame_rate_enabled, caps.frame_rate_enable)
            self._configure_numeric(self.frame_rate, caps.frame_rate)
            self._set_bool(self.gamma_enabled, caps.gamma_enable)
            self._configure_numeric(self.gamma, caps.gamma)
            self._configure_numeric(self.black_level, caps.black_level)
            self._set_auto(self.white_balance_auto, caps.white_balance_auto)
            binning = int(caps.binning_horizontal.value or 1)
            self.binning.setCurrentIndex(1 if binning == 2 else 0)
            has_binning = (
                caps.binning_horizontal.available and caps.binning_vertical.available
            )
            self._set_row_visible(self.binning, has_binning)
            self._set_row_visible(self.gamma_enabled, caps.gamma_enable.available)
            self._set_row_visible(self.gamma, caps.gamma.available)
            self._set_row_visible(self.black_level, caps.black_level.available)
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
        self.exposure_time.setEnabled(usable and not self.exposure_auto.isChecked())
        self.gain_auto.setEnabled(usable and caps.gain_auto.writable if caps else False)
        self.gain.setEnabled(usable and not self.gain_auto.isChecked())
        self.frame_rate_enabled.setEnabled(
            usable and caps.frame_rate_enable.writable if caps else False
        )
        self.frame_rate.setEnabled(usable and self.frame_rate_enabled.isChecked())
        self.gamma_enabled.setEnabled(usable and caps.gamma_enable.writable if caps else False)
        self.gamma.setEnabled(usable and self.gamma_enabled.isChecked())
        self.black_level.setEnabled(usable and caps.black_level.writable if caps else False)
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
    def _numeric(name: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setObjectName(name)
        spin.setDecimals(3)
        spin.setRange(-1_000_000_000, 1_000_000_000)
        return spin

    @staticmethod
    def _configure_numeric(widget: QDoubleSpinBox, cap: NodeCapability) -> None:
        if cap.minimum is not None and cap.maximum is not None:
            widget.setRange(float(cap.minimum), float(cap.maximum))
        widget.setSingleStep(float(cap.increment or 0.1))
        if isinstance(cap.value, (int, float)) and not isinstance(cap.value, bool):
            widget.setValue(float(cap.value))
        if cap.unit:
            widget.setSuffix(f" {cap.unit}")

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
