"""Main application window."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lucid_camera_control.application.state import CameraState


class MainWindow(QMainWindow):
    """Minimal shell expanded by later implementation tickets."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LUCID Camera Control")
        self.resize(1100, 720)

        title = QLabel("LUCID Camera Control")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel(CameraState.DISCONNECTED.value)
        self.status_label.setObjectName("cameraStateLabel")

        self.explore_button = QPushButton("Explore Cameras")
        self.explore_button.setObjectName("exploreCamerasButton")

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.status_label)
        toolbar.addStretch(1)
        toolbar.addWidget(self.explore_button)

        placeholder = QLabel("Connect a camera to begin.")
        placeholder.setObjectName("previewPlaceholder")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setMinimumSize(640, 360)

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addLayout(toolbar)
        layout.addWidget(placeholder, stretch=1)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

