from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QSplitter  # noqa: E402

from lucid_camera_control.ui.main_window import MainWindow  # noqa: E402


class WorkspaceLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])
        self.window = MainWindow()
        self.window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.window.resize(1100, 720)
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_settings_and_imaging_workflows_use_resizable_panes(self) -> None:
        splitter = self.window.findChild(QSplitter, "workspaceSplitter")
        settings = self.window.findChild(QScrollArea, "settingsScrollArea")

        self.assertIsNotNone(splitter)
        self.assertIsNotNone(settings)
        self.assertEqual(splitter.orientation(), Qt.Orientation.Horizontal)
        self.assertTrue(settings.widgetResizable())
        self.assertTrue(settings.isAncestorOf(self.window.camera_panel))
        self.assertTrue(settings.isAncestorOf(self.window.roi_panel))
        self.assertTrue(settings.isAncestorOf(self.window.controls_panel))
        self.assertTrue(settings.isAncestorOf(self.window.config_panel))
        self.assertFalse(settings.isAncestorOf(self.window.preview_widget))
        self.assertFalse(settings.isAncestorOf(self.window.recording_panel))

    def test_standard_window_keeps_both_workflows_usable(self) -> None:
        splitter = self.window.findChild(QSplitter, "workspaceSplitter")

        self.assertEqual(self.window.width(), 1100)
        self.assertGreaterEqual(splitter.sizes()[0], 320)
        self.assertGreaterEqual(splitter.sizes()[1], 500)
        self.assertGreaterEqual(self.window.preview_widget.image_label.height(), 180)
        self.assertGreaterEqual(self.window.controls_panel.exposure_time.height(), 22)
        self.assertEqual(
            self.window.findChild(QScrollArea, "settingsScrollArea")
            .horizontalScrollBar()
            .maximum(),
            0,
        )

    def test_compact_window_scrolls_settings_without_crushing_controls(self) -> None:
        self.window.resize(900, 600)
        self.app.processEvents()
        splitter = self.window.findChild(QSplitter, "workspaceSplitter")
        settings = self.window.findChild(QScrollArea, "settingsScrollArea")

        self.assertEqual(self.window.size().toTuple(), (900, 600))
        self.assertGreaterEqual(splitter.sizes()[0], 320)
        self.assertGreaterEqual(splitter.sizes()[1], 500)
        self.assertEqual(settings.horizontalScrollBar().maximum(), 0)
        self.assertGreaterEqual(self.window.preview_widget.image_label.height(), 180)
        self.assertGreaterEqual(self.window.controls_panel.exposure_time.height(), 22)

    def test_camera_and_recording_state_remain_in_the_status_bar(self) -> None:
        camera_state = self.window.findChild(QLabel, "statusBarCameraState")
        recording_state = self.window.findChild(QLabel, "statusBarRecordingState")

        self.assertIsNotNone(camera_state)
        self.assertIsNotNone(recording_state)
        self.assertEqual(camera_state.text(), "Camera: Disconnected")
        self.assertEqual(recording_state.text(), "Recording: Inactive")

    def test_splitter_cannot_hide_either_workflow(self) -> None:
        splitter = self.window.findChild(QSplitter, "workspaceSplitter")

        splitter.setSizes([1, 1077])
        self.app.processEvents()
        self.assertGreaterEqual(splitter.sizes()[0], 320)

        splitter.setSizes([1077, 1])
        self.app.processEvents()
        self.assertGreaterEqual(splitter.sizes()[1], 500)

    def test_keyboard_order_moves_from_settings_to_imaging_actions(self) -> None:
        self.window.config_panel.apply_button.setEnabled(True)
        self.window.preview_widget.start_button.setEnabled(True)
        current = self.window.config_panel.apply_button.nextInFocusChain()
        while current is not self.window.config_panel.apply_button:
            if (
                current.focusPolicy() & Qt.FocusPolicy.TabFocus
                and current.isEnabled()
            ):
                break
            current = current.nextInFocusChain()

        self.assertIs(
            current,
            self.window.preview_widget.start_button,
        )


if __name__ == "__main__":
    unittest.main()
