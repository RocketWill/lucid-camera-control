"""Modal AVI-to-BMP export workflow."""

from __future__ import annotations

from pathlib import Path
import shutil
import threading

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lucid_camera_control.media.frame_exporter import (
    CollisionPolicy,
    FrameExportProgress,
    FrameExportRequest,
    FrameExportResult,
    FrameExporterService,
    VideoMetadata,
)


class _ExportWorker(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, service: FrameExporterService, request: FrameExportRequest):
        super().__init__()
        self._service = service
        self._request = request
        self._cancel = threading.Event()

    @Slot()
    def run(self) -> None:
        try:
            result = self._service.export(
                self._request,
                progress=self.progress.emit,
                cancelled=self._cancel.is_set,
            )
        except Exception as exc:
            self.failed.emit(str(exc) or type(exc).__name__)
        else:
            self.completed.emit(result)

    def cancel(self) -> None:
        self._cancel.set()


class ExportFramesDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        service: FrameExporterService | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export AVI Frames")
        self.setModal(True)
        self.setMinimumWidth(620)
        self._service = service or FrameExporterService()
        self._metadata: VideoMetadata | None = None
        self._thread: QThread | None = None
        self._worker: _ExportWorker | None = None
        self._running = False
        self._last_result: FrameExportResult | None = None

        self.source_edit = QLineEdit()
        self.source_edit.setAccessibleName("Source AVI")
        self.source_browse = QPushButton("Browse...")
        source_row = QHBoxLayout()
        source_row.addWidget(self.source_edit, 1)
        source_row.addWidget(self.source_browse)
        self.metadata_label = QLabel("Select an AVI to inspect its contents.")
        self.metadata_label.setWordWrap(True)
        source_group = QGroupBox("Source")
        source_layout = QVBoxLayout(source_group)
        source_layout.addLayout(source_row)
        source_layout.addWidget(self.metadata_label)

        self.range_enabled = QCheckBox("Export a frame range")
        self.start_frame = QSpinBox()
        self.start_frame.setRange(0, 2_147_483_647)
        self.start_frame.setAccessibleName("Start source frame")
        self.end_frame = QSpinBox()
        self.end_frame.setRange(0, 2_147_483_647)
        self.end_frame.setAccessibleName("End source frame")
        self.every_n = QSpinBox()
        self.every_n.setRange(1, 2_147_483_647)
        self.every_n.setValue(1)
        self.every_n.setSuffix(" frame(s)")
        self.every_n.setAccessibleName("Export every N frames")
        selection_group = QGroupBox("Frame Selection")
        selection_form = QFormLayout(selection_group)
        selection_form.addRow(self.range_enabled)
        selection_form.addRow("Start frame", self.start_frame)
        selection_form.addRow("End frame", self.end_frame)
        selection_form.addRow("Export every", self.every_n)

        self.destination_edit = QLineEdit()
        self.destination_edit.setAccessibleName("BMP output folder")
        self.destination_browse = QPushButton("Browse...")
        destination_row = QHBoxLayout()
        destination_row.addWidget(self.destination_edit, 1)
        destination_row.addWidget(self.destination_browse)
        self.collision_policy = QComboBox()
        self.collision_policy.setAccessibleName("Existing output handling")
        self.collision_policy.addItem(
            "Create a new folder when needed", CollisionPolicy.NEW_DIRECTORY
        )
        self.collision_policy.addItem("Skip existing BMP files", CollisionPolicy.SKIP)
        self.collision_policy.addItem(
            "Overwrite existing BMP files", CollisionPolicy.OVERWRITE
        )
        self.compression_label = QLabel("BMP compression: None (uncompressed)")
        self.estimate_label = QLabel("Estimated output: unavailable")
        self.estimate_label.setWordWrap(True)
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)
        output_layout.addLayout(destination_row)
        output_form = QFormLayout()
        output_form.addRow("Existing files", self.collision_policy)
        output_layout.addLayout(output_form)
        output_layout.addWidget(self.compression_label)
        output_layout.addWidget(self.estimate_label)

        self.validation_label = QLabel()
        self.validation_label.setObjectName("exportValidationLabel")
        self.validation_label.setWordWrap(True)
        self.validation_label.setAccessibleName("Export validation status")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_label = QLabel()
        self.progress_label.setWordWrap(True)
        self.progress_label.setVisible(False)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.export_button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        self.export_button.setText("Export")
        self.cancel_button = self.buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.setVisible(False)
        self.buttons.addButton(
            self.open_folder_button, QDialogButtonBox.ButtonRole.ActionRole
        )

        layout = QVBoxLayout(self)
        layout.addWidget(source_group)
        layout.addWidget(selection_group)
        layout.addWidget(output_group)
        layout.addWidget(self.validation_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.buttons)

        self.source_browse.clicked.connect(self._browse_source)
        self.destination_browse.clicked.connect(self._browse_destination)
        self.source_edit.editingFinished.connect(self._inspect_source)
        self.source_edit.textChanged.connect(self._clear_source_metadata)
        self.range_enabled.toggled.connect(self._range_toggled)
        self.start_frame.valueChanged.connect(self._refresh_validation)
        self.end_frame.valueChanged.connect(self._refresh_validation)
        self.every_n.valueChanged.connect(self._refresh_validation)
        self.destination_edit.textChanged.connect(self._refresh_validation)
        self.collision_policy.currentIndexChanged.connect(self._refresh_validation)
        self.buttons.accepted.connect(self._start_export)
        self.buttons.rejected.connect(self.reject)
        self.open_folder_button.clicked.connect(self._open_folder)
        self._range_toggled(False)
        self._refresh_validation()
        self._configure_tab_order()

    def set_source(self, source: Path) -> None:
        self.source_edit.setText(str(source))
        self.destination_edit.setText(str(source.parent / f"{source.stem}_frames"))
        self._inspect_source()

    def reject(self) -> None:
        if self._running:
            if self._worker is not None:
                self._worker.cancel()
            self.cancel_button.setEnabled(False)
            self.progress_label.setText("Cancelling after the current frame...")
            return
        super().reject()

    def _browse_source(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select AVI", self.source_edit.text(), "AVI Video (*.avi)"
        )
        if filename:
            self.set_source(Path(filename))

    def _browse_destination(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Select BMP Output Folder", self.destination_edit.text()
        )
        if directory:
            self.destination_edit.setText(directory)

    def _clear_source_metadata(self) -> None:
        self._metadata = None
        self.metadata_label.setText("Press Enter or leave the field to inspect this AVI.")
        self._refresh_validation()

    def _inspect_source(self) -> None:
        try:
            metadata = self._service.inspect(Path(self.source_edit.text().strip()))
        except Exception as exc:
            self._metadata = None
            self.metadata_label.setText(str(exc) or type(exc).__name__)
        else:
            self._metadata = metadata
            fps = f"{metadata.fps:.3f}" if metadata.fps is not None else "unknown"
            count = (
                f"{metadata.estimated_frame_count:,}"
                if metadata.estimated_frame_count is not None
                else "unknown"
            )
            duration = (
                f"{metadata.estimated_duration_seconds:.2f} s"
                if metadata.estimated_duration_seconds is not None
                else "unknown"
            )
            self.metadata_label.setText(
                f"{metadata.width} x {metadata.height} | {fps} FPS | "
                f"about {count} frames | {duration}"
            )
            if metadata.estimated_frame_count:
                self.end_frame.setMaximum(metadata.estimated_frame_count - 1)
                self.end_frame.setValue(metadata.estimated_frame_count - 1)
        self._refresh_validation()

    def _range_toggled(self, enabled: bool) -> None:
        self.start_frame.setEnabled(enabled)
        self.end_frame.setEnabled(enabled)
        self._refresh_validation()

    def _request(self) -> FrameExportRequest:
        return FrameExportRequest(
            Path(self.source_edit.text().strip()),
            Path(self.destination_edit.text().strip()),
            start_frame=self.start_frame.value() if self.range_enabled.isChecked() else 0,
            end_frame=self.end_frame.value() if self.range_enabled.isChecked() else None,
            every_n=self.every_n.value(),
            collision_policy=self.collision_policy.currentData(),
        )

    def _refresh_validation(self) -> None:
        if self._running:
            return
        error = ""
        if self._metadata is None:
            error = "Select and inspect a readable AVI file."
        elif not self.destination_edit.text().strip():
            error = "Select an output folder."
        elif self.range_enabled.isChecked() and (
            self.end_frame.value() < self.start_frame.value()
        ):
            error = "End frame must not be before start frame."
        self.validation_label.setText(error)
        self.export_button.setEnabled(not error)
        if error or self._metadata is None:
            self.estimate_label.setText("Estimated output: unavailable")
            return
        request = self._request()
        estimate = self._service.estimated_output_count(self._metadata, request)
        if estimate is None:
            self.estimate_label.setText("Estimated output: unavailable")
            return
        row_bytes = ((self._metadata.width * 3 + 3) // 4) * 4
        estimated_bytes = estimate * (row_bytes * self._metadata.height + 54)
        text = f"Estimated output: {estimate:,} BMP files, about {self._size(estimated_bytes)}"
        try:
            probe = request.destination
            while not probe.exists() and probe.parent != probe:
                probe = probe.parent
            free = shutil.disk_usage(probe).free
            if estimated_bytes > free:
                text += " | Warning: estimated size exceeds available disk space."
                self.export_button.setEnabled(False)
        except OSError:
            pass
        self.estimate_label.setText(text)

    def _start_export(self) -> None:
        if self._running:
            return
        request = self._request()
        if request.collision_policy is CollisionPolicy.OVERWRITE:
            answer = QMessageBox.warning(
                self,
                "Overwrite existing BMP files?",
                "Matching BMP files in the selected folder will be replaced.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer is not QMessageBox.StandardButton.Yes:
                return
        self._set_running(True)
        self._thread = QThread(self)
        self._worker = _ExportWorker(self._service, request)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.completed.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_worker)
        self._thread.start()

    def _set_running(self, running: bool) -> None:
        self._running = running
        for widget in (
            self.source_edit,
            self.source_browse,
            self.range_enabled,
            self.start_frame,
            self.end_frame,
            self.every_n,
            self.destination_edit,
            self.destination_browse,
            self.collision_policy,
        ):
            widget.setEnabled(not running)
        self.export_button.setVisible(not running)
        self.progress_bar.setVisible(running)
        self.progress_label.setVisible(running)
        self.cancel_button.setText("Cancel" if running else "Close")
        self.cancel_button.setEnabled(True)
        if running:
            self.validation_label.clear()
            self.progress_bar.setRange(0, 0)
            self.progress_label.setText("Starting export...")

    @Slot(object)
    def _on_progress(self, update: FrameExportProgress) -> None:
        if update.estimated_total is None:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, max(1, update.estimated_total))
            self.progress_bar.setValue(
                min(update.estimated_total, update.exported + update.skipped + update.failed)
            )
        text = (
            f"Exported {update.exported:,} | skipped {update.skipped:,} | "
            f"failed {update.failed:,} | elapsed {update.elapsed_seconds:.1f} s"
        )
        if update.estimated_remaining_seconds is not None:
            text += f" | about {update.estimated_remaining_seconds:.1f} s remaining"
        self.progress_label.setText(text)

    @Slot(object)
    def _on_completed(self, result: FrameExportResult) -> None:
        self._last_result = result
        self._set_running(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, max(1, result.exported + result.skipped + result.failed))
        self.progress_bar.setValue(result.exported + result.skipped + result.failed)
        outcome = "Export cancelled" if result.cancelled else "Export complete"
        self.progress_label.setVisible(True)
        self.progress_label.setText(
            f"{outcome}: {result.exported:,} exported, {result.skipped:,} skipped, "
            f"{result.failed:,} failed in {result.elapsed_seconds:.1f} s."
        )
        self.open_folder_button.setVisible(True)
        self.export_button.setVisible(False)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._set_running(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(True)
        self.progress_label.setText(f"Export failed: {message}")
        self._refresh_validation()

    @Slot()
    def _clear_worker(self) -> None:
        self._worker = None
        self._thread = None

    def _open_folder(self) -> None:
        if self._last_result is None:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_result.output_directory)))

    def _configure_tab_order(self) -> None:
        controls = (
            self.source_edit,
            self.source_browse,
            self.range_enabled,
            self.start_frame,
            self.end_frame,
            self.every_n,
            self.destination_edit,
            self.destination_browse,
            self.collision_policy,
            self.export_button,
            self.cancel_button,
        )
        for current, following in zip(controls, controls[1:]):
            self.setTabOrder(current, following)

    @staticmethod
    def _size(value: int) -> str:
        amount = float(value)
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if amount < 1024 or unit == "TiB":
                return f"{amount:.1f} {unit}"
            amount /= 1024
        return f"{amount:.1f} TiB"
