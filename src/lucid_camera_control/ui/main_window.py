"""Main application window."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from pathlib import Path
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
    ApplyCameraControls,
    StartStream,
    StopStream,
    StartRecording,
    StopRecording,
    CaptureScreenshot,
)
from lucid_camera_control.application.controller import ApplicationController
from lucid_camera_control.application.state import CameraState
from lucid_camera_control.camera.arena_system import ArenaCameraSystem
from lucid_camera_control.ui.camera_panel import CameraPanel
from lucid_camera_control.ui.command_bridge import CommandBridge
from lucid_camera_control.ui.roi_panel import RoiPanel
from lucid_camera_control.ui.preview_bridge import FramePublisher, PreviewBridge
from lucid_camera_control.ui.preview_widget import PreviewWidget
from lucid_camera_control.ui.controls_panel import ControlsPanel
from lucid_camera_control.ui.recording_panel import RecordingPanel
from lucid_camera_control.media.recorder import RecorderService
from lucid_camera_control.media.screenshot import ScreenshotService


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
            screenshot_service = ScreenshotService(
                Path.home() / "Pictures" / "LUCID Camera Control"
            )
            recorder_service = RecorderService(
                Path.home() / "Videos" / "LUCID Camera Control"
            )
            arena_camera.subscribe_frames(screenshot_service.receive)
            arena_camera.subscribe_frames(recorder_service.receive)
            controller = ApplicationController(
                arena_camera,
                recorder_service,
                screenshot_service,
            )
            frame_source = arena_camera
            self._recorder_service = recorder_service
        else:
            self._recorder_service = None
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
        self.controls_panel = ControlsPanel()
        self.preview_widget = PreviewWidget()
        self.recording_panel = RecordingPanel(
            (lambda: self._recorder_service.status)
            if self._recorder_service is not None
            else None
        )
        self.status_label = self.camera_panel.status_label
        self.explore_button = self.camera_panel.explore_button

        self.camera_panel.explore_button.clicked.connect(self._explore)
        self.camera_panel.connect_button.clicked.connect(self._connect)
        self.camera_panel.close_button.clicked.connect(self._close_camera)
        self.roi_panel.apply_requested.connect(
            lambda request: self.bridge.execute(ApplyRoi(request))
        )
        self.controls_panel.apply_requested.connect(
            lambda request: self.bridge.execute(ApplyCameraControls(request))
        )
        self.preview_widget.start_requested.connect(
            lambda: self.bridge.execute(StartStream())
        )
        self.preview_widget.stop_requested.connect(
            lambda: self.bridge.execute(StopStream())
        )
        self.recording_panel.screenshot_requested.connect(
            lambda: self.bridge.execute(CaptureScreenshot())
        )
        self.recording_panel.start_requested.connect(
            lambda: self.bridge.execute(StartRecording())
        )
        self.recording_panel.stop_requested.connect(
            lambda: self.bridge.execute(StopRecording())
        )
        self.bridge.snapshot_changed.connect(self._on_snapshot)
        self.bridge.busy_changed.connect(self.camera_panel.set_busy)
        self.bridge.busy_changed.connect(self.roi_panel.set_busy)
        self.bridge.busy_changed.connect(self.controls_panel.set_busy)
        self.bridge.busy_changed.connect(self.preview_widget.set_busy)
        self.bridge.busy_changed.connect(self.recording_panel.set_busy)
        self.bridge.command_failed.connect(self._show_error)
        if self.preview_bridge is not None:
            self.preview_bridge.frame_arrived.connect(self.preview_widget.show_frame)
            self.preview_bridge.acquisition_failed.connect(self._show_error)

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(self.camera_panel)
        layout.addWidget(self.roi_panel)
        layout.addWidget(self.controls_panel)
        layout.addWidget(self.recording_panel)
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
        self.controls_panel.apply_snapshot(snapshot, self.bridge.busy)
        self.preview_widget.apply_snapshot(snapshot, self.bridge.busy)
        self.recording_panel.apply_snapshot(snapshot, self.bridge.busy)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Camera operation failed", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.controller.snapshot.state is CameraState.RECORDING:
            answer = QMessageBox.question(
                self,
                "Stop recording and exit?",
                "The AVI must be finalized before the application exits.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer is not QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self.controller.snapshot.state is not CameraState.DISCONNECTED:
            self.controller.execute(CloseCamera())
        event.accept()
