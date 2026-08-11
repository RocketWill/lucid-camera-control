"""Main application window."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from lucid_camera_control.application.commands import (
    CloseCamera,
    ConnectCamera,
    ExploreCameras,
    ApplyRoi,
    StartStream,
    StopStream,
)
from lucid_camera_control.application.controller import ApplicationController
from lucid_camera_control.camera.arena_system import ArenaCameraSystem
from lucid_camera_control.ui.camera_panel import CameraPanel
from lucid_camera_control.ui.command_bridge import CommandBridge
from lucid_camera_control.ui.roi_panel import RoiPanel
from lucid_camera_control.ui.preview_bridge import FramePublisher, PreviewBridge
from lucid_camera_control.ui.preview_widget import PreviewWidget


class MainWindow(QMainWindow):
    """Minimal shell expanded by later implementation tickets."""

    def __init__(
        self,
        controller: ApplicationController | None = None,
        frame_source: FramePublisher | None = None,
    ) -> None:
        super().__init__()
        if controller is None:
            arena_camera = ArenaCameraSystem()
            controller = ApplicationController(arena_camera)
            frame_source = arena_camera
        self.controller = controller
        self.bridge = CommandBridge(self.controller)
        self.preview_bridge = PreviewBridge(frame_source) if frame_source else None
        self.setWindowTitle("LUCID Camera Control")
        self.resize(1100, 720)

        title = QLabel("LUCID Camera Control")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.camera_panel = CameraPanel()
        self.roi_panel = RoiPanel()
        self.preview_widget = PreviewWidget()
        self.status_label = self.camera_panel.status_label
        self.explore_button = self.camera_panel.explore_button

        self.camera_panel.explore_button.clicked.connect(self._explore)
        self.camera_panel.connect_button.clicked.connect(self._connect)
        self.camera_panel.close_button.clicked.connect(self._close_camera)
        self.roi_panel.apply_requested.connect(
            lambda request: self.bridge.execute(ApplyRoi(request))
        )
        self.preview_widget.start_requested.connect(
            lambda: self.bridge.execute(StartStream())
        )
        self.preview_widget.stop_requested.connect(
            lambda: self.bridge.execute(StopStream())
        )
        self.bridge.snapshot_changed.connect(self._on_snapshot)
        self.bridge.busy_changed.connect(self.camera_panel.set_busy)
        self.bridge.busy_changed.connect(self.roi_panel.set_busy)
        self.bridge.busy_changed.connect(self.preview_widget.set_busy)
        self.bridge.command_failed.connect(self._show_error)
        if self.preview_bridge is not None:
            self.preview_bridge.frame_arrived.connect(self.preview_widget.show_frame)
            self.preview_bridge.acquisition_failed.connect(self._show_error)

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(self.camera_panel)
        layout.addWidget(self.roi_panel)
        layout.addWidget(self.preview_widget, stretch=1)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

    def _explore(self) -> None:
        self.bridge.execute(ExploreCameras())

    def _connect(self) -> None:
        serial = self.camera_panel.selected_serial
        if serial:
            self.bridge.execute(ConnectCamera(serial))

    def _close_camera(self) -> None:
        self.bridge.execute(CloseCamera())

    def _on_snapshot(self, snapshot: object) -> None:
        self.camera_panel.apply_snapshot(snapshot, self.bridge.busy)
        self.roi_panel.apply_snapshot(snapshot, self.bridge.busy)
        self.preview_widget.apply_snapshot(snapshot, self.bridge.busy)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Camera operation failed", message)
