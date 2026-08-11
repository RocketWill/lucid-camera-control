"""Main application window."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from pathlib import Path
from dataclasses import asdict
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QFileDialog,
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
from lucid_camera_control.ui.config_panel import ConfigPanel
from lucid_camera_control.media.recorder import RecorderService
from lucid_camera_control.media.screenshot import ScreenshotService
from lucid_camera_control.config.models import (
    AppConfigV1,
    CameraControlsConfig,
    RoiConfig,
    WindowConfig,
)
from lucid_camera_control.config.store import ConfigStore
from PySide6.QtCore import QStandardPaths
from lucid_camera_control.application.commands import ApplyConfiguration


class MainWindow(QMainWindow):
    """Minimal shell expanded by later implementation tickets."""

    def __init__(
        self,
        controller: ApplicationController | None = None,
        frame_source: FramePublisher | None = None,
        config_store: ConfigStore | None = None,
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
            self._screenshot_service = screenshot_service
        else:
            self._recorder_service = None
            self._screenshot_service = None
        self.controller = controller
        config_root = Path(
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppConfigLocation
            )
        )
        self._config_store = config_store or ConfigStore(config_root / "config.json")
        self._pending_config = AppConfigV1()
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
        self.config_panel = ConfigPanel()
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
        self.config_panel.import_requested.connect(self._import_config)
        self.config_panel.export_requested.connect(self._export_config)
        self.config_panel.apply_requested.connect(self._apply_imported_config)
        self.bridge.snapshot_changed.connect(self._on_snapshot)
        self.bridge.busy_changed.connect(self.camera_panel.set_busy)
        self.bridge.busy_changed.connect(self.roi_panel.set_busy)
        self.bridge.busy_changed.connect(self.controls_panel.set_busy)
        self.bridge.busy_changed.connect(self.preview_widget.set_busy)
        self.bridge.busy_changed.connect(self.recording_panel.set_busy)
        self.bridge.busy_changed.connect(self.config_panel.set_busy)
        self.bridge.command_completed.connect(self._on_command_completed)
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
        layout.addWidget(self.config_panel)
        layout.addWidget(self.preview_widget, stretch=1)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)
        self._load_last_config()

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
        self.config_panel.apply_snapshot(snapshot, self.bridge.busy)
        if snapshot.state is CameraState.DISCONNECTED:
            self.camera_panel.select_serial(
                self._pending_config.preferred_camera_serial
            )

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Camera operation failed", message)

    def _load_last_config(self) -> None:
        try:
            config = self._config_store.load_last_known_good()
        except Exception as exc:
            self.config_panel.status_label.setText(
                f"Last configuration is invalid: {exc}"
            )
            return
        if config is not None:
            self._pending_config = config
            self._apply_app_preferences(config)
            self.config_panel.set_loaded(
                str(self._config_store.last_known_good_path), automatic=True
            )

    def _import_config(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import Configuration", "", "JSON Configuration (*.json)"
        )
        if not filename:
            return
        try:
            config = self._config_store.parse(Path(filename))
            self._config_store.save_last_known_good(config)
        except Exception as exc:
            self._show_error(f"Configuration was not imported: {exc}")
            return
        self._pending_config = config
        self._apply_app_preferences(config)
        self.config_panel.set_loaded(filename)

    def _export_config(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Configuration", "camera-config.json", "JSON (*.json)"
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.casefold() != ".json":
            path = path.with_suffix(".json")
        try:
            config = self._runtime_config()
            self._config_store.export(config, path)
            self._config_store.save_last_known_good(config)
        except Exception as exc:
            self._show_error(f"Configuration was not exported: {exc}")
            return
        self._pending_config = config
        self.config_panel.set_exported(str(path))

    def _apply_imported_config(self) -> None:
        self.bridge.execute(ApplyConfiguration(self._pending_config))

    def _on_command_completed(self, events: object) -> None:
        if any(type(event).__name__ == "ConfigurationApplied" for event in events):
            self.config_panel.set_applied()
        try:
            config = self._runtime_config()
            self._config_store.save_last_known_good(config)
            self._pending_config = config
        except Exception:
            pass

    def _apply_app_preferences(self, config: AppConfigV1) -> None:
        self.preview_widget.contrast.setValue(config.preview_contrast)
        self.resize(config.window.width, config.window.height)
        if config.window.maximized:
            self.showMaximized()
        if self._recorder_service is not None:
            self._recorder_service.output_directory = config.recording_directory
        if self._screenshot_service is not None:
            self._screenshot_service.output_directory = config.screenshot_directory

    def _runtime_config(self) -> AppConfigV1:
        snapshot = self.controller.snapshot
        roi = self._pending_config.roi
        if snapshot.roi_result is not None:
            applied = snapshot.roi_result.applied
            roi = RoiConfig(
                enabled=applied.enabled,
                width=applied.width,
                height=applied.height,
                centered=applied.centered,
                offset_x=applied.offset_x,
                offset_y=applied.offset_y,
            )
        controls = self._pending_config.controls
        if snapshot.applied_configuration is not None:
            roi = snapshot.applied_configuration.roi
            controls = snapshot.applied_configuration.controls
        if snapshot.control_result is not None:
            if snapshot.applied_configuration is None:
                controls = CameraControlsConfig.model_validate(
                    asdict(snapshot.control_result.requested)
                )
        serial = (
            snapshot.active_camera.serial_number
            if snapshot.active_camera is not None
            else self._pending_config.preferred_camera_serial
        )
        screenshot_dir = self._pending_config.screenshot_directory
        recording_dir = self._pending_config.recording_directory
        if self._recorder_service is not None:
            recording_dir = self._recorder_service.output_directory
        if self._screenshot_service is not None:
            screenshot_dir = self._screenshot_service.output_directory
        return AppConfigV1(
            preferred_camera_serial=serial,
            roi=roi,
            controls=controls,
            screenshot_directory=screenshot_dir,
            recording_directory=recording_dir,
            preview_contrast=self.preview_widget.contrast.value(),
            window=WindowConfig(
                width=self.width(),
                height=self.height(),
                maximized=self.isMaximized(),
            ),
        )

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
