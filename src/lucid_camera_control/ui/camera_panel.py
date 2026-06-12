"""Camera discovery, selection, and lifecycle controls."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QGridLayout, QLabel, QPushButton, QWidget

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
        self.close_button = QPushButton("Close Camera")
        self.close_button.setObjectName("closeCameraButton")

        layout = QGridLayout(self)
        layout.addWidget(QLabel("Status"), 0, 0)
        layout.addWidget(self.status_label, 0, 1)
        layout.addWidget(QLabel("Camera"), 1, 0)
        layout.addWidget(self.camera_combo, 1, 1)
        layout.addWidget(self.explore_button, 1, 2)
        layout.addWidget(self.connect_button, 1, 3)
        layout.addWidget(self.close_button, 1, 4)

        self.apply_snapshot(ApplicationSnapshot(), busy=False)
        self.camera_combo.currentIndexChanged.connect(self._refresh_buttons)

    @property
    def selected_serial(self) -> str | None:
        value = self.camera_combo.currentData()
        return str(value) if value else None

    def apply_snapshot(self, snapshot: ApplicationSnapshot, busy: bool) -> None:
        self._snapshot = snapshot
        self._busy = busy
        self.status_label.setText(snapshot.state.value)

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
