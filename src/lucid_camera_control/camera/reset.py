"""Factory-default UserSet reset with refreshed capability readback."""

from __future__ import annotations

from dataclasses import dataclass

from lucid_camera_control.camera.controls import CameraControlCapabilities, CameraControls
from lucid_camera_control.camera.nodes import NodeAccessor
from lucid_camera_control.camera.roi import RoiCapabilities, RoiTransaction


@dataclass(frozen=True, slots=True)
class FactoryResetResult:
    roi_capabilities: RoiCapabilities
    control_capabilities: CameraControlCapabilities


class FactoryResetTransaction:
    def __init__(self, nodes: NodeAccessor) -> None:
        self._nodes = nodes

    def apply(self) -> FactoryResetResult:
        selector = self._nodes.snapshot("UserSetSelector")
        load = self._nodes.snapshot("UserSetLoad")
        if "Default" not in selector.choices or not selector.writable:
            raise RuntimeError("Camera does not expose a writable Default UserSet")
        if not load.available or not load.writable:
            raise RuntimeError("Camera does not expose a writable UserSetLoad command")
        self._nodes.write_enumeration("UserSetSelector", "Default")
        self._nodes.execute_command("UserSetLoad")
        return FactoryResetResult(
            RoiTransaction(self._nodes).capabilities(),
            CameraControls(self._nodes).capabilities(),
        )
