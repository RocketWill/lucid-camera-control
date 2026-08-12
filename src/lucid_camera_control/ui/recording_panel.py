"""Screenshot and recording actions plus live recording health."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from lucid_camera_control.application.state import ApplicationSnapshot, CameraState
from lucid_camera_control.media.recorder import RecordingStatus


class RecordingPanel(QGroupBox):
    screenshot_requested = Signal()
    start_requested = Signal()
    stop_requested = Signal()
    open_screenshot_folder_requested = Signal()
    open_recording_folder_requested = Signal()
    export_frames_requested = Signal()

    def __init__(
        self,
        status_provider: Callable[[], RecordingStatus] | None = None,
    ) -> None:
        super().__init__("Media Output")
        self.screenshot_button = QPushButton("Save PNG Screenshot")
        self.start_button = QPushButton("Start Raw AVI")
        self.stop_button = QPushButton("Stop Recording")
        self.open_screenshot_folder_button = QPushButton("Open Screenshot Folder")
        self.open_recording_folder_button = QPushButton("Open Recording Folder")
        self.export_frames_button = QPushButton("Export AVI Frames...")
        self.status_label = QLabel("Not recording")
        self.status_label.setWordWrap(True)
        self.path_label = QLabel("No media saved in this session.")
        self.path_label.setWordWrap(True)

        capture_buttons = QHBoxLayout()
        capture_buttons.addWidget(self.screenshot_button)
        capture_buttons.addWidget(self.start_button)
        capture_buttons.addWidget(self.stop_button)
        folder_buttons = QHBoxLayout()
        folder_buttons.addWidget(self.open_screenshot_folder_button)
        folder_buttons.addWidget(self.open_recording_folder_button)
        layout = QVBoxLayout(self)
        layout.addLayout(capture_buttons)
        layout.addLayout(folder_buttons)
        layout.addWidget(self.export_frames_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.path_label)

        self._snapshot = ApplicationSnapshot()
        self._busy = False
        self._status_provider = status_provider
        self.screenshot_button.clicked.connect(self.screenshot_requested)
        self.start_button.clicked.connect(self.start_requested)
        self.stop_button.clicked.connect(self.stop_requested)
        self.open_screenshot_folder_button.clicked.connect(
            self.open_screenshot_folder_requested
        )
        self.open_recording_folder_button.clicked.connect(
            self.open_recording_folder_requested
        )
        self.export_frames_button.clicked.connect(self.export_frames_requested)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start()
        self.apply_snapshot(self._snapshot, False)

    def apply_snapshot(self, snapshot: ApplicationSnapshot, busy: bool) -> None:
        self._snapshot = snapshot
        self._busy = busy
        if snapshot.last_screenshot_path is not None:
            self.path_label.setText(f"Screenshot: {snapshot.last_screenshot_path}")
        self._refresh_actions()
        self._refresh_status()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._refresh_actions()

    def _refresh_actions(self) -> None:
        state = self._snapshot.state
        self.screenshot_button.setEnabled(
            state in (CameraState.STREAMING, CameraState.RECORDING) and not self._busy
        )
        self.start_button.setEnabled(state is CameraState.STREAMING and not self._busy)
        self.stop_button.setEnabled(state is CameraState.RECORDING and not self._busy)
        self.open_screenshot_folder_button.setEnabled(not self._busy)
        self.open_recording_folder_button.setEnabled(not self._busy)
        self.export_frames_button.setEnabled(
            state is not CameraState.RECORDING and not self._busy
        )

    def _refresh_status(self) -> None:
        if self._status_provider is None:
            return
        status = self._status_provider()
        state = "Recording" if status.active else "Not recording"
        text = (
            f"{state} | {status.duration_seconds:.1f} s | "
            f"written {status.frames_written} | dropped {status.dropped_frames}"
        )
        if status.error:
            text += f" | {status.error}"
        self.status_label.setText(text)
        if status.output_path is not None:
            size = (
                status.output_path.stat().st_size
                if status.output_path.exists()
                else 0
            )
            self.path_label.setText(
                f"AVI: {status.output_path} ({size / (1024 * 1024):.1f} MiB)"
            )
