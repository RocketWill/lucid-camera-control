"""Arena SDK implementation of camera discovery and lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from arena_api.system import system as arena_system

from lucid_camera_control.camera.models import CameraDescriptor
from lucid_camera_control.camera.nodes import (
    NodeAccessor,
    NodeCapability,
    NodeWriteResult,
)


class ArenaSystemLike(Protocol):
    @property
    def device_infos(self) -> list[dict[str, Any]]: ...

    def create_device(self, device_info: dict[str, Any]) -> list[Any]: ...

    def destroy_device(self, device: Any) -> None: ...


class CameraNotFoundError(LookupError):
    """The requested serial number was not found during fresh discovery."""


class CameraConnectionError(RuntimeError):
    """Arena did not create the requested camera device."""


class CameraNotConnectedError(RuntimeError):
    """An operation requires an active Arena device."""


class ArenaCameraSystem:
    """Own exactly one Arena device while exposing a testable lifecycle port."""

    def __init__(self, system: ArenaSystemLike | None = None) -> None:
        self._system = system or arena_system
        self._device: Any | None = None
        self._active_descriptor: CameraDescriptor | None = None

    @property
    def active_descriptor(self) -> CameraDescriptor | None:
        return self._active_descriptor

    @property
    def is_connected(self) -> bool:
        return self._device is not None

    def discover(self) -> tuple[CameraDescriptor, ...]:
        descriptors: list[CameraDescriptor] = []
        for info in self._system.device_infos:
            descriptor = self._descriptor_from_info(info)
            if descriptor is not None:
                descriptors.append(descriptor)
        return tuple(sorted(descriptors, key=lambda item: item.serial_number))

    def connect(self, serial_number: str) -> CameraDescriptor:
        if self._device is not None:
            raise CameraConnectionError("A camera is already connected")

        requested = serial_number.strip()
        if not requested:
            raise CameraNotFoundError("Camera serial number is required")

        selected_info: dict[str, Any] | None = None
        selected_descriptor: CameraDescriptor | None = None
        for info in self._system.device_infos:
            descriptor = self._descriptor_from_info(info)
            if descriptor is not None and descriptor.serial_number == requested:
                selected_info = dict(info)
                selected_descriptor = descriptor
                break

        if selected_info is None or selected_descriptor is None:
            raise CameraNotFoundError(f"LUCID camera {requested!r} was not found")

        devices = self._system.create_device(selected_info)
        if len(devices) != 1:
            for device in devices:
                self._system.destroy_device(device)
            raise CameraConnectionError(
                f"Arena created {len(devices)} devices for serial {requested!r}"
            )

        self._device = devices[0]
        self._active_descriptor = selected_descriptor
        return selected_descriptor

    def close(self) -> None:
        device, self._device = self._device, None
        self._active_descriptor = None
        if device is not None:
            self._system.destroy_device(device)

    def start_stream(self) -> None:
        self._require_device().start_stream()

    def stop_stream(self) -> None:
        self._require_device().stop_stream()

    def node_capability(self, name: str) -> NodeCapability:
        return self._node_accessor().snapshot(name)

    def node_capabilities(self, names: tuple[str, ...]) -> tuple[NodeCapability, ...]:
        return self._node_accessor().snapshot_many(names)

    def write_numeric_node(self, name: str, value: int | float) -> NodeWriteResult:
        return self._node_accessor().write_numeric(name, value)

    def write_enumeration_node(self, name: str, value: str) -> NodeWriteResult:
        return self._node_accessor().write_enumeration(name, value)

    def write_boolean_node(self, name: str, value: bool) -> NodeWriteResult:
        return self._node_accessor().write_boolean(name, value)

    def _require_device(self) -> Any:
        if self._device is None:
            raise CameraNotConnectedError("No camera is connected")
        return self._device

    def _node_accessor(self) -> NodeAccessor:
        return NodeAccessor(self._require_device().nodemap)

    @classmethod
    def _descriptor_from_info(
        cls,
        info: Mapping[str, Any],
    ) -> CameraDescriptor | None:
        vendor = cls._optional_text(info.get("vendor"))
        serial = cls._optional_text(info.get("serial"))
        if vendor is None or "lucid" not in vendor.casefold() or serial is None:
            return None
        return CameraDescriptor(
            serial_number=serial,
            model_name=cls._optional_text(info.get("model")),
            vendor_name=vendor,
            user_defined_name=cls._optional_text(info.get("name")),
            ip_address=cls._optional_text(info.get("ip")),
            mac_address=cls._optional_text(info.get("mac")),
            firmware_version=cls._optional_text(info.get("version")),
        )

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
