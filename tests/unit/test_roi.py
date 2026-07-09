from __future__ import annotations

import unittest

from lucid_camera_control.camera.nodes import NodeAccessor
from lucid_camera_control.camera.roi import RoiRequest, RoiTransaction, RoiTransactionError
from tests.unit.test_nodes import FakeNode, FakeNodeMap, InterfaceType


class FailingPixelFormatNode(FakeNode):
    @FakeNode.value.setter
    def value(self, value: object) -> None:
        if value == "Mono8":
            raise RuntimeError("pixel format rejected")
        self._value = value


def roi_nodemap(*, fail_pixel_format: bool = False) -> FakeNodeMap:
    pixel_node_type = FailingPixelFormatNode if fail_pixel_format else FakeNode
    return FakeNodeMap(
        {
            "Width": FakeNode(
                InterfaceType.INTEGER,
                2048,
                minimum=4,
                maximum=2048,
                increment=4,
            ),
            "Height": FakeNode(
                InterfaceType.INTEGER,
                1536,
                minimum=2,
                maximum=1536,
                increment=2,
            ),
            "OffsetX": FakeNode(
                InterfaceType.INTEGER,
                0,
                minimum=0,
                maximum=2044,
                increment=4,
            ),
            "OffsetY": FakeNode(
                InterfaceType.INTEGER,
                0,
                minimum=0,
                maximum=1534,
                increment=2,
            ),
            "PixelFormat": pixel_node_type(
                InterfaceType.ENUMERATION,
                "BayerRG8",
                choices=("Mono8", "BayerRG8"),
            ),
            "BinningHorizontal": FakeNode(
                InterfaceType.INTEGER,
                2,
                minimum=1,
                maximum=2,
                increment=1,
            ),
            "BinningVertical": FakeNode(
                InterfaceType.INTEGER,
                2,
                minimum=1,
                maximum=2,
                increment=1,
            ),
            "PayloadSize": FakeNode(
                InterfaceType.INTEGER,
                700000,
                writable=False,
                minimum=0,
                maximum=10000000,
                increment=1,
            ),
            "AcquisitionFrameRate": FakeNode(
                InterfaceType.FLOAT,
                30.0,
                writable=False,
                minimum=0.1,
                maximum=60.0,
            ),
        }
    )


class RoiTransactionTests(unittest.TestCase):
    def test_centered_roi_aligns_dimensions_offsets_and_forces_mono8(self) -> None:
        nodemap = roi_nodemap()
        result = RoiTransaction(NodeAccessor(nodemap)).apply(
            RoiRequest(True, width=1001, height=701, centered=True)
        )
        self.assertEqual(result.applied.width, 1000)
        self.assertEqual(result.applied.height, 700)
        self.assertEqual(result.applied.offset_x, 524)
        self.assertEqual(result.applied.offset_y, 418)
        self.assertEqual(nodemap.nodes["BinningHorizontal"].value, 1)
        self.assertEqual(nodemap.nodes["BinningVertical"].value, 1)
        self.assertEqual(nodemap.nodes["PixelFormat"].value, "Mono8")
        self.assertEqual(result.payload_size, 700000)
        self.assertEqual(result.maximum_fps, 60.0)

    def test_manual_offsets_are_clamped_and_aligned(self) -> None:
        result = RoiTransaction(NodeAccessor(roi_nodemap())).apply(
            RoiRequest(
                True,
                width=1024,
                height=768,
                centered=False,
                offset_x=9999,
                offset_y=333,
            )
        )
        self.assertEqual(result.applied.offset_x, 2044)
        self.assertEqual(result.applied.offset_y, 332)

    def test_disabled_roi_restores_full_frame(self) -> None:
        nodemap = roi_nodemap()
        nodemap.nodes["Width"]._value = 800
        nodemap.nodes["Height"]._value = 600
        nodemap.nodes["OffsetX"]._value = 100
        nodemap.nodes["OffsetY"]._value = 100
        result = RoiTransaction(NodeAccessor(nodemap)).apply(RoiRequest(False))
        self.assertEqual(
            (result.applied.width, result.applied.height),
            (2048, 1536),
        )
        self.assertEqual((result.applied.offset_x, result.applied.offset_y), (0, 0))

    def test_failure_rolls_back_dimensions_offsets_binning_and_pixel_format(self) -> None:
        nodemap = roi_nodemap(fail_pixel_format=True)
        transaction = RoiTransaction(NodeAccessor(nodemap))
        with self.assertRaises(RoiTransactionError) as caught:
            transaction.apply(RoiRequest(True, 1024, 768, centered=True))
        self.assertEqual(caught.exception.rollback_errors, ())
        self.assertEqual(nodemap.nodes["Width"].value, 2048)
        self.assertEqual(nodemap.nodes["Height"].value, 1536)
        self.assertEqual(nodemap.nodes["OffsetX"].value, 0)
        self.assertEqual(nodemap.nodes["OffsetY"].value, 0)
        self.assertEqual(nodemap.nodes["BinningHorizontal"].value, 2)
        self.assertEqual(nodemap.nodes["BinningVertical"].value, 2)
        self.assertEqual(nodemap.nodes["PixelFormat"].value, "BayerRG8")


if __name__ == "__main__":
    unittest.main()
