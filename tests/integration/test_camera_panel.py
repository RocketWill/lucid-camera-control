from __future__ import annotations

import os
import unittest
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThreadPool
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from lucid_camera_control.application.controller import ApplicationController
from lucid_camera_control.camera.models import CameraDescriptor
from lucid_camera_control.camera.controls import (
    CameraControlCapabilities,
    CameraControlRequest,
    CameraControlResult,
)
from lucid_camera_control.camera.nodes import NodeCapability, NodeKind
from lucid_camera_control.camera.roi import (
    AppliedRoi,
    RoiCapabilities,
    RoiRequest,
    RoiResult,
)
from lucid_camera_control.ui.main_window import MainWindow
from lucid_camera_control.config.store import ConfigStore
from lucid_camera_control.config.models import AppConfigV1


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

    def control_capabilities(self) -> CameraControlCapabilities:
        missing = lambda name: NodeCapability(
            name, NodeKind.UNAVAILABLE, False, False, False
        )
        return CameraControlCapabilities(
            missing("ExposureAuto"),
            missing("ExposureTime"),
            missing("GainAuto"),
            missing("Gain"),
            missing("AcquisitionFrameRateEnable"),
            missing("AcquisitionFrameRate"),
            missing("GammaEnable"),
            missing("Gamma"),
            missing("BlackLevel"),
            missing("BalanceWhiteAuto"),
            missing("BinningHorizontal"),
            missing("BinningVertical"),
        )

    def apply_controls(self, request: CameraControlRequest) -> CameraControlResult:
        return CameraControlResult(request, (), self.control_capabilities())

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
        self.temp_directory = tempfile.TemporaryDirectory()
        self.window = MainWindow(
            ApplicationController(self.camera),
            config_store=ConfigStore(
                Path(self.temp_directory.name) / "config.json"
            ),
        )
        self.window.show()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()
        self.temp_directory.cleanup()

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

    def test_last_known_good_loads_preferences_without_camera_mutation(self) -> None:
        self.window.close()
        self.app.processEvents()
        store = ConfigStore(Path(self.temp_directory.name) / "config.json")
        store.save_last_known_good(
            AppConfigV1(
                preferred_camera_serial="ABC123",
                preview_contrast=1.8,
            )
        )
        self.window = MainWindow(
            ApplicationController(self.camera),
            config_store=store,
        )
        self.assertEqual(self.window.preview_widget.contrast.value(), 1.8)
        self.assertIsNone(self.camera.last_roi_request)
        self.assertFalse(self.camera.closed)
        self.assertIn(
            "Loaded last configuration",
            self.window.config_panel.status_label.text(),
        )


if __name__ == "__main__":
    unittest.main()
