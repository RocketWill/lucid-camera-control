"""Mono8 live preview with display-only contrast."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

import numpy as np

from lucid_camera_control.application.state import ApplicationSnapshot, CameraState
from lucid_camera_control.media.frame import Frame


class PreviewWidget(QGroupBox):
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self) -> None:
        super().__init__("Live Preview")
        self.image_label = QLabel("Start preview to acquire frames.")
        self.image_label.setObjectName("previewImageLabel")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(640, 360)

        self.fps_label = QLabel("Receive FPS: --")
        self.fps_label.setObjectName("receiveFpsLabel")
        self.contrast = QDoubleSpinBox()
        self.contrast.setObjectName("previewContrastSpinBox")
        self.contrast.setRange(0.1, 3.0)
        self.contrast.setSingleStep(0.1)
        self.contrast.setValue(1.0)
        self.contrast.setSuffix("x")
        self.contrast.setToolTip("Preview only; saved frames are unchanged")

        self.start_button = QPushButton("Start Preview")
        self.start_button.setObjectName("startPreviewButton")
        self.stop_button = QPushButton("Stop Preview")
        self.stop_button.setObjectName("stopPreviewButton")
        self.start_button.clicked.connect(self.start_requested)
        self.stop_button.clicked.connect(self.stop_requested)

        controls = QHBoxLayout()
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addStretch(1)
        controls.addWidget(self.fps_label)
        controls.addWidget(QLabel("Preview-only contrast"))
        controls.addWidget(self.contrast)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.image_label, stretch=1)

        self._snapshot = ApplicationSnapshot()
        self._busy = False
        self._last_image: QImage | None = None
        self._last_fps_update_ns = 0
        self.apply_snapshot(self._snapshot, False)

    def apply_snapshot(self, snapshot: ApplicationSnapshot, busy: bool) -> None:
        self._snapshot = snapshot
        self._busy = busy
        self._refresh_actions()
        if snapshot.state in (CameraState.DISCONNECTED, CameraState.CONNECTED):
            self.fps_label.setText("Receive FPS: --")

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._refresh_actions()

    def show_frame(self, frame: Frame, fps: float) -> None:
        image_data = frame.mono8_view()
        contrast = self.contrast.value()
        if contrast != 1.0:
            image_data = np.clip(
                (image_data.astype(np.float32) - 127.5) * contrast + 127.5,
                0,
                255,
            ).astype(np.uint8)
        image = QImage(
            image_data.data,
            frame.width,
            frame.height,
            int(image_data.strides[0]),
            QImage.Format.Format_Grayscale8,
        ).copy()
        self._last_image = image
        self._render_image()
        if frame.received_monotonic_ns - self._last_fps_update_ns >= 250_000_000:
            self.fps_label.setText(f"Receive FPS: {fps:.2f}")
            self._last_fps_update_ns = frame.received_monotonic_ns

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._render_image()

    def _render_image(self) -> None:
        if self._last_image is None:
            return
        pixmap = QPixmap.fromImage(self._last_image).scaled(
            self.image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(pixmap)

    def _refresh_actions(self) -> None:
        self.start_button.setEnabled(
            self._snapshot.state is CameraState.CONNECTED and not self._busy
        )
        self.stop_button.setEnabled(
            self._snapshot.state is CameraState.STREAMING and not self._busy
        )
        self.contrast.setEnabled(
            self._snapshot.state in (CameraState.STREAMING, CameraState.RECORDING)
        )
