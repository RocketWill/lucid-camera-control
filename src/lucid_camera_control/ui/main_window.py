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
)
from lucid_camera_control.application.controller import ApplicationController
from lucid_camera_control.camera.arena_system import ArenaCameraSystem
from lucid_camera_control.ui.camera_panel import CameraPanel
from lucid_camera_control.ui.command_bridge import CommandBridge
from lucid_camera_control.ui.roi_panel import RoiPanel


class MainWindow(QMainWindow):
    """Minimal shell expanded by later implementation tickets."""

    def __init__(self, controller: ApplicationController | None = None) -> None:
        super().__init__()
        self.controller = controller or ApplicationController(ArenaCameraSystem())
        self.bridge = CommandBridge(self.controller)
        self.setWindowTitle("LUCID Camera Control")
        self.resize(1100, 720)

        title = QLabel("LUCID Camera Control")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.camera_panel = CameraPanel()
        self.roi_panel = RoiPanel()
        self.status_label = self.camera_panel.status_label
        self.explore_button = self.camera_panel.explore_button

        self.camera_panel.explore_button.clicked.connect(self._explore)
        self.camera_panel.connect_button.clicked.connect(self._connect)
        self.camera_panel.close_button.clicked.connect(self._close_camera)
        self.roi_panel.apply_requested.connect(
            lambda request: self.bridge.execute(ApplyRoi(request))
        )
        self.bridge.snapshot_changed.connect(self._on_snapshot)
        self.bridge.busy_changed.connect(self.camera_panel.set_busy)
        self.bridge.busy_changed.connect(self.roi_panel.set_busy)
        self.bridge.command_failed.connect(self._show_error)

        placeholder = QLabel("Connect a camera to begin.")
        placeholder.setObjectName("previewPlaceholder")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setMinimumSize(640, 360)

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(self.camera_panel)
        layout.addWidget(self.roi_panel)
        layout.addWidget(placeholder, stretch=1)

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

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Camera operation failed", message)
