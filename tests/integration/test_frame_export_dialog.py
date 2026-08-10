from __future__ import annotations

from dataclasses import replace
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lucid_camera_control.application.state import (  # noqa: E402
    ApplicationSnapshot,
    CameraState,
)
from lucid_camera_control.ui.export_frames_dialog import (  # noqa: E402
    ExportFramesDialog,
)
from lucid_camera_control.ui.main_window import MainWindow  # noqa: E402


def create_avi(path: Path, frame_count: int = 5) -> None:
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (8, 6)
    )
    if not writer.isOpened():
        raise RuntimeError("Test AVI writer could not open")
    try:
        for index in range(frame_count):
            writer.write(np.full((6, 8, 3), index * 20, dtype=np.uint8))
    finally:
        writer.release()


class FrameExportDialogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])

    def test_main_window_opens_modal_export_dialog_while_disconnected(self) -> None:
        window = MainWindow()
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.show()
        self.app.processEvents()
        self.assertTrue(window.recording_panel.export_frames_button.isEnabled())

        window.recording_panel.export_frames_button.click()
        self.app.processEvents()
        dialog = window.findChild(ExportFramesDialog)
        self.assertIsNotNone(dialog)
        self.assertTrue(dialog.isModal())
        self.assertTrue(dialog.isVisible())
        dialog.reject()
        window.close()

    def test_recording_state_disables_export_entry(self) -> None:
        window = MainWindow()
        snapshot = replace(ApplicationSnapshot(), state=CameraState.RECORDING)
        window.recording_panel.apply_snapshot(snapshot, False)
        self.assertFalse(window.recording_panel.export_frames_button.isEnabled())
        window.close()

    def test_inspection_updates_metadata_estimate_and_range_controls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.avi"
            create_avi(source)
            dialog = ExportFramesDialog()
            dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            dialog.set_source(source)
            dialog.show()
            self.app.processEvents()

            self.assertIn("8 x 6", dialog.metadata_label.text())
            self.assertIn("5 BMP files", dialog.estimate_label.text())
            self.assertTrue(dialog.export_button.isEnabled())
            self.assertFalse(dialog.start_frame.isEnabled())
            dialog.range_enabled.setChecked(True)
            self.assertTrue(dialog.start_frame.isEnabled())
            self.assertEqual(dialog.end_frame.maximum(), 4)
            self.assertEqual(
                dialog.source_edit.nextInFocusChain(), dialog.source_browse
            )
            dialog.close()

    def test_escape_closes_settings_before_export_starts(self) -> None:
        dialog = ExportFramesDialog()
        dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        dialog.show()
        self.app.processEvents()
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(dialog.isVisible())


if __name__ == "__main__":
    unittest.main()
