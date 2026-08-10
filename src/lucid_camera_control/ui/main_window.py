"""Main application window."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QDesktopServices
from pathlib import Path
from dataclasses import asdict
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QFileDialog,
    QScrollArea,
    QSplitter,
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
    ResetFactoryDefaults,
    HandleDeviceLoss,
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
from lucid_camera_control.ui.export_frames_dialog import ExportFramesDialog
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
from PySide6.QtCore import QStandardPaths, QUrl
from lucid_camera_control.application.commands import ApplyConfiguration
from lucid_camera_control.camera.acquisition import RecoverableFrameError


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
        self._pending_device_loss: str | None = None
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
        self.status_bar_camera_state = QLabel("Camera: Disconnected")
        self.status_bar_camera_state.setObjectName("statusBarCameraState")
        self.status_bar_recording_state = QLabel("Recording: Inactive")
        self.status_bar_recording_state.setObjectName("statusBarRecordingState")
        self.statusBar().addWidget(self.status_bar_camera_state)
        self.statusBar().addPermanentWidget(self.status_bar_recording_state)

        self.camera_panel.explore_button.clicked.connect(self._explore)
        self.camera_panel.connect_button.clicked.connect(self._connect)
        self.camera_panel.close_button.clicked.connect(self._close_camera)
        self.camera_panel.reset_button.clicked.connect(self._factory_reset)
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
        self.recording_panel.open_screenshot_folder_requested.connect(
            lambda: self._open_folder(self._pending_config.screenshot_directory)
        )
        self.recording_panel.open_recording_folder_requested.connect(
            lambda: self._open_folder(self._pending_config.recording_directory)
        )
        self.recording_panel.export_frames_requested.connect(self._export_avi_frames)
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
        self.bridge.busy_changed.connect(self._on_busy_changed)
        self.bridge.command_completed.connect(self._on_command_completed)
        self.bridge.command_failed.connect(self._show_error)
        if self.preview_bridge is not None:
            self.preview_bridge.frame_arrived.connect(self.preview_widget.show_frame)
            self.preview_bridge.acquisition_failed.connect(self._on_acquisition_error)

        settings_layout = QVBoxLayout()
        settings_layout.addWidget(self.camera_panel)
        settings_layout.addWidget(self.roi_panel)
        settings_layout.addWidget(self.controls_panel)
        settings_layout.addWidget(self.config_panel)
        settings_layout.addStretch(1)
        settings_content = QWidget()
        settings_content.setLayout(settings_layout)

        settings_scroll = QScrollArea()
        settings_scroll.setObjectName("settingsScrollArea")
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setMinimumWidth(320)
        settings_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        settings_scroll.setWidget(settings_content)

        imaging_layout = QVBoxLayout()
        imaging_layout.addWidget(self.preview_widget, stretch=1)
        imaging_layout.addWidget(self.recording_panel)
        imaging_content = QWidget()
        imaging_content.setLayout(imaging_layout)
        imaging_content.setMinimumWidth(500)

        workspace = QSplitter(Qt.Orientation.Horizontal)
        workspace.setObjectName("workspaceSplitter")
        workspace.addWidget(settings_scroll)
        workspace.addWidget(imaging_content)
        workspace.setCollapsible(0, False)
        workspace.setCollapsible(1, False)
        workspace.setStretchFactor(0, 0)
        workspace.setStretchFactor(1, 1)
        workspace.setSizes([380, 720])

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(workspace, stretch=1)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)
        self._configure_tab_order()
        self._load_last_config()

    def _configure_tab_order(self) -> None:
        controls = (
            self.camera_panel.camera_combo,
            self.camera_panel.explore_button,
            self.camera_panel.connect_button,
            self.camera_panel.close_button,
            self.camera_panel.reset_button,
            self.roi_panel.enable_roi,
            self.roi_panel.center_roi,
            self.roi_panel.width,
            self.roi_panel.height,
            self.roi_panel.offset_x,
            self.roi_panel.offset_y,
            self.roi_panel.apply_button,
            self.roi_panel.full_frame_button,
            self.controls_panel.exposure_auto,
            self.controls_panel.exposure_time_slider,
            self.controls_panel.exposure_time,
            self.controls_panel.gain_auto,
            self.controls_panel.gain_slider,
            self.controls_panel.gain,
            self.controls_panel.frame_rate_enabled,
            self.controls_panel.frame_rate_slider,
            self.controls_panel.frame_rate,
            self.controls_panel.gamma_enabled,
            self.controls_panel.gamma_slider,
            self.controls_panel.gamma,
            self.controls_panel.black_level_slider,
            self.controls_panel.black_level,
            self.controls_panel.white_balance_auto,
            self.controls_panel.binning,
            self.controls_panel.apply_button,
            self.config_panel.import_button,
            self.config_panel.export_button,
            self.config_panel.apply_button,
            self.preview_widget.start_button,
            self.preview_widget.stop_button,
            self.preview_widget.contrast,
            self.recording_panel.screenshot_button,
            self.recording_panel.start_button,
            self.recording_panel.stop_button,
            self.recording_panel.open_screenshot_folder_button,
            self.recording_panel.open_recording_folder_button,
            self.recording_panel.export_frames_button,
        )
        for current, following in zip(controls, controls[1:]):
            QWidget.setTabOrder(current, following)
        QWidget.setTabOrder(
            self.config_panel.apply_button,
            self.preview_widget.start_button,
        )

    def _export_avi_frames(self) -> None:
        dialog = ExportFramesDialog(self)
        dialog.open()

    def _explore(self) -> None:
        self.bridge.execute(ExploreCameras())

    def _connect(self) -> None:
        serial = self.camera_panel.selected_serial
        if serial:
            self.bridge.execute(ConnectCamera(serial))

    def _close_camera(self) -> None:
        self.bridge.execute(CloseCamera())

    def _factory_reset(self) -> None:
        answer = QMessageBox.warning(
            self,
            "Restore factory defaults?",
            "Recording and preview will stop. Current camera settings will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is QMessageBox.StandardButton.Yes:
            self.bridge.execute(ResetFactoryDefaults())

    def _on_acquisition_error(self, error: object) -> None:
        if isinstance(error, RecoverableFrameError):
            return
        self._pending_device_loss = str(error) or type(error).__name__
        self._dispatch_pending_device_loss()

    def _on_busy_changed(self, busy: bool) -> None:
        if not busy:
            self._dispatch_pending_device_loss()

    def _dispatch_pending_device_loss(self) -> None:
        if self.bridge.busy or self._pending_device_loss is None:
            return
        message, self._pending_device_loss = self._pending_device_loss, None
        self.bridge.execute(HandleDeviceLoss(message))

    def _on_snapshot(self, snapshot: object) -> None:
        self.camera_panel.apply_snapshot(snapshot, self.bridge.busy)
        self.roi_panel.apply_snapshot(snapshot, self.bridge.busy)
        self.controls_panel.apply_snapshot(snapshot, self.bridge.busy)
        self.preview_widget.apply_snapshot(snapshot, self.bridge.busy)
        self.recording_panel.apply_snapshot(snapshot, self.bridge.busy)
        self.config_panel.apply_snapshot(snapshot, self.bridge.busy)
        self.status_bar_camera_state.setText(f"Camera: {snapshot.state.value}")
        self.status_bar_recording_state.setText(
            "Recording: Active"
            if snapshot.state is CameraState.RECORDING
            else "Recording: Inactive"
        )
        if snapshot.state is CameraState.DISCONNECTED:
            self.camera_panel.select_serial(
                self._pending_config.preferred_camera_serial
            )

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Camera operation failed", message)

    def _open_folder(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

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
        if any(type(event).__name__ == "FactoryDefaultsLoaded" for event in events):
            self._pending_config = self._factory_default_config()
        try:
            config = self._runtime_config()
            self._config_store.save_last_known_good(config)
            self._pending_config = config
        except Exception:
            pass

    def _factory_default_config(self) -> AppConfigV1:
        snapshot = self.controller.snapshot
        roi_caps = snapshot.roi_capabilities
        control_caps = snapshot.control_capabilities
        if roi_caps is None or control_caps is None:
            return self._pending_config
        width = int(roi_caps.width.value or 0)
        height = int(roi_caps.height.value or 0)
        offset_x = int(roi_caps.offset_x.value or 0)
        offset_y = int(roi_caps.offset_y.value or 0)
        roi = RoiConfig(
            enabled=bool(
                width < int(roi_caps.width.maximum or width)
                or height < int(roi_caps.height.maximum or height)
                or offset_x
                or offset_y
            ),
            width=width,
            height=height,
            centered=False,
            offset_x=offset_x,
            offset_y=offset_y,
        )
        controls = CameraControlsConfig(
            exposure_auto=control_caps.exposure_auto.value != "Off",
            exposure_time=float(control_caps.exposure_time.value or 1000),
            gain_auto=control_caps.gain_auto.value != "Off",
            gain=float(control_caps.gain.value or 0),
            frame_rate_enabled=bool(control_caps.frame_rate_enable.value),
            frame_rate=float(control_caps.frame_rate.value or 30),
            gamma_enabled=bool(control_caps.gamma_enable.value)
            if control_caps.gamma_enable.available
            else None,
            gamma=float(control_caps.gamma.value)
            if control_caps.gamma.value is not None
            else None,
            black_level=float(control_caps.black_level.value)
            if control_caps.black_level.value is not None
            else None,
            white_balance_auto=control_caps.white_balance_auto.value != "Off"
            if control_caps.white_balance_auto.available
            else None,
            binning=int(control_caps.binning_horizontal.value or 1)
            if control_caps.binning_horizontal.available
            else None,
        )
        return self._pending_config.model_copy(
            update={"roi": roi, "controls": controls}
        )

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
