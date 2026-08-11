from __future__ import annotations

import unittest
from enum import Enum
from typing import Any

from lucid_camera_control.camera.nodes import (
    NodeAccessError,
    NodeAccessor,
    NodeKind,
)


class InterfaceType(Enum):
    INTEGER = 2
    BOOLEAN = 3
    FLOAT = 5
    STRING = 6
    ENUMERATION = 9
    COMMAND = 10


class FakeEntry:
    def __init__(self, readable: bool = True) -> None:
        self.is_readable = readable


class FakeNode:
    def __init__(
        self,
        kind: InterfaceType,
        value: object,
        *,
        readable: bool = True,
        writable: bool = True,
        minimum: int | float | None = None,
        maximum: int | float | None = None,
        increment: int | float | None = None,
        choices: tuple[str, ...] = (),
        unit: str = "",
    ) -> None:
        self.interface_type = kind
        self.is_readable = readable
        self.is_writable = writable
        self._value = value
        self.min = minimum
        self.max = maximum
        self.inc = increment
        self.unit = unit
        self.enumentry_names = list(choices)
        self.enumentry_nodes = {choice: FakeEntry() for choice in choices}
        self.execute_count = 0

    @property
    def value(self) -> object:
        if not self.is_readable:
            raise RuntimeError("not readable")
        return self._value

    @value.setter
    def value(self, value: object) -> None:
        if not self.is_writable:
            raise RuntimeError("not writable")
        self._value = value

    def execute(self) -> None:
        if not self.is_writable:
            raise RuntimeError("not writable")
        self.execute_count += 1


class FakeNodeMap:
    def __init__(self, nodes: dict[str, FakeNode] | None = None) -> None:
        self.nodes = nodes or {}

    def get_node(self, name: str) -> FakeNode:
        if name not in self.nodes:
            raise ValueError(name)
        return self.nodes[name]


class NodeAccessorTests(unittest.TestCase):
    def test_missing_node_returns_unavailable_snapshot(self) -> None:
        capability = NodeAccessor(FakeNodeMap()).snapshot("Missing")
        self.assertFalse(capability.available)
        self.assertEqual(capability.kind, NodeKind.UNAVAILABLE)

    def test_command_executes_only_through_writable_command_node(self) -> None:
        node = FakeNode(InterfaceType.COMMAND, None, readable=False)
        NodeAccessor(FakeNodeMap({"UserSetLoad": node})).execute_command(
            "UserSetLoad"
        )
        self.assertEqual(node.execute_count, 1)

    def test_unreadable_node_does_not_attempt_value_access(self) -> None:
        node = FakeNode(InterfaceType.INTEGER, 10, readable=False, minimum=0, maximum=20)
        capability = NodeAccessor(FakeNodeMap({"Width": node})).snapshot("Width")
        self.assertTrue(capability.available)
        self.assertFalse(capability.readable)
        self.assertIsNone(capability.value)

    def test_integer_write_clamps_aligns_and_reads_back(self) -> None:
        node = FakeNode(
            InterfaceType.INTEGER,
            64,
            minimum=64,
            maximum=200,
            increment=8,
            unit="px",
        )
        accessor = NodeAccessor(FakeNodeMap({"Width": node}))
        result = accessor.write_numeric("Width", 101)
        self.assertEqual(result.requested, 101)
        self.assertEqual(result.applied, 96)
        self.assertTrue(result.adjusted)
        self.assertEqual(result.capability.unit, "px")

    def test_integer_write_clamps_to_aligned_maximum(self) -> None:
        node = FakeNode(InterfaceType.INTEGER, 64, minimum=64, maximum=198, increment=8)
        result = NodeAccessor(FakeNodeMap({"Width": node})).write_numeric("Width", 999)
        self.assertEqual(result.applied, 192)

    def test_float_write_uses_decimal_alignment(self) -> None:
        node = FakeNode(
            InterfaceType.FLOAT,
            0.5,
            minimum=0.5,
            maximum=2.0,
            increment=0.1,
        )
        result = NodeAccessor(FakeNodeMap({"Gain": node})).write_numeric("Gain", 1.06)
        self.assertEqual(result.applied, 1.0)

    def test_enum_snapshot_filters_unreadable_entries(self) -> None:
        node = FakeNode(
            InterfaceType.ENUMERATION,
            "Off",
            choices=("Off", "Continuous"),
        )
        node.enumentry_nodes["Continuous"].is_readable = False
        capability = NodeAccessor(FakeNodeMap({"ExposureAuto": node})).snapshot(
            "ExposureAuto"
        )
        self.assertEqual(capability.choices, ("Off",))

    def test_invalid_enum_is_rejected_before_write(self) -> None:
        node = FakeNode(InterfaceType.ENUMERATION, "Off", choices=("Off", "Once"))
        accessor = NodeAccessor(FakeNodeMap({"ExposureAuto": node}))
        with self.assertRaises(NodeAccessError):
            accessor.write_enumeration("ExposureAuto", "Continuous")
        self.assertEqual(node.value, "Off")

    def test_read_only_node_reports_capability(self) -> None:
        node = FakeNode(
            InterfaceType.FLOAT,
            10.0,
            writable=False,
            minimum=1.0,
            maximum=20.0,
        )
        accessor = NodeAccessor(FakeNodeMap({"FPS": node}))
        with self.assertRaises(NodeAccessError) as caught:
            accessor.write_numeric("FPS", 15.0)
        self.assertFalse(caught.exception.capability.writable)

    def test_boolean_requires_actual_bool_and_reads_back(self) -> None:
        node = FakeNode(InterfaceType.BOOLEAN, False)
        accessor = NodeAccessor(FakeNodeMap({"Enabled": node}))
        result = accessor.write_boolean("Enabled", True)
        self.assertIs(result.applied, True)
        with self.assertRaises(NodeAccessError):
            accessor.write_boolean("Enabled", 1)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
