from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThreadPool
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from lucid_camera_control.application.controller import ApplicationController
from lucid_camera_control.camera.models import CameraDescriptor
from lucid_camera_control.ui.main_window import MainWindow


class FakeCamera:
    def __init__(self) -> None:
        self.descriptor = CameraDescriptor("ABC123", "TRI032S-C")
        self.closed = False

    def discover(self) -> tuple[CameraDescriptor, ...]:
        return (self.descriptor,)

    def connect(self, serial_number: str) -> CameraDescriptor:
        if serial_number != self.descriptor.serial_number:
            raise LookupError(serial_number)
        return self.descriptor

    def close(self) -> None:
        self.closed = True

    def start_stream(self) -> None:
        pass

    def stop_stream(self) -> None:
        pass


class CameraPanelIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])
        self.camera = FakeCamera()
        self.window = MainWindow(ApplicationController(self.camera))
        self.window.show()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def run_command(self, click: object) -> None:
        spy = QSignalSpy(self.window.bridge.command_completed)
        click()
        self.assertTrue(QThreadPool.globalInstance().waitForDone(2000))
        self.app.processEvents()
        self.assertEqual(spy.count(), 1)

    def test_explore_select_connect_and_close(self) -> None:
        self.run_command(self.window.camera_panel.explore_button.click)
        self.assertEqual(self.window.camera_panel.camera_combo.count(), 1)
        self.assertEqual(self.window.camera_panel.selected_serial, "ABC123")

        self.run_command(self.window.camera_panel.connect_button.click)
        self.assertEqual(self.window.status_label.text(), "Connected")
        self.assertFalse(self.window.camera_panel.explore_button.isEnabled())

        self.run_command(self.window.camera_panel.close_button.click)
        self.assertEqual(self.window.status_label.text(), "Disconnected")
        self.assertTrue(self.camera.closed)


if __name__ == "__main__":
    unittest.main()
