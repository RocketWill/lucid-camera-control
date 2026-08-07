from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtTest import QSignalSpy  # noqa: E402

from lucid_camera_control.application.state import (  # noqa: E402
    ApplicationSnapshot,
    CameraState,
)
from lucid_camera_control.camera.controls import CameraControlCapabilities  # noqa: E402
from lucid_camera_control.camera.nodes import NodeCapability, NodeKind  # noqa: E402
from lucid_camera_control.ui.controls_panel import ControlsPanel  # noqa: E402


def numeric(
    name: str,
    value: float,
    minimum: float,
    maximum: float,
    increment: float | None,
    unit: str | None = None,
) -> NodeCapability:
    return NodeCapability(
        name,
        NodeKind.FLOAT,
        True,
        True,
        True,
        value=value,
        minimum=minimum,
        maximum=maximum,
        increment=increment,
        unit=unit,
    )


def unavailable(name: str) -> NodeCapability:
    return NodeCapability(name, NodeKind.UNAVAILABLE, False, False, False)


def capabilities() -> CameraControlCapabilities:
    return CameraControlCapabilities(
        NodeCapability(
            "ExposureAuto",
            NodeKind.ENUMERATION,
            True,
            True,
            True,
            value="Off",
            choices=("Off", "Continuous"),
        ),
        numeric("ExposureTime", 1000.0, 30.0, 30000.0, 5.0, "us"),
        unavailable("GainAuto"),
        unavailable("Gain"),
        unavailable("AcquisitionFrameRateEnable"),
        unavailable("AcquisitionFrameRate"),
        unavailable("GammaEnable"),
        unavailable("Gamma"),
        unavailable("BlackLevel"),
        unavailable("BalanceWhiteAuto"),
        unavailable("BinningHorizontal"),
        unavailable("BinningVertical"),
    )


def all_numeric_capabilities() -> CameraControlCapabilities:
    caps = capabilities()
    return CameraControlCapabilities(
        caps.exposure_auto,
        caps.exposure_time,
        NodeCapability(
            "GainAuto",
            NodeKind.ENUMERATION,
            True,
            True,
            True,
            value="Off",
            choices=("Off", "Continuous"),
        ),
        numeric("Gain", 2.0, 0.0, 48.0, None, "dB"),
        NodeCapability(
            "AcquisitionFrameRateEnable",
            NodeKind.BOOLEAN,
            True,
            True,
            True,
            value=True,
        ),
        numeric("AcquisitionFrameRate", 30.0, 0.1, 100.0, None, "Hz"),
        NodeCapability(
            "GammaEnable",
            NodeKind.BOOLEAN,
            True,
            True,
            True,
            value=True,
        ),
        numeric("Gamma", 1.0, 0.2, 2.0, None),
        numeric("BlackLevel", 0.0, 0.0, 12.5, None),
        unavailable("BalanceWhiteAuto"),
        unavailable("BinningHorizontal"),
        unavailable("BinningVertical"),
    )


class ControlSliderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])
        self.panel = ControlsPanel()

    def tearDown(self) -> None:
        self.panel.close()

    def test_exposure_uses_camera_range_and_increment(self) -> None:
        snapshot = ApplicationSnapshot(
            state=CameraState.CONNECTED,
            control_capabilities=capabilities(),
        )

        self.panel.apply_snapshot(snapshot, busy=False)

        self.assertEqual(self.panel.exposure_time.minimum(), 30.0)
        self.assertEqual(self.panel.exposure_time.maximum(), 30000.0)
        self.assertEqual(self.panel.exposure_time.singleStep(), 5.0)
        self.assertEqual(self.panel.exposure_time_slider.minimum(), 0)
        self.assertEqual(self.panel.exposure_time_slider.maximum(), 5994)
        self.assertEqual(
            self.panel.exposure_time_range.text(),
            "Range: 30 to 30000 us | Step: 5 us",
        )

    def test_exposure_slider_syncs_value_and_auto_disables_the_editor(self) -> None:
        snapshot = ApplicationSnapshot(
            state=CameraState.CONNECTED,
            control_capabilities=capabilities(),
        )
        self.panel.apply_snapshot(snapshot, busy=False)

        self.panel.exposure_time_slider.setValue(200)
        self.assertEqual(self.panel.exposure_time.value(), 1030.0)

        self.panel.exposure_time.setValue(1235.0)
        self.assertEqual(self.panel.exposure_time_slider.value(), 241)

        self.panel.exposure_auto.setChecked(True)
        self.assertFalse(self.panel.exposure_time_control.isEnabled())

    def test_common_numeric_controls_use_parameter_specific_fallback_steps(self) -> None:
        snapshot = ApplicationSnapshot(
            state=CameraState.CONNECTED,
            control_capabilities=all_numeric_capabilities(),
        )

        self.panel.apply_snapshot(snapshot, busy=False)

        expected_steps = (
            (self.panel.gain, self.panel.gain_slider, 0.1),
            (self.panel.frame_rate, self.panel.frame_rate_slider, 0.1),
            (self.panel.gamma, self.panel.gamma_slider, 0.01),
            (self.panel.black_level, self.panel.black_level_slider, 0.1),
        )
        for spin_box, slider, step in expected_steps:
            self.assertEqual(spin_box.singleStep(), step)
            self.assertGreater(slider.maximum(), slider.minimum())

    def test_slider_changes_remain_pending_until_apply(self) -> None:
        snapshot = ApplicationSnapshot(
            state=CameraState.CONNECTED,
            control_capabilities=all_numeric_capabilities(),
        )
        self.panel.apply_snapshot(snapshot, busy=False)
        spy = QSignalSpy(self.panel.apply_requested)

        self.panel.exposure_time_slider.setValue(200)
        self.panel.gain_slider.setValue(30)
        self.assertEqual(spy.count(), 0)

        self.panel.apply_button.click()
        self.assertEqual(spy.count(), 1)
        request = spy.at(0)[0]
        self.assertEqual(request.exposure_time, 1030.0)
        self.assertEqual(request.gain, 3.0)


if __name__ == "__main__":
    unittest.main()
