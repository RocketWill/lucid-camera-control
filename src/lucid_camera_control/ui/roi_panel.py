"""Hardware ROI controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lucid_camera_control.application.state import ApplicationSnapshot, CameraState
from lucid_camera_control.camera.nodes import NodeCapability
from lucid_camera_control.camera.roi import RoiRequest


class RoiPanel(QGroupBox):
    apply_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__("Hardware ROI")
        self.enable_roi = QCheckBox("Enable hardware ROI")
        self.enable_roi.setObjectName("enableRoiCheckBox")
        self.center_roi = QCheckBox("Center ROI")
        self.center_roi.setObjectName("centerRoiCheckBox")
        self.center_roi.setChecked(True)

        self.width = self._spin_box("roiWidthSpinBox")
        self.height = self._spin_box("roiHeightSpinBox")
        self.offset_x = self._spin_box("roiOffsetXSpinBox")
        self.offset_y = self._spin_box("roiOffsetYSpinBox")

        form = QFormLayout()
        form.addRow("Width", self.width)
        form.addRow("Height", self.height)
        form.addRow("Offset X", self.offset_x)
        form.addRow("Offset Y", self.offset_y)

        self.apply_button = QPushButton("Apply ROI")
        self.apply_button.setObjectName("applyRoiButton")
        self.full_frame_button = QPushButton("Full Frame")
        self.full_frame_button.setObjectName("fullFrameButton")
        self.result_label = QLabel("No ROI has been applied in this session.")
        self.result_label.setObjectName("roiResultLabel")
        self.result_label.setWordWrap(True)
        buttons = QHBoxLayout()
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.full_frame_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.enable_roi)
        layout.addWidget(self.center_roi)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.result_label)

        self._snapshot = ApplicationSnapshot()
        self._busy = False
        self.enable_roi.toggled.connect(self._refresh_enabled)
        self.center_roi.toggled.connect(self._refresh_enabled)
        self.apply_button.clicked.connect(self._emit_apply)
        self.full_frame_button.clicked.connect(
            lambda: self.apply_requested.emit(RoiRequest(False))
        )
        self.apply_snapshot(self._snapshot, busy=False)

    def apply_snapshot(self, snapshot: ApplicationSnapshot, busy: bool) -> None:
        self._snapshot = snapshot
        self._busy = busy
        capabilities = snapshot.roi_capabilities
        if capabilities is not None:
            self._configure_dimension(self.width, capabilities.width)
            self._configure_dimension(self.height, capabilities.height)
            self._configure_offset(
                self.offset_x,
                capabilities.offset_x,
                capabilities.width,
            )
            self._configure_offset(
                self.offset_y,
                capabilities.offset_y,
                capabilities.height,
            )
        if snapshot.roi_result is not None:
            applied = snapshot.roi_result.applied
            self.enable_roi.setChecked(applied.enabled)
            self.center_roi.setChecked(applied.centered)
            self.width.setValue(applied.width)
            self.height.setValue(applied.height)
            self.offset_x.setValue(applied.offset_x)
            self.offset_y.setValue(applied.offset_y)
            adjustment_names = sorted(
                {
                    item.name
                    for item in snapshot.roi_result.adjustments
                    if item.adjusted
                }
            )
            adjustment_text = (
                f" Adjusted: {', '.join(adjustment_names)}."
                if adjustment_names
                else " No alignment adjustment was required."
            )
            fps = snapshot.roi_result.maximum_fps
            fps_text = f" Maximum FPS: {fps:.2f}." if fps is not None else ""
            mode = "ROI" if applied.enabled else "Full frame"
            self.result_label.setText(
                f"{mode} applied: {applied.width} x {applied.height} "
                f"at ({applied.offset_x}, {applied.offset_y})."
                f"{adjustment_text}{fps_text}"
            )
        self._refresh_enabled()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._refresh_enabled()

    def _emit_apply(self) -> None:
        self.apply_requested.emit(
            RoiRequest(
                enabled=self.enable_roi.isChecked(),
                width=self.width.value(),
                height=self.height.value(),
                centered=self.center_roi.isChecked(),
                offset_x=self.offset_x.value(),
                offset_y=self.offset_y.value(),
            )
        )

    def _refresh_enabled(self) -> None:
        connected = self._snapshot.state in (CameraState.CONNECTED, CameraState.STREAMING)
        usable = connected and not self._busy and self._snapshot.roi_capabilities is not None
        controls = self._snapshot.control_capabilities
        binning = int(controls.binning_horizontal.value or 1) if controls else 1
        if binning > 1:
            usable = False
            self.result_label.setText("Hardware ROI requires 1 x 1 binning.")
        roi_enabled = usable and self.enable_roi.isChecked()
        manual = roi_enabled and not self.center_roi.isChecked()
        self.enable_roi.setEnabled(usable)
        self.center_roi.setEnabled(roi_enabled)
        self.width.setEnabled(roi_enabled)
        self.height.setEnabled(roi_enabled)
        self.offset_x.setEnabled(manual)
        self.offset_y.setEnabled(manual)
        self.apply_button.setEnabled(usable)
        self.full_frame_button.setEnabled(usable)

    @staticmethod
    def _spin_box(name: str) -> QSpinBox:
        spin = QSpinBox()
        spin.setObjectName(name)
        spin.setRange(0, 2_147_483_647)
        return spin

    @staticmethod
    def _configure_dimension(spin: QSpinBox, capability: NodeCapability) -> None:
        minimum = int(capability.minimum or 0)
        maximum = int(capability.maximum or max(minimum, int(capability.value or 0)))
        spin.setRange(minimum, maximum)
        spin.setSingleStep(max(1, int(capability.increment or 1)))
        if isinstance(capability.value, int):
            spin.setValue(capability.value)

    @staticmethod
    def _configure_offset(
        spin: QSpinBox,
        offset: NodeCapability,
        dimension: NodeCapability,
    ) -> None:
        minimum = int(offset.minimum or 0)
        sensor_extent = int(dimension.maximum or offset.maximum or minimum)
        spin.setRange(minimum, max(minimum, sensor_extent))
        spin.setSingleStep(max(1, int(offset.increment or 1)))
        if isinstance(offset.value, int):
            spin.setValue(offset.value)
