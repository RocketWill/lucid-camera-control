from __future__ import annotations

import unittest

from lucid_camera_control.camera.controls import CameraControlRequest, CameraControls
from lucid_camera_control.camera.nodes import NodeAccessor
from tests.unit.test_nodes import FakeNode, FakeNodeMap, InterfaceType


def controls_nodemap() -> FakeNodeMap:
    enum = lambda value: FakeNode(
        InterfaceType.ENUMERATION,
        value,
        choices=("Off", "Continuous"),
    )
    number = lambda value, low, high: FakeNode(
        InterfaceType.FLOAT,
        value,
        minimum=low,
        maximum=high,
    )
    return FakeNodeMap(
        {
            "ExposureAuto": enum("Continuous"),
            "ExposureTime": number(1000.0, 30.0, 30000.0),
            "GainAuto": enum("Off"),
            "Gain": number(0.0, 0.0, 48.0),
            "AcquisitionFrameRateEnable": FakeNode(InterfaceType.BOOLEAN, False),
            "AcquisitionFrameRate": number(30.0, 0.1, 100.0),
            "GammaEnable": FakeNode(InterfaceType.BOOLEAN, True),
            "Gamma": number(1.0, 0.2, 2.0),
            "BlackLevel": number(0.0, 0.0, 12.5),
            "BalanceWhiteAuto": enum("Continuous"),
            "BinningHorizontal": FakeNode(
                InterfaceType.INTEGER, 1, minimum=1, maximum=8, increment=1
            ),
            "BinningVertical": FakeNode(
                InterfaceType.INTEGER, 1, minimum=1, maximum=8, increment=1
            ),
        }
    )


class CameraControlsTests(unittest.TestCase):
    def test_manual_modes_are_selected_before_verified_numeric_writes(self) -> None:
        nodemap = controls_nodemap()
        request = CameraControlRequest(
            False, 1234.5, False, 4.5, True, 50.0, True, 1.2, 2.0, False, 2
        )
        result = CameraControls(NodeAccessor(nodemap)).apply(request)
        self.assertEqual(nodemap.nodes["ExposureAuto"].value, "Off")
        self.assertEqual(nodemap.nodes["ExposureTime"].value, 1234.5)
        self.assertEqual(nodemap.nodes["AcquisitionFrameRate"].value, 50.0)
        self.assertEqual(nodemap.nodes["BinningHorizontal"].value, 2)
        self.assertEqual(nodemap.nodes["BinningVertical"].value, 2)
        self.assertEqual(result.capabilities.gamma.value, 1.2)

    def test_unsupported_binning_is_rejected_before_any_write(self) -> None:
        nodemap = controls_nodemap()
        request = CameraControlRequest(False, 1000, False, 0, False, 30, binning=3)
        with self.assertRaises(ValueError):
            CameraControls(NodeAccessor(nodemap)).apply(request)
        self.assertEqual(nodemap.nodes["ExposureAuto"].value, "Continuous")

    def test_absent_optional_binning_is_not_written(self) -> None:
        nodemap = controls_nodemap()
        del nodemap.nodes["BinningHorizontal"]
        del nodemap.nodes["BinningVertical"]
        request = CameraControlRequest(
            False, 1000, False, 0, False, 30, binning=None
        )
        result = CameraControls(NodeAccessor(nodemap)).apply(request)
        self.assertFalse(result.capabilities.binning_horizontal.available)
