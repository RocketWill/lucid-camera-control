from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThreadPool
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from lucid_camera_control.application.controller import ApplicationController
from lucid_camera_control.camera.models import CameraDescriptor
from lucid_camera_control.camera.nodes import NodeCapability, NodeKind
from lucid_camera_control.camera.roi import (
    AppliedRoi,
    RoiCapabilities,
    RoiRequest,
    RoiResult,
)
from lucid_camera_control.ui.main_window import MainWindow


class FakeCamera:
    def __init__(self) -> None:
        self.descriptor = CameraDescriptor("ABC123", "TRI032S-C")
        self.closed = False
        self.last_roi_request: RoiRequest | None = None

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

    def roi_capabilities(self) -> RoiCapabilities:
        dimension = lambda name, value, maximum, increment: NodeCapability(
            name,
            NodeKind.INTEGER,
            True,
            True,
            True,
            value=value,
            minimum=0 if "Offset" in name else increment,
            maximum=maximum,
            increment=increment,
        )
        return RoiCapabilities(
            dimension("Width", 2048, 2048, 4),
            dimension("Height", 1536, 1536, 2),
            dimension("OffsetX", 0, 0, 4),
            dimension("OffsetY", 0, 0, 2),
            NodeCapability(
                "PixelFormat",
                NodeKind.ENUMERATION,
                True,
                True,
                True,
                value="Mono8",
                choices=("Mono8",),
            ),
        )

    def apply_roi(self, request: RoiRequest) -> RoiResult:
        self.last_roi_request = request
        applied = AppliedRoi(
            request.enabled,
            request.width if request.enabled else 2048,
            request.height if request.enabled else 1536,
            request.offset_x if request.enabled and not request.centered else 0,
            request.offset_y if request.enabled and not request.centered else 0,
            request.centered if request.enabled else False,
        )
        return RoiResult(request, applied, (), self.roi_capabilities(), 0, 60.0)


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

    def test_connected_operator_can_apply_centered_roi(self) -> None:
        self.run_command(self.window.camera_panel.explore_button.click)
        self.run_command(self.window.camera_panel.connect_button.click)
        panel = self.window.roi_panel
        panel.enable_roi.setChecked(True)
        panel.center_roi.setChecked(True)
        panel.width.setValue(1024)
        panel.height.setValue(768)
        self.run_command(panel.apply_button.click)
        self.assertEqual(
            self.camera.last_roi_request,
            RoiRequest(True, 1024, 768, True, 0, 0),
        )
        self.assertIn("ROI applied: 1024 x 768", panel.result_label.text())
        self.assertIn("Maximum FPS: 60.00", panel.result_label.text())


if __name__ == "__main__":
    unittest.main()
