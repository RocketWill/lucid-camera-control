"""JSON configuration import, export, and explicit camera apply actions."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from lucid_camera_control.application.state import ApplicationSnapshot, CameraState


class ConfigPanel(QGroupBox):
    import_requested = Signal()
    export_requested = Signal()
    apply_requested = Signal()

    def __init__(self) -> None:
        super().__init__("JSON Configuration")
        self.import_button = QPushButton("Import JSON")
        self.export_button = QPushButton("Export JSON")
        self.apply_button = QPushButton("Apply Imported Camera Settings")
        self.status_label = QLabel("No configuration imported in this session.")
        self.status_label.setWordWrap(True)
        buttons = QHBoxLayout()
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.export_button)
        buttons.addWidget(self.apply_button)
        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self.status_label)
        self._snapshot = ApplicationSnapshot()
        self._busy = False
        self._has_pending = False
        self.import_button.clicked.connect(self.import_requested)
        self.export_button.clicked.connect(self.export_requested)
        self.apply_button.clicked.connect(self.apply_requested)
        self.apply_snapshot(self._snapshot, False)

    def set_loaded(self, source: str, *, automatic: bool = False) -> None:
        self._has_pending = True
        prefix = "Loaded last configuration" if automatic else "Imported"
        self.status_label.setText(
            f"{prefix}: {source}. Connect a camera, then apply camera settings."
        )
        self._refresh()

    def set_exported(self, path: str) -> None:
        self.status_label.setText(f"Exported: {path}")

    def set_applied(self) -> None:
        self.status_label.setText("Imported camera settings applied and verified.")

    def apply_snapshot(self, snapshot: ApplicationSnapshot, busy: bool) -> None:
        self._snapshot = snapshot
        self._busy = busy
        self._refresh()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._refresh()

    def _refresh(self) -> None:
        self.import_button.setEnabled(not self._busy)
        self.export_button.setEnabled(not self._busy)
        self.apply_button.setEnabled(
            self._has_pending
            and self._snapshot.state in (CameraState.CONNECTED, CameraState.STREAMING)
            and not self._busy
        )
