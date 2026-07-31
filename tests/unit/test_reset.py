from __future__ import annotations

import unittest

from lucid_camera_control.camera.nodes import NodeAccessor
from lucid_camera_control.camera.reset import FactoryResetTransaction
from tests.unit.test_controls import controls_nodemap
from tests.unit.test_nodes import FakeNode, InterfaceType


class FactoryResetTests(unittest.TestCase):
    def test_default_user_set_loads_and_capabilities_refresh(self) -> None:
        nodemap = controls_nodemap()
        nodemap.nodes.update(
            {
                "UserSetSelector": FakeNode(
                    InterfaceType.ENUMERATION,
                    "UserSet1",
                    choices=("Default", "UserSet1"),
                ),
                "UserSetLoad": FakeNode(
                    InterfaceType.COMMAND, None, readable=False
                ),
                "Width": FakeNode(
                    InterfaceType.INTEGER, 2048, minimum=64, maximum=2048, increment=4
                ),
                "Height": FakeNode(
                    InterfaceType.INTEGER, 1536, minimum=2, maximum=1536, increment=2
                ),
                "OffsetX": FakeNode(
                    InterfaceType.INTEGER, 0, minimum=0, maximum=1984, increment=4
                ),
                "OffsetY": FakeNode(
                    InterfaceType.INTEGER, 0, minimum=0, maximum=1534, increment=2
                ),
                "PixelFormat": FakeNode(
                    InterfaceType.ENUMERATION, "Mono8", choices=("Mono8",)
                ),
            }
        )
        result = FactoryResetTransaction(NodeAccessor(nodemap)).apply()
        self.assertEqual(nodemap.nodes["UserSetSelector"].value, "Default")
        self.assertEqual(nodemap.nodes["UserSetLoad"].execute_count, 1)
        self.assertEqual(result.roi_capabilities.width.value, 2048)
        self.assertEqual(result.control_capabilities.gain.value, 0.0)

    def test_missing_default_user_set_fails_before_command(self) -> None:
        nodemap = controls_nodemap()
        command = FakeNode(InterfaceType.COMMAND, None, readable=False)
        nodemap.nodes.update(
            {
                "UserSetSelector": FakeNode(
                    InterfaceType.ENUMERATION,
                    "UserSet1",
                    choices=("UserSet1",),
                ),
                "UserSetLoad": command,
            }
        )
        with self.assertRaises(RuntimeError):
            FactoryResetTransaction(NodeAccessor(nodemap)).apply()
        self.assertEqual(command.execute_count, 0)
