"""Camera discovery, selection, and lifecycle controls."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lucid_camera_control.application.state import ApplicationSnapshot, CameraState


class CameraPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.status_label = QLabel(CameraState.DISCONNECTED.value)
        self.status_label.setObjectName("cameraStateLabel")

        self.camera_combo = QComboBox()
        self.camera_combo.setObjectName("cameraSelectionCombo")
        self.camera_combo.setPlaceholderText("No cameras discovered")

        self.explore_button = QPushButton("Explore Cameras")
        self.explore_button.setObjectName("exploreCamerasButton")
        self.connect_button = QPushButton("Connect")
        self.connect_button.setObjectName("connectCameraButton")
        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("closeCameraButton")
        self.reset_button = QPushButton("Factory Reset")
        self.reset_button.setObjectName("factoryResetButton")

        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Status"))
        status_row.addWidget(self.status_label)
        status_row.addStretch(1)
        connect_row = QHBoxLayout()
        connect_row.addWidget(self.explore_button)
        connect_row.addWidget(self.connect_button)
        close_row = QHBoxLayout()
        close_row.addWidget(self.close_button)
        close_row.addWidget(self.reset_button)
        layout = QVBoxLayout(self)
        layout.addLayout(status_row)
        layout.addWidget(QLabel("Camera"))
        layout.addWidget(self.camera_combo)
        layout.addLayout(connect_row)
        layout.addLayout(close_row)

        self.apply_snapshot(ApplicationSnapshot(), busy=False)
        self.camera_combo.currentIndexChanged.connect(self._refresh_buttons)

    @property
    def selected_serial(self) -> str | None:
        value = self.camera_combo.currentData()
        return str(value) if value else None

    def select_serial(self, serial_number: str | None) -> bool:
        if not serial_number:
            return False
        index = self.camera_combo.findData(serial_number)
        if index < 0:
            return False
        self.camera_combo.setCurrentIndex(index)
        return True

    def apply_snapshot(self, snapshot: ApplicationSnapshot, busy: bool) -> None:
        self._snapshot = snapshot
        self._busy = busy
        self.status_label.setText(snapshot.state.value)
        self.connect_button.setText(
            "Reconnect"
            if snapshot.last_error is not None
            and snapshot.last_error.operation == "DeviceLost"
            else "Connect"
        )

        serials = tuple(
            self.camera_combo.itemData(index)
            for index in range(self.camera_combo.count())
        )
        discovered_serials = tuple(
            camera.serial_number for camera in snapshot.discovered_cameras
        )
        if serials != discovered_serials:
            selected = self.selected_serial
            self.camera_combo.clear()
            for camera in snapshot.discovered_cameras:
                self.camera_combo.addItem(camera.display_name, camera.serial_number)
            if selected:
                index = self.camera_combo.findData(selected)
                if index >= 0:
                    self.camera_combo.setCurrentIndex(index)
            if self.camera_combo.currentIndex() < 0 and self.camera_combo.count() > 0:
                self.camera_combo.setCurrentIndex(0)
        self._refresh_buttons()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        disconnected = self._snapshot.state is CameraState.DISCONNECTED
        self.explore_button.setEnabled(disconnected and not self._busy)
        self.camera_combo.setEnabled(disconnected and not self._busy)
        self.connect_button.setEnabled(
            disconnected and not self._busy and self.selected_serial is not None
        )
        self.close_button.setEnabled(not disconnected and not self._busy)
        self.reset_button.setEnabled(not disconnected and not self._busy)
